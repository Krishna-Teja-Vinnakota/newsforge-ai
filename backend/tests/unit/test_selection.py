from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.agents import selection_agent
from app.agents.selection_agent import _clamp_priority_score, run_selection
from app.models.agents import LeadInput
from app.core.settings import settings


@pytest.mark.asyncio
async def test_selection_is_deterministic_and_uses_requested_tie_breaks(db):
    now = datetime.now(UTC)
    await db.lead_inbox.insert_many([
        {"lead_id": "alpha", "headline": "Alpha", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 3, "updated_at": now},
        {"lead_id": "bravo", "headline": "Bravo", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 2, "updated_at": now},
        {"lead_id": "newer", "headline": "Newer", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 1, "updated_at": now + timedelta(seconds=1)},
    ])
    leads = [LeadInput(id=item, headline=item.title(), topic="technology", geo="global") for item in ["alpha", "bravo", "newer"]]
    result = await run_selection(leads)
    assert [item.lead_id for item in result.ranked] == ["newer", "alpha", "bravo"]
    assert [item.current_rank for item in result.ranked] == [1, 2, 3]
    assert all(item.final_score == round(item.base_score + item.learned_weight_delta, 4) for item in result.ranked)


def test_priority_scores_are_strictly_clamped():
    assert _clamp_priority_score(-5) == 0.0
    assert _clamp_priority_score(0.123456) == 0.1235
    assert _clamp_priority_score(5) == 1.0


