from __future__ import annotations

import asyncio
import re
import statistics
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.settings import settings
from app.models.trends import ConnectorResult, TrendSignal

MAX_RESPONSE_BYTES = 1_000_000
RETRYABLE_STATUS = {429, 502, 503}
USER_AGENT = "NewsForge/0.1 trend-cache"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:100] or "untitled"


def _datetime(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class ConnectorFetchError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def _get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(3):
        try:
            response = await client.get(url, **kwargs)
        except httpx.TimeoutException as error:
            raise ConnectorFetchError("timeout") from error
        except httpx.HTTPError as error:
            raise ConnectorFetchError("transport_error") from error
        if response.status_code in RETRYABLE_STATUS and attempt < 2:
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        if response.status_code in RETRYABLE_STATUS:
            raise ConnectorFetchError("rate_limited" if response.status_code == 429 else "upstream_unavailable")
        if response.is_error:
            raise ConnectorFetchError("upstream_error")
        if (
            int(response.headers.get("content-length", 0) or 0) > MAX_RESPONSE_BYTES
            or len(response.content) > MAX_RESPONSE_BYTES
        ):
            raise ConnectorFetchError("response_too_large")
        return response
    raise ConnectorFetchError("upstream_error")


class TrendConnector(ABC):
    name: str
    signal_source: str
    lifetime: timedelta

    def result(self, geo: str, signals: list[TrendSignal]) -> ConnectorResult:
        limited = signals[: settings.trends_max_signals_per_source]
        return ConnectorResult(
            source=self.name, geo=geo, status="success" if limited else "success_empty", signals=limited
        )

    @abstractmethod
    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        raise NotImplementedError


class GoogleNewsConnector(TrendConnector):
    name = "google_news"
    signal_source = "google_news"
    lifetime = timedelta(hours=6)

    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        response = await _get(
            client,
            "https://news.google.com/rss",
            params={"hl": "en-US", "gl": geo, "ceid": f"{geo}:en"},
        )
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise ConnectorFetchError("parse_error") from error
        signals: list[TrendSignal] = []
        seen: set[str] = set()
        for rank, item in enumerate(root.findall(".//item"), start=1):
            raw_title = (item.findtext("title") or "").strip()
            label = re.sub(r"\s+[-–—]\s+[^-–—]+$", "", raw_title).strip()[:180]
            topic_id = _slug(label)
            if not label or topic_id in seen:
                continue
            seen.add(topic_id)
            observed = _datetime(item.findtext("pubDate"), now)
            signals.append(
                TrendSignal(
                    topic_id=topic_id,
                    label=label,
                    source=self.signal_source,
                    geo=geo,
                    country_code=geo,
                    interest_score=max(20.0, 100.0 - (rank - 1) * 2.0),
                    velocity=1.0,
                    rank=rank,
                    observed_at=observed,
                    fetched_at=now,
                    expires_at=observed + self.lifetime,
                    source_url=item.findtext("link"),
                    raw={"via": "rss"},
                )
            )
        return self.result(geo, signals)


class WeatherConnector(TrendConnector):
    name = "weather"
    signal_source = "weather_alert"
    lifetime = timedelta(hours=6)

    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        if geo.upper() not in {"US", "GB", "UK"}:
            return self.result(geo, [])
        if geo.upper() == "US":
            response = await _get(
                client,
                "https://api.weather.gov/alerts/active",
                params={"status": "actual", "message_type": "alert"},
                headers={"Accept": "application/geo+json"},
            )
            try:
                features = response.json().get("features") or []
            except ValueError as error:
                raise ConnectorFetchError("parse_error") from error
            signals: list[TrendSignal] = []
            scores = {"Extreme": 100.0, "Severe": 90.0, "Moderate": 75.0}
            severities = {"Extreme": "red", "Severe": "amber", "Moderate": "yellow"}
            for rank, feature in enumerate(features, start=1):
                props = feature.get("properties") or {}
                severity = str(props.get("severity") or "Unknown")
                label = str(props.get("headline") or props.get("event") or "").strip()[:180]
                if severity not in scores or not label:
                    continue
                observed = _datetime(props.get("sent") or props.get("effective") or props.get("onset"), now)
                signals.append(
                    TrendSignal(
                        topic_id=_slug(label),
                        label=label,
                        source=self.signal_source,
                        geo=geo,
                        country_code="US",
                        interest_score=scores[severity],
                        velocity=1.4 if severity in {"Extreme", "Severe"} else 1.0,
                        rank=rank,
                        observed_at=observed,
                        fetched_at=now,
                        expires_at=min(
                            _datetime(props.get("expires"), observed + self.lifetime), observed + self.lifetime
                        ),
                        source_url=props.get("@id") or props.get("id"),
                        raw={
                            "official": True,
                            "severity": severities[severity],
                            "hazard": props.get("event"),
                            "area": props.get("areaDesc"),
                            "description": str(props.get("description") or "")[:500],
                        },
                    )
                )
            return self.result(geo, signals)

        response = await _get(
            client, "https://environment.data.gov.uk/flood-monitoring/id/floods", params={"min-severity": 3}
        )
        try:
            items = response.json().get("items") or []
        except ValueError as error:
            raise ConnectorFetchError("parse_error") from error
        scores = {1: 100.0, 2: 88.0, 3: 72.0}
        colors = {1: "red", 2: "amber", 3: "yellow"}
        signals = []
        for rank, item in enumerate(items, start=1):
            level = int(item.get("severityLevel") or 99)
            if level not in scores:
                continue
            label = (
                f"{item.get('severity', 'Flood alert')}: {item.get('description') or item.get('eaAreaName') or 'UK'}"[
                    :180
                ]
            )
            signals.append(
                TrendSignal(
                    topic_id=_slug(label),
                    label=label,
                    source=self.signal_source,
                    geo="GB",
                    country_code="GB",
                    interest_score=scores[level],
                    velocity=1.4 if level <= 2 else 1.0,
                    rank=rank,
                    observed_at=now,
                    fetched_at=now,
                    expires_at=now + self.lifetime,
                    source_url=item.get("@id"),
                    raw={
                        "official": True,
                        "severity": colors[level],
                        "hazard": "flood",
                        "area": item.get("eaAreaName"),
                    },
                )
            )
        return self.result(geo, signals)


class GovernmentConnector(TrendConnector):
    name = "government"
    signal_source = "government"
    lifetime = timedelta(hours=12)

    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        signals: list[TrendSignal] = []
        if geo.upper() in {"GB", "UK"}:
            response = await _get(
                client,
                "https://www.gov.uk/api/search.json",
                params={
                    "filter_format": "news_story",
                    "count": settings.trends_max_signals_per_source,
                    "order": "-public_timestamp",
                },
            )
            try:
                results = response.json().get("results") or []
            except ValueError as error:
                raise ConnectorFetchError("parse_error") from error
            for rank, item in enumerate(results, start=1):
                label = str(item.get("title") or "").strip()[:180]
                if not label:
                    continue
                observed = _datetime(item.get("public_timestamp"), now)
                signals.append(
                    TrendSignal(
                        topic_id=_slug(label),
                        label=label,
                        source=self.signal_source,
                        geo="GB",
                        country_code="GB",
                        interest_score=max(40.0, 90.0 - rank),
                        velocity=1.0,
                        rank=rank,
                        observed_at=observed,
                        fetched_at=now,
                        expires_at=observed + self.lifetime,
                        source_url=f"https://www.gov.uk{item.get('link', '')}",
                        raw={"official": True},
                    )
                )
            return self.result(geo, signals)

        response = await _get(
            client,
            "https://www.federalregister.gov/api/v1/documents.json",
            params={
                "per_page": settings.trends_max_signals_per_source,
                "order": "newest",
                "conditions[type][]": ["RULE", "PRORULE", "PRESDOCU"],
            },
        )
        try:
            results = response.json().get("results") or []
        except ValueError as error:
            raise ConnectorFetchError("parse_error") from error
        for rank, item in enumerate(results, start=1):
            label = str(item.get("title") or "").strip()[:180]
            if not label:
                continue
            observed = _datetime(item.get("publication_date"), now)
            signals.append(
                TrendSignal(
                    topic_id=_slug(label),
                    label=label,
                    source=self.signal_source,
                    geo=geo,
                    country_code=geo,
                    interest_score=max(40.0, 90.0 - rank),
                    velocity=1.0,
                    rank=rank,
                    observed_at=observed,
                    fetched_at=now,
                    expires_at=observed + self.lifetime,
                    source_url=item.get("html_url"),
                    raw={"official": True, "document_type": item.get("type")},
                )
            )
        return self.result(geo, signals)


class WikipediaConnector(TrendConnector):
    name = "wikipedia"
    signal_source = "wikipedia"
    lifetime = timedelta(hours=24)

    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        project = {"US": "en.wikipedia.org", "GB": "en.wikipedia.org", "IN": "en.wikipedia.org"}.get(
            geo.upper(), "en.wikipedia.org"
        )
        day = now - timedelta(days=1)
        response = await _get(
            client,
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/all-access/{day:%Y/%m/%d}",
        )
        try:
            articles = (response.json().get("items") or [{}])[0].get("articles") or []
        except (ValueError, AttributeError, IndexError) as error:
            raise ConnectorFetchError("parse_error") from error
        signals = []
        skipped = {"main_page", "special:search", "-"}
        for rank, item in enumerate(articles, start=1):
            article = str(item.get("article") or "")
            if article.casefold() in skipped or article.startswith("Special:"):
                continue
            label = article.replace("_", " ")[:180]
            views = float(item.get("views") or 0)
            signals.append(
                TrendSignal(
                    topic_id=_slug(label),
                    label=label,
                    source=self.signal_source,
                    geo="global",
                    country_code=None,
                    interest_score=min(100.0, 30.0 + 15.0 * math_log10(max(1.0, views))),
                    velocity=1.0,
                    rank=rank,
                    observed_at=now,
                    fetched_at=now,
                    expires_at=now + self.lifetime,
                    source_url=f"https://{project}/wiki/{article}",
                    raw={"views": int(views)},
                )
            )
        return self.result(geo, signals)


def math_log10(value: float) -> float:
    # Kept local so connector parsing remains dependency-free.
    import math

    return math.log10(value)


async def enrich_with_gdelt(
    signals: list[TrendSignal], geo: str, client: httpx.AsyncClient, now: datetime
) -> tuple[ConnectorResult, dict[str, float]]:
    """Measure coverage velocity without creating standalone GDELT signals."""
    if not signals:
        return ConnectorResult(source="gdelt", geo=geo, status="success_empty", processed_count=0), {}
    updates: dict[str, float] = {}
    for signal in sorted(signals, key=lambda item: (-item.interest_score, item.signal_id))[:10]:
        response = await _get(
            client,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": f'"{signal.label[:120]}"',
                "mode": "timelinevol",
                "format": "json",
                "timespan": "1d",
            },
        )
        try:
            timelines = response.json().get("timeline") or []
            values = (
                [float(point.get("value") or 0.0) for point in (timelines[0].get("data") or [])] if timelines else []
            )
        except (ValueError, TypeError, AttributeError, IndexError) as error:
            raise ConnectorFetchError("parse_error") from error
        if len(values) < 4:
            continue
        split = max(1, len(values) // 4)
        recent = statistics.fmean(values[-split:])
        baseline = statistics.fmean(values[:-split]) if values[:-split] else 0.0
        velocity = 2.0 if baseline <= 0 < recent else (1.0 if baseline <= 0 else recent / baseline)
        updates[signal.signal_id] = round(max(0.1, min(5.0, velocity)), 4)
    return (
        ConnectorResult(
            source="gdelt", geo=geo, status="success" if updates else "success_empty", processed_count=len(updates)
        ),
        updates,
    )


class RedditConnector(TrendConnector):
    name = "reddit"
    signal_source = "reddit"
    lifetime = timedelta(hours=6)

    async def fetch(self, geo: str, client: httpx.AsyncClient, now: datetime) -> ConnectorResult:
        subreddits = {"US": "news", "GB": "unitedkingdom", "IN": "india", "AU": "australia", "CA": "canada"}
        subreddit = subreddits.get(geo.upper(), "worldnews")
        response = await _get(
            client,
            f"https://www.reddit.com/r/{subreddit}/hot.json",
            params={"limit": settings.trends_max_signals_per_source, "raw_json": 1},
        )
        try:
            posts = response.json().get("data", {}).get("children", [])
        except ValueError as error:
            raise ConnectorFetchError("parse_error") from error
        signals = []
        for rank, post in enumerate(posts, start=1):
            data = post.get("data") or {}
            label = str(data.get("title") or "").strip()[:180]
            if not label:
                continue
            score = float(data.get("score") or 0)
            observed = datetime.fromtimestamp(float(data.get("created_utc") or now.timestamp()), tz=UTC)
            signals.append(
                TrendSignal(
                    topic_id=_slug(label),
                    label=label,
                    source=self.signal_source,
                    geo=geo,
                    country_code=geo,
                    interest_score=min(100.0, score / 100.0),
                    velocity=1.0,
                    rank=rank,
                    observed_at=observed,
                    fetched_at=now,
                    expires_at=observed + self.lifetime,
                    source_url=f"https://www.reddit.com{data.get('permalink', '')}",
                    raw={"subreddit": subreddit, "score": int(score), "official": False},
                )
            )
        return self.result(geo, signals)


CONNECTORS: dict[str, TrendConnector] = {
    connector.name: connector
    for connector in (
        GoogleNewsConnector(),
        WeatherConnector(),
        GovernmentConnector(),
        WikipediaConnector(),
        RedditConnector(),
    )
}


async def fetch_connector(
    connector: TrendConnector, geo: str, client: httpx.AsyncClient, now: datetime
) -> ConnectorResult:
    try:
        return await connector.fetch(geo, client, now)
    except ConnectorFetchError as error:
        return ConnectorResult(source=connector.name, geo=geo, status="failed", error_code=error.code)
    except Exception:
        return ConnectorResult(source=connector.name, geo=geo, status="failed", error_code="unexpected_error")


def connector_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.trends_connector_timeout_seconds),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, application/xml;q=0.9"},
    )
