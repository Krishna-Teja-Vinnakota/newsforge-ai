from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Iterable

from app.core.database import get_database
from app.core.settings import settings
from app.models.trends import ConnectorResult, TrendRefreshResponse, TrendSignal, TrendSourceStatus
from app.services.trends.connectors import CONNECTORS, connector_client, enrich_with_gdelt, fetch_connector

logger = logging.getLogger("newsforge.trends")
_refresh_lock = asyncio.Lock()
_snapshot_lock = asyncio.Lock()
_refresh_task: asyncio.Task | None = None


def configured_sources() -> list[str]:
    aliases = {"weather_alert": "weather"}
    names = [
        aliases.get(item.strip().casefold(), item.strip().casefold()) for item in settings.trends_sources.split(",")
    ]
    return list(dict.fromkeys(name for name in names if name))


async def _replace_scope(result: ConnectorResult) -> None:
    """Replace one successful source/geo snapshot; failures never call this."""
    async with _snapshot_lock:
        collection = get_database().trend_signals
        signal_ids: list[str] = []
        for signal in result.signals:
            signal_ids.append(signal.signal_id)
            document = signal.model_dump()
            document.update({"_id": signal.signal_id, "scope_source": result.source, "scope_geo": result.geo})
            await collection.replace_one({"_id": signal.signal_id}, document, upsert=True)
        criteria: dict = {"scope_source": result.source, "scope_geo": result.geo}
        if signal_ids:
            criteria["_id"] = {"$nin": signal_ids}
        await collection.delete_many(criteria)


async def load_fresh_signals(now: datetime, max_age_hours: int) -> list[TrendSignal]:
    """Read a complete in-process snapshot while successful refreshes swap scopes."""
    cutoff = now - timedelta(hours=max_age_hours)
    async with _snapshot_lock:
        cursor = get_database().trend_signals.find({"expires_at": {"$gt": now}, "observed_at": {"$gte": cutoff}})
        return [TrendSignal.model_validate(item) async for item in cursor]


async def _record_result(result: ConnectorResult, started_at: datetime, duration_ms: int) -> TrendSourceStatus:
    now = datetime.now(UTC)
    if result.source != "gdelt" and result.status in {"success", "success_empty"}:
        await _replace_scope(result)
    count = result.processed_count if result.processed_count is not None else len(result.signals)
    run = {
        "source": result.source,
        "geo": result.geo,
        "status": result.status,
        "count": count,
        "duration_ms": duration_ms,
        "started_at": started_at,
        "completed_at": now,
        "error_code": result.error_code,
    }
    if result.status in {"success", "success_empty"}:
        run["last_success_at"] = now
    else:
        previous = await get_database().trend_refresh_runs.find_one(
            {"source": result.source, "geo": result.geo, "status": {"$in": ["success", "success_empty"]}},
            sort=[("started_at", -1)],
        )
        run["last_success_at"] = previous.get("completed_at") if previous else None
    await get_database().trend_refresh_runs.insert_one(run)
    return TrendSourceStatus(
        source=result.source,
        geo=result.geo,
        status=result.status,
        count=count,
        duration_ms=duration_ms,
        last_success_at=run["last_success_at"],
        error_code=result.error_code,
        next_refresh_at=started_at + timedelta(minutes=settings.trends_refresh_minutes),
    )


