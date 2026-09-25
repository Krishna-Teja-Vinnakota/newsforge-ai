from datetime import UTC, datetime, timedelta

import pytest

from app.core.settings import settings
from app.services.trends.leads import promote_trend_leads
from app.services.trends.refresh import refresh_trends


# Signals expire after six hours, so the fixture time must track the real clock the endpoints use.
NOW = datetime.now(UTC).replace(microsecond=0)


def strong_signal(topic_id: str = "heat-warning", **updates) -> dict:
    values = {
        "_id": f"{topic_id}|weather_alert|US",
        "topic_id": topic_id,
        "label": "Ohio heat warning issued for the region",
        "source": "weather_alert",
        "geo": "US",
        "country_code": "US",
        "interest_score": 95,
        "velocity": 1.5,
        "rank": 1,
        "observed_at": NOW,
        "fetched_at": NOW,
        "expires_at": NOW + timedelta(hours=6),
        "source_url": "https://example.test/alert",
        "raw": {"official": True, "severity": "amber"},
    }
    values.update(updates)
    return values


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "trends_lead_intake_enabled", True)
    monkeypatch.setattr(settings, "trends_lead_min_strength", 0.5)
    monkeypatch.setattr(settings, "trends_lead_max_per_refresh", 5)


@pytest.mark.asyncio
async def test_flag_off_creates_nothing(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_lead_intake_enabled", False)
    await db.trend_signals.insert_one(strong_signal())
    assert await promote_trend_leads(NOW) == []
    assert await db.lead_inbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_strong_uncovered_signal_becomes_a_pending_lead(db):
    await db.trend_signals.insert_one(strong_signal())
    promoted = await promote_trend_leads(NOW)
    assert promoted == ["trend:heat-warning:us"]
    lead = await db.lead_inbox.find_one({"lead_id": "trend:heat-warning:us"})
    assert lead["status"] == "pending"
    assert lead["origin"] == "trend_feed"
    assert lead["topic"] == "trending"
    assert lead["geo"] == "US"
    assert "Ohio heat warning" in lead["headline"]
    assert "weather_alert" in lead["source_context"]
    assert lead["origin_evidence"][0]["source"] == "weather_alert"


@pytest.mark.asyncio
async def test_weak_signal_is_not_promoted(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_lead_min_strength", 0.99)
    await db.trend_signals.insert_one(strong_signal(interest_score=20, velocity=1.0, rank=10))
    assert await promote_trend_leads(NOW) == []
    assert await db.lead_inbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_fully_covered_topic_is_not_promoted(db):
    await db.trend_signals.insert_one(strong_signal())
    await db.articles.insert_many([
        {
            "_id": f"story-{index}",
            "status": "published",
            "published_at": NOW - timedelta(days=1),
            "title": "Ohio heat warning issued for the region",
            "dek": "",
            "topic": "climate",
            "tags": [],
        }
        for index in range(10)
    ])
    assert await promote_trend_leads(NOW) == []
    assert await db.lead_inbox.count_documents({}) == 0


@pytest.mark.asyncio
async def test_rejected_trend_lead_is_never_resurrected(db):
    await db.trend_signals.insert_one(strong_signal())
    await promote_trend_leads(NOW)
    await db.lead_inbox.update_one({"lead_id": "trend:heat-warning:us"}, {"$set": {"status": "rejected"}})
    again = await promote_trend_leads(NOW + timedelta(minutes=5))
    assert again == []
    lead = await db.lead_inbox.find_one({"lead_id": "trend:heat-warning:us"})
    assert lead["status"] == "rejected"


@pytest.mark.asyncio
async def test_manually_created_lead_with_a_colliding_id_is_never_overwritten(db):
    await db.lead_inbox.insert_one(
        {"lead_id": "trend:heat-warning:us", "headline": "Editor's own lead", "status": "pending", "updated_at": NOW}
    )
    await db.trend_signals.insert_one(strong_signal())
    assert await promote_trend_leads(NOW) == []
    lead = await db.lead_inbox.find_one({"lead_id": "trend:heat-warning:us"})
    assert lead["headline"] == "Editor's own lead"
    assert "origin" not in lead


@pytest.mark.asyncio
async def test_promotion_is_bounded_per_refresh(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_lead_max_per_refresh", 2)
    await db.trend_signals.insert_many([strong_signal(topic_id=f"topic-{index}") for index in range(5)])
    promoted = await promote_trend_leads(NOW)
    assert len(promoted) == 2


@pytest.mark.asyncio
async def test_rerunning_promotion_refreshes_a_still_pending_lead_without_duplicating(db):
    await db.trend_signals.insert_one(strong_signal())
    await promote_trend_leads(NOW)
    await db.trend_signals.update_one({"_id": "heat-warning|weather_alert|US"}, {"$set": {"rank": 1, "interest_score": 99}})
    again = await promote_trend_leads(NOW + timedelta(minutes=5))
    assert again == ["trend:heat-warning:us"]
    assert await db.lead_inbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_promote_leads_endpoint_uses_the_existing_cache(db, client, admin_headers):
    await db.trend_signals.insert_one(strong_signal())
    response = await client.post("/api/v1/agents/trends/promote-leads", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["promoted"] == ["trend:heat-warning:us"]
    assert await db.lead_inbox.count_documents({"origin": "trend_feed"}) == 1


@pytest.mark.asyncio
async def test_promoted_leads_appear_in_the_lead_inbox_listing(db, client, admin_headers):
    await db.trend_signals.insert_one(strong_signal())
    await promote_trend_leads(NOW)
    response = await client.get("/api/v1/agents/leads", headers=admin_headers)
    assert response.status_code == 200
    [lead] = response.json()
    assert lead["origin"] == "trend_feed"
    assert lead["id"] == "trend:heat-warning:us"


@pytest.mark.asyncio
async def test_refresh_trends_promotes_leads_automatically_when_enabled(db, monkeypatch):
    # No connectors are exercised here (empty source list); this isolates that refresh_trends
    # invokes promotion against whatever is already cached.
    await db.trend_signals.insert_one(strong_signal())
    result = await refresh_trends([])
    assert result.leads_promoted == ["trend:heat-warning:us"]
