from datetime import UTC, datetime, timedelta

import pytest

from app.models.trends import ConnectorResult, TrendSignal
from app.services.trends.refresh import _record_result, _refresh_lock, refresh_trends


NOW = datetime.now(UTC)


def signal(topic_id: str) -> TrendSignal:
    return TrendSignal(
        topic_id=topic_id,
        label=topic_id.replace("-", " "),
        source="google_news",
        geo="US",
        country_code="US",
        interest_score=80,
        velocity=1,
        rank=1,
        observed_at=NOW,
        fetched_at=NOW,
        expires_at=NOW + timedelta(hours=6),
        raw={},
    )


@pytest.mark.asyncio
async def test_success_replaces_snapshot_and_failure_preserves_it(db):
    old = signal("old-topic")
    await db.trend_signals.insert_one(
        {
            **old.model_dump(),
            "_id": old.signal_id,
            "scope_source": "google_news",
            "scope_geo": "US",
        }
    )
    new = signal("new-topic")
    await _record_result(ConnectorResult(source="google_news", geo="US", status="success", signals=[new]), NOW, 4)
    assert await db.trend_signals.find_one({"_id": old.signal_id}) is None
    assert await db.trend_signals.find_one({"_id": new.signal_id}) is not None

    await _record_result(ConnectorResult(source="google_news", geo="US", status="failed", error_code="timeout"), NOW, 5)
    assert await db.trend_signals.find_one({"_id": new.signal_id}) is not None


@pytest.mark.asyncio
async def test_success_empty_clears_scope_and_is_not_failure(db):
    existing = signal("existing-topic")
    await db.trend_signals.insert_one(
        {
            **existing.model_dump(),
            "_id": existing.signal_id,
            "scope_source": "google_news",
            "scope_geo": "US",
        }
    )
    status = await _record_result(ConnectorResult(source="google_news", geo="US", status="success_empty"), NOW, 1)
    assert status.status == "success_empty"
    assert await db.trend_signals.count_documents({}) == 0


@pytest.mark.asyncio
async def test_overlapping_refresh_is_skipped(db):
    await _refresh_lock.acquire()
    try:
        result = await refresh_trends(["google_news"])
    finally:
        _refresh_lock.release()
    assert result.status == "refresh_in_progress"