async def _refresh_one(source: str, geo: str, client, semaphore: asyncio.Semaphore) -> TrendSourceStatus:
    started_at = datetime.now(UTC)
    started = perf_counter()
    connector = CONNECTORS.get(source)
    if source == "gdelt":
        cached = [
            TrendSignal.model_validate(item)
            async for item in get_database().trend_signals.find({"expires_at": {"$gt": started_at}})
        ]
        async with semaphore:
            try:
                result, updates = await enrich_with_gdelt(cached, geo, client, started_at)
                async with _snapshot_lock:
                    for signal_id, velocity in updates.items():
                        await get_database().trend_signals.update_one(
                            {"_id": signal_id},
                            {"$set": {"velocity": velocity, "raw.gdelt_velocity": velocity}},
                        )
            except Exception as error:
                error_code = getattr(error, "code", "unexpected_error")
                result = ConnectorResult(source=source, geo=geo, status="failed", error_code=error_code)
    elif connector is None:
        result = ConnectorResult(source=source, geo=geo, status="failed", error_code="unsupported_source")
    else:
        async with semaphore:
            result = await fetch_connector(connector, geo, client, started_at)
    duration_ms = int((perf_counter() - started) * 1000)
    if result.status == "failed":
        logger.warning("Trend refresh failed for %s/%s: %s", source, geo, result.error_code)
    return await _record_result(result, started_at, duration_ms)


async def refresh_trends(sources: Iterable[str] | None = None) -> TrendRefreshResponse:
    """Refresh configured scopes once, without allowing scheduled/manual overlap."""
    if _refresh_lock.locked():
        return TrendRefreshResponse(status="refresh_in_progress")
    async with _refresh_lock:
        selected = list(sources) if sources is not None else configured_sources()
        geo = settings.trends_geo.upper()
        semaphore = asyncio.Semaphore(4)
        async with connector_client() as client:
            base_sources = [source for source in selected if source != "gdelt"]
            statuses = list(
                await asyncio.gather(*(_refresh_one(source, geo, client, semaphore) for source in base_sources))
            )
            # GDELT only enriches the snapshot produced by primary connectors.
            if "gdelt" in selected:
                statuses.append(await _refresh_one("gdelt", geo, client, semaphore))
        overall = "success" if all(item.status != "failed" for item in statuses) else "partial_failure"
        return TrendRefreshResponse(status=overall, sources=list(statuses))


async def get_trend_status() -> TrendRefreshResponse:
    now = datetime.now(UTC)
    geo = settings.trends_geo.upper()
    statuses: list[TrendSourceStatus] = []
    for source in configured_sources():
        latest = await get_database().trend_refresh_runs.find_one(
            {"source": source, "geo": geo}, sort=[("started_at", -1)]
        )
        latest_success = await get_database().trend_refresh_runs.find_one(
            {"source": source, "geo": geo, "status": {"$in": ["success", "success_empty"]}},
            sort=[("started_at", -1)],
        )
        count = (
            int(latest.get("count", 0))
            if source == "gdelt" and latest
            else await get_database().trend_signals.count_documents(
                {
                    "scope_source": source,
                    "scope_geo": geo,
                    "expires_at": {"$gt": now},
                }
            )
        )
        started = latest.get("started_at") if latest else None
        statuses.append(
            TrendSourceStatus(
                source=source,
                geo=geo,
                status=latest.get("status", "never_run") if latest else "never_run",
                count=count,
                duration_ms=int(latest.get("duration_ms", 0)) if latest else 0,
                last_success_at=latest_success.get("completed_at") if latest_success else None,
                error_code=latest.get("error_code") if latest else None,
                next_refresh_at=(started + timedelta(minutes=settings.trends_refresh_minutes)) if started else None,
            )
        )
    return TrendRefreshResponse(status="enabled" if settings.trends_refresh_enabled else "disabled", sources=statuses)


async def _refresh_forever() -> None:
    while True:
        try:
            await refresh_trends()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected trend refresh loop failure")
        await asyncio.sleep(max(1, settings.trends_refresh_minutes) * 60)


def start_refresh_loop() -> asyncio.Task | None:
    global _refresh_task
    if not settings.trends_refresh_enabled:
        return None
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.create_task(_refresh_forever(), name="trend-signal-refresh")
    return _refresh_task


async def stop_refresh_loop() -> None:
    global _refresh_task
    if _refresh_task is None:
        return
    _refresh_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _refresh_task
    _refresh_task = None