@pytest.mark.asyncio
async def test_trend_scoring_is_cached_audited_and_persisted(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_scoring_enabled", True)
    monkeypatch.setattr(settings, "trends_refresh_enabled", False)
    now = datetime.now(UTC)
    await db.trend_signals.insert_one({
        "_id": "heat-warning|weather_alert|US", "topic_id": "heat-warning",
        "label": "Ohio heat warning", "source": "weather_alert", "geo": "US", "country_code": "US",
        "interest_score": 95, "velocity": 1.5, "rank": 1, "observed_at": now, "fetched_at": now,
        "expires_at": now + timedelta(hours=6), "source_url": "https://example.test/alert",
        "raw": {"official": True, "severity": "amber"},
    })
    lead = LeadInput(id="heat", headline="Ohio heat warning issued", topic="climate", geo="Ohio")
    result = await run_selection([lead])
    ranked = result.ranked[0]
    stored = await db.lead_inbox.find_one({"lead_id": "heat"})
    assert ranked.final_score == round(ranked.base_score + ranked.learned_weight_delta + ranked.trend_boost + ranked.coverage_adjustment, 4)
    assert ranked.trend_boost > 0
    assert stored["final_score"] == ranked.final_score
    assert stored["score_audit"]["scoring_version"] == "selection_v2_trends_2"
    assert stored["trend_evidence"][0]["matched_tokens"]


@pytest.mark.asyncio
async def test_shadow_mode_leaves_final_score_and_top_level_trend_fields_unchanged(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_scoring_enabled", False)
    monkeypatch.setattr(settings, "trends_refresh_enabled", True)
    now = datetime.now(UTC)
    await db.trend_signals.insert_one({
        "_id": "heat-warning|weather_alert|US", "topic_id": "heat-warning",
        "label": "Ohio heat warning", "source": "weather_alert", "geo": "US", "country_code": "US",
        "interest_score": 95, "velocity": 1.5, "rank": 1, "observed_at": now, "fetched_at": now,
        "expires_at": now + timedelta(hours=6), "raw": {"official": True},
    })
    result = await run_selection([LeadInput(id="shadow", headline="Ohio heat warning issued", topic="climate", geo="Ohio")])
    ranked = result.ranked[0]
    stored = await db.lead_inbox.find_one({"lead_id": "shadow"})
    assert ranked.final_score == round(ranked.base_score + ranked.learned_weight_delta, 4)
    assert stored["score_audit"]["shadow_trend_boost"] > 0
    assert "trend_boost" not in stored


@pytest.mark.asyncio
async def test_selection_api_preserves_and_returns_trend_audit(db, client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "trends_scoring_enabled", True)
    monkeypatch.setattr(settings, "trends_refresh_enabled", False)
    now = datetime.now(UTC)
    await db.trend_signals.insert_one(
        {
            "_id": "transit-budget|government|US",
            "topic_id": "transit-budget",
            "label": "Ohio transit budget",
            "source": "government",
            "geo": "US",
            "country_code": "US",
            "interest_score": 90,
            "velocity": 1.2,
            "rank": 2,
            "observed_at": now,
            "fetched_at": now,
            "expires_at": now + timedelta(hours=6),
            "raw": {"official": True},
        }
    )
    response = await client.post(
        "/api/v1/agents/selection/run",
        headers=admin_headers,
        json={"leads": [{"id": "transit", "headline": "Ohio transit budget approved", "topic": "local", "geo": "Ohio"}]},
    )
    assert response.status_code == 200
    ranked = response.json()["output"]["ranked"][0]
    stored = await db.lead_inbox.find_one({"lead_id": "transit"})
    assert stored["final_score"] == ranked["final_score"]

    inbox = await client.get("/api/v1/agents/leads", headers=admin_headers)
    assert inbox.status_code == 200
    returned = inbox.json()[0]
    assert returned["trend_boost"] > 0
    assert returned["trend_evidence"][0]["source"] == "government"
    assert returned["score_audit"]["scoring_version"] == "selection_v2_trends_2"


def heat_signal(now: datetime) -> dict:
    return {
        "_id": "heat-warning|weather_alert|US", "topic_id": "heat-warning",
        "label": "Ohio heat warning", "source": "weather_alert", "geo": "US", "country_code": "US",
        "interest_score": 95, "velocity": 1.5, "rank": 1, "observed_at": now, "fetched_at": now,
        "expires_at": now + timedelta(hours=6), "raw": {"official": True, "severity": "amber"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(("refresh", "scoring"), [(False, False), (False, True), (True, False), (True, True)])
async def test_selection_never_makes_outbound_requests(db, monkeypatch, refresh, scoring):
    monkeypatch.setattr(settings, "trends_refresh_enabled", refresh)
    monkeypatch.setattr(settings, "trends_scoring_enabled", scoring)

    def forbid(*args, **kwargs):
        raise AssertionError("ranking attempted an outbound HTTP request")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid)
    monkeypatch.setattr(httpx.Client, "send", forbid)
    monkeypatch.setattr("app.services.trends.refresh.refresh_trends", forbid)
    await db.trend_signals.insert_one(heat_signal(datetime.now(UTC)))
    result = await run_selection([LeadInput(id="heat", headline="Ohio heat warning issued", topic="climate", geo="Ohio")])
    assert len(result.ranked) == 1


@pytest.mark.asyncio
async def test_trend_data_is_not_read_when_both_flags_are_off(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_refresh_enabled", False)
    monkeypatch.setattr(settings, "trends_scoring_enabled", False)

    async def forbid(*args, **kwargs):
        raise AssertionError("trend signals were loaded while both flags are off")

    monkeypatch.setattr(selection_agent, "_load_trend_signals", forbid)
    await db.trend_signals.insert_one(heat_signal(datetime.now(UTC)))
    result = await run_selection([LeadInput(id="heat", headline="Ohio heat warning issued", topic="climate", geo="Ohio")])
    ranked = result.ranked[0]
    assert ranked.trend_boost == 0 and ranked.coverage_adjustment == 0
    assert ranked.final_score == round(ranked.base_score + ranked.learned_weight_delta, 4)
    stored = await db.lead_inbox.find_one({"lead_id": "heat"})
    assert "trend_boost" not in stored and "scoring_version" not in stored["score_audit"]


@pytest.mark.asyncio
async def test_lead_adjustment_is_independent_of_batch_composition(db, monkeypatch):
    monkeypatch.setattr(settings, "trends_scoring_enabled", True)
    monkeypatch.setattr(settings, "trends_refresh_enabled", False)
    await db.trend_signals.insert_one(heat_signal(datetime.now(UTC)))
    target = LeadInput(id="heat", headline="Ohio heat warning issued", topic="climate", geo="Ohio")
    others = [LeadInput(id=f"other-{index}", headline=f"Unrelated markets story {index}", topic="business", geo="global") for index in range(3)]
    alone = (await run_selection([target])).ranked[0]
    together = {item.lead_id: item for item in (await run_selection([target, *others])).ranked}["heat"]
    assert alone.trend_boost > 0
    assert together.trend_boost == pytest.approx(alone.trend_boost, abs=1e-3)
    assert together.coverage_adjustment == pytest.approx(alone.coverage_adjustment, abs=1e-3)


@pytest.mark.asyncio
async def test_telemetry_rerank_preserves_trend_fields(db, client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "trends_scoring_enabled", True)
    monkeypatch.setattr(settings, "trends_refresh_enabled", False)
    await db.trend_signals.insert_one(heat_signal(datetime.now(UTC)))
    await run_selection([LeadInput(id="heat", headline="Ohio heat warning issued", topic="climate", geo="Ohio")])
    assert (await db.lead_inbox.find_one({"lead_id": "heat"}))["trend_boost"] > 0

    response = await client.post(
        "/api/v1/telemetry/simulate",
        headers=admin_headers,
        json={"topic": "climate", "geo": "Ohio", "sample_size": 100},
    )
    assert response.status_code == 200
    stored = await db.lead_inbox.find_one({"lead_id": "heat"})
    assert stored["trend_boost"] > 0
    assert stored["trend_evidence"] and stored["score_audit"]["scoring_version"] == "selection_v2_trends_2"
    assert stored["learned_weight_delta"] != 0
    assert stored["final_score"] == round(
        stored["base_score"] + stored["learned_weight_delta"] + stored["trend_boost"] + stored["coverage_adjustment"], 4
    )
