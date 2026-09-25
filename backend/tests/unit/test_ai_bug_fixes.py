"""Regression tests for the backend AI review fixes (fallback visibility, draft consistency, geo, spoofing, workflow)."""

from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from bson import ObjectId
from google import genai

from app.agents import provider as provider_module
from app.agents.provider import VertexGeminiProvider, fallback_used
from app.core.settings import settings
from app.models.agents import AgentName, DekResult, ProductionResult
from app.services.agent_runs import record_run
from app.services.content import html_to_tiptap, reconcile_document, tiptap_to_html
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.image_search import is_relevant_page


class FakeGenAI:
    """Stand-in for google.genai.Client returning a canned response or raising a canned error."""

    response_text: str = "{}"
    error: Exception | None = None

    def __init__(self, **_: Any) -> None:
        self.models = self

    def generate_content(self, **_: Any):
        if FakeGenAI.error:
            raise FakeGenAI.error

        class Response:
            text = FakeGenAI.response_text

        return Response()


@pytest.fixture
def gemini(monkeypatch):
    FakeGenAI.error, FakeGenAI.response_text = None, "{}"
    monkeypatch.setattr(genai, "Client", FakeGenAI)
    monkeypatch.setattr(settings, "llm_provider", "gemini_enterprise")
    monkeypatch.setattr(settings, "google_cloud_project", "test-project")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(provider_module.asyncio, "sleep", _no_sleep)
    return FakeGenAI


async def _no_sleep(_: float) -> None:
    return None


# --- 1. a failed model call is visible instead of looking like a success -------------------------------


@pytest.mark.asyncio
async def test_provider_flags_fallback_when_the_model_call_fails(gemini):
    gemini.error = RuntimeError("400 INVALID_ARGUMENT API key not valid")
    result = await VertexGeminiProvider().generate_json(model="m", prompt="p", schema=DekResult, fallback={"dek": "templated"})
    assert result.dek == "templated"
    assert fallback_used.get() is True


@pytest.mark.asyncio
async def test_provider_clears_fallback_flag_on_success(gemini):
    fallback_used.set(True)
    gemini.response_text = '{"dek": "written by the model"}'
    result = await VertexGeminiProvider().generate_json(model="m", prompt="p", schema=DekResult, fallback={"dek": "templated"})
    assert result.dek == "written by the model"
    assert fallback_used.get() is False


@pytest.mark.asyncio
async def test_provider_retries_quota_errors_before_falling_back(gemini, monkeypatch):
    calls = []

    def flaky(**_: Any):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

        class Response:
            text = '{"dek": "recovered"}'

        return Response()

    monkeypatch.setattr(gemini, "generate_content", staticmethod(flaky))
    result = await VertexGeminiProvider().generate_json(model="m", prompt="p", schema=DekResult, fallback={"dek": "templated"})
    assert result.dek == "recovered" and len(calls) == 3


@pytest.mark.asyncio
async def test_record_run_reports_and_persists_used_fallback(db):
    async def runner():
        fallback_used.set(True)
        return DekResult(dek="templated")

    run = await record_run(AgentName.DEK, "mock", "dek_v1", {}, runner)
    assert run.used_fallback is True
    stored = await db.agent_runs.find_one({"_id": ObjectId(run.id)})
    assert stored["used_fallback"] is True

    async def clean_runner():
        return DekResult(dek="model text")

    clean = await record_run(AgentName.DEK, "mock", "dek_v1", {}, clean_runner)
    assert clean.used_fallback is False


@pytest.mark.asyncio
async def test_agent_run_endpoint_exposes_used_fallback(client, admin_headers):
    response = await client.post("/api/v1/agents/dek", headers=admin_headers, json={"title": "A valid headline", "mode": "generate"})
    assert response.status_code == 200
    assert response.json()["used_fallback"] is True  # the mock provider only ever returns fallbacks


# --- 2. html and Tiptap JSON always describe the same story -------------------------------------------------


def test_html_to_tiptap_and_back_round_trips_supported_markup():
    html = '<h2>Budget</h2><p>The <strong>council</strong> voted <em>7-2</em> on <a href="https://example.test/a">Tuesday</a>.</p><ul><li><p>One</p></li></ul>'
    document = html_to_tiptap(html)
    assert document["type"] == "doc"
    assert document["content"][0] == {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Budget"}]}
    paragraph = document["content"][1]["content"]
    assert {"type": "text", "text": "council", "marks": [{"type": "bold"}]} in paragraph
    assert tiptap_to_html(document) == html


def test_reconcile_derives_json_from_html_instead_of_using_a_stale_fallback():
    payload = {"content_html": "<h2>Real heading</h2><p>Real body.</p>"}
    reconcile_document(payload)
    headings = [node["content"][0]["text"] for node in payload["content_json"]["content"] if node["type"] == "heading"]
    assert headings == ["Real heading"]


@pytest.mark.asyncio
async def test_provider_keeps_html_and_json_consistent_when_model_omits_content_json(gemini):
    gemini.response_text = (
        '{"title": "T headline", "dek": "D", "content_html": "<h2>Model heading</h2><p>Model body.</p>",'
        ' "reporter_brief": {"background": "b"}, "social_posts": ["s"], "push_notification": "p"}'
    )
    fallback = {
        "title": "T headline", "dek": "fallback dek", "content_html": "<p>fallback</p>", "reporter_brief": {"background": "fb"},
        "content_json": {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Details still to verify"}]}]},
        "social_posts": ["x"], "push_notification": "fb", "provenance": [],
    }
    result = await VertexGeminiProvider().generate_json(model="m", prompt="p", schema=ProductionResult, fallback=fallback)
    assert result.content_html == "<h2>Model heading</h2><p>Model body.</p>"
    assert "Details still to verify" not in str(result.content_json)
    assert "Model heading" in str(result.content_json)


# --- 3. reader engagement reaches leads carrying a geography -------------------------------------------------


@pytest.mark.asyncio
async def test_lead_sourced_draft_inherits_the_leads_geo(client, db, admin_headers):
    await db.lead_inbox.insert_one({"lead_id": "geo-1", "headline": "Council approves transit plan", "topic": "local", "geo": "US", "status": "pending"})
    response = await client.post(
        "/api/v1/agents/produce", headers=admin_headers,
        json={"headline": "Council approves transit plan", "topic": "local", "context": "Vote was 7-2.", "source_lead_id": "geo-1"},
    )
    assert response.status_code == 200
    article = await db.articles.find_one({"source_lead_id": "geo-1"})
    assert article["geo"] == "US"


@pytest.mark.asyncio
async def test_selection_uses_the_topic_global_signal_when_no_geo_signal_exists(client, db, admin_headers):
    await db.ranking_signals.insert_one({"_id": "local|global", "topic": "local", "geo": "global", "weight_delta": 0.05})
    await db.lead_inbox.insert_one({"lead_id": "geo-2", "headline": "Council approves transit plan today", "topic": "local", "geo": "US", "status": "pending"})
    response = await client.post("/api/v1/agents/selection/run", headers=admin_headers, json={"leads": []})
    ranked = response.json()["output"]["ranked"]
    assert [item["learned_weight_delta"] for item in ranked if item["lead_id"] == "geo-2"] == [0.05]


@pytest.mark.asyncio
async def test_exact_geo_signal_wins_over_the_global_fallback(client, db, admin_headers):
    await db.ranking_signals.insert_many(
        [{"_id": "local|global", "weight_delta": 0.05}, {"_id": "local|US", "weight_delta": -0.02}]
    )
    await db.lead_inbox.insert_one({"lead_id": "geo-3", "headline": "Council approves transit plan today", "topic": "local", "geo": "US", "status": "pending"})
    response = await client.post("/api/v1/agents/selection/run", headers=admin_headers, json={"leads": []})
    assert [item["learned_weight_delta"] for item in response.json()["output"]["ranked"] if item["lead_id"] == "geo-3"] == [-0.02]


# --- 4. views and likes cannot be inflated by dropping the visitor header ------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def fresh_rate_limits(client):
    """The app (and its in-memory limiter) is a process singleton, so isolate each test's counters."""
    await client.get("/api/v1/health")  # builds the middleware stack
    layer = client._transport.app.middleware_stack
    while layer is not None:
        if isinstance(layer, RateLimitMiddleware):
            layer._requests.clear()
        layer = getattr(layer, "app", None)


async def _published_article(db, admin_user) -> str:
    # The real app creates these unique indexes at startup; the in-memory test database does not.
    for name in ("view_events", "feedback_events"):
        await db[name].create_index([("article_id", 1), ("actor_key", 1), ("day", 1)], unique=True)
    await db.article_daily_metrics.create_index([("article_id", 1), ("day", 1)], unique=True)
    now = datetime.now(UTC)
    inserted = await db.articles.insert_one(
        {
            "slug": "published-story", "status": "published", "title": "Published story", "dek": "d", "content_json": {}, "content_html": "<p>x</p>",
            "topic": "local", "tags": [], "hero_media_id": None, "creator_id": admin_user["_id"], "created_at": now, "updated_at": now,
            "published_at": now, "metrics": {"views": 0, "likes": 0, "dislikes": 0, "engagement_ratio": 0, "popularity_score": 0},
        }
    )
    return str(inserted.inserted_id)


@pytest.mark.asyncio
async def test_repeated_views_without_a_visitor_header_count_once(client, db, admin_user):
    article_id = await _published_article(db, admin_user)
    for _ in range(3):
        response = await client.post(f"/api/v1/articles/{article_id}/view")
    assert response.json()["metrics"]["views"] == 1
    daily = await db.article_daily_metrics.find_one({"article_id": ObjectId(article_id)})
    assert daily["views"] == 1


@pytest.mark.asyncio
async def test_repeated_likes_without_a_visitor_header_count_once(client, db, admin_user):
    article_id = await _published_article(db, admin_user)
    for _ in range(3):
        response = await client.post(f"/api/v1/articles/{article_id}/feedback", json={"action": "like"})
    assert response.json()["metrics"]["likes"] == 1
    daily = await db.article_daily_metrics.find_one({"article_id": ObjectId(article_id)})
    assert daily["likes"] == 1


@pytest.mark.asyncio
async def test_distinct_visitor_headers_still_count_separately(client, db, admin_user):
    article_id = await _published_article(db, admin_user)
    for visitor in ("a", "b", "c"):
        response = await client.post(f"/api/v1/articles/{article_id}/view", headers={"X-NewsForge-Visitor": visitor})
    assert response.json()["metrics"]["views"] == 3


@pytest.mark.asyncio
async def test_real_reader_feedback_updates_signal_and_reranks_open_leads(client, db, admin_user):
    article_id = await _published_article(db, admin_user)
    await db.lead_inbox.insert_one(
        {
            "lead_id": "local-follow-up",
            "headline": "Local follow-up story for engaged readers",
            "topic": "local",
            "geo": "global",
            "status": "pending",
        }
    )
    await client.post(
        f"/api/v1/articles/{article_id}/view", headers={"X-NewsForge-Visitor": "reader-one"}
    )
    response = await client.post(
        f"/api/v1/articles/{article_id}/feedback",
        headers={"X-NewsForge-Visitor": "reader-one"},
        json={"action": "like"},
    )
    assert response.status_code == 200
    signal = await db.ranking_signals.find_one({"_id": "local|global"})
    lead = await db.lead_inbox.find_one({"lead_id": "local-follow-up"})
    assert signal["weight_delta"] > 0
    assert lead["learned_weight_delta"] == signal["weight_delta"]
    assert lead["current_rank"] == 1


@pytest.mark.asyncio
async def test_recalculate_is_idempotent_and_reranks_leads(client, db, admin_headers, admin_user):
    article_id = await _published_article(db, admin_user)
    await db.articles.update_one(
        {"_id": ObjectId(article_id)},
        {"$set": {"metrics.views": 100, "metrics.likes": 10, "metrics.engagement_ratio": 1.0}},
    )
    await db.lead_inbox.insert_one(
        {
            "lead_id": "recalc-lead",
            "headline": "Local story informed by audience demand",
            "topic": "local",
            "geo": "global",
            "status": "pending",
        }
    )
    endpoint = "/api/v1/agents/telemetry/recalculate"
    first = await client.post(endpoint, headers=admin_headers, json={"article_id": article_id})
    before = await db.ranking_signals.find_one({"_id": "local|global"})
    second = await client.post(endpoint, headers=admin_headers, json={"article_id": article_id})
    after = await db.ranking_signals.find_one({"_id": "local|global"})
    assert first.status_code == second.status_code == 200
    assert first.json()["output"]["affected_leads_count"] == 1
    assert before["weight_delta"] == after["weight_delta"]
    assert before["sample_size"] == after["sample_size"] == 100
    assert await db.ranking_signal_contributions.count_documents({"_id": f"article:{article_id}"}) == 1


@pytest.mark.asyncio
async def test_generic_public_events_feed_ranking_and_rerank(client, db):
    await db.lead_inbox.insert_one(
        {
            "lead_id": "event-lead",
            "headline": "Ohio technology readers show demand",
            "topic": "technology",
            "geo": "Ohio",
            "status": "pending",
        }
    )
    response = await client.post(
        "/api/v1/telemetry/event",
        headers={"X-NewsForge-Visitor": "event-reader"},
        json={"topic": "technology", "geo": "Ohio", "event_type": "save", "platform": "web"},
    )
    assert response.status_code == 202
    signal = await db.ranking_signals.find_one({"_id": "technology|Ohio"})
    lead = await db.lead_inbox.find_one({"lead_id": "event-lead"})
    assert signal["weight_delta"] > 0
    assert lead["learned_weight_delta"] == signal["weight_delta"]


@pytest.mark.asyncio
async def test_reader_writes_are_rate_limited_per_address(client, db, admin_user):
    article_id = await _published_article(db, admin_user)
    statuses = [(await client.post(f"/api/v1/articles/{article_id}/view", headers={"X-NewsForge-Visitor": str(index)})).status_code for index in range(35)]
    assert statuses[:30] == [200] * 30
    assert 429 in statuses[30:]


@pytest.mark.asyncio
async def test_browsing_agent_data_does_not_consume_the_ai_rate_limit(client, admin_headers):
    statuses = [(await client.get("/api/v1/agents/leads", headers=admin_headers)).status_code for _ in range(15)]
    assert statuses == [200] * 15


# --- 5. the workflow really publishes, and does not fabricate telemetry --------------------------------------


@pytest.mark.asyncio
async def test_workflow_publishes_a_real_article_and_leaves_ranking_signals_alone(client, db, admin_headers):
    lead = {"id": "wf-lead", "headline": "Regional airport to add 12 new routes next spring", "topic": "business", "geo": "US", "source_context": "Airport board approved the plan on Monday."}
    await db.lead_inbox.insert_one({"lead_id": "wf-lead", **{key: value for key, value in lead.items() if key != "id"}, "status": "pending"})
    started = await client.post("/api/v1/workflow/start", headers=admin_headers, json={"lead": lead})
    assert started.status_code == 200 and started.json()["pending_interrupts"] == ["approval_gate"]
    thread_id = started.json()["thread_id"]

    drafted = await client.post(f"/api/v1/workflow/{thread_id}/resume", headers=admin_headers, json={"approval_status": "approved"})
    assert drafted.json()["pending_interrupts"] == ["editorial_gate"]
    assert "Airport board approved the plan on Monday." in drafted.json()["state"]["generated_draft"]["content_html"]

    finished = await client.post(f"/api/v1/workflow/{thread_id}/resume", headers=admin_headers, json={"editorial_status": "approved"})
    assert finished.status_code == 200 and finished.json()["current_node"] == "telemetry"

    article = await db.articles.find_one({"source_lead_id": "wf-lead"})
    assert article is not None and article["status"] == "published" and article["published_at"] is not None
    assert article["geo"] == "US"
    assert finished.json()["state"]["article_id"] == str(article["_id"])
    assert await db.editorial_index.count_documents({"article_id": article["_id"]}) == 1
    assert (await db.lead_inbox.find_one({"lead_id": "wf-lead"}))["status"] == "published"
    assert await db.ranking_signals.count_documents({}) == 0

    public = await client.get(f"/api/v1/articles/{article['slug']}")
    assert public.status_code == 200


@pytest.mark.asyncio
async def test_rejected_workflow_lead_creates_no_article(client, db, admin_headers):
    lead = {"id": "wf-reject", "headline": "Something the desk will decline", "topic": "local", "geo": "US"}
    started = await client.post("/api/v1/workflow/start", headers=admin_headers, json={"lead": lead})
    thread_id = started.json()["thread_id"]
    await client.post(f"/api/v1/workflow/{thread_id}/resume", headers=admin_headers, json={"approval_status": "rejected"})
    assert await db.articles.count_documents({}) == 0


# --- smaller fixes -----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("article_id", ["not-an-id", "0" * 24])
async def test_telemetry_run_rejects_unknown_or_malformed_article_ids_cleanly(client, admin_headers, article_id):
    response = await client.post("/api/v1/agents/telemetry/recalculate", headers=admin_headers, json={"article_id": article_id})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_telemetry_agent_overwrites_a_model_supplied_article_id(db, monkeypatch, admin_user):
    from app.agents import telemetry_agent
    from app.agents.provider import GeminiProvider
    from app.models.agents import TelemetryResult

    article_id = await _published_article(db, admin_user)

    class WrongIdProvider(GeminiProvider):
        name = "wrong-id"

        async def generate_json(self, *, model, prompt, schema, fallback):
            return TelemetryResult(article_id="art_telemetry_001", topic="made-up", engagement_score=0.5, popularity_rank_hint=0, weight_delta=0.0, insight="i", seo_recommendations=[])

    monkeypatch.setattr(telemetry_agent, "get_provider", lambda: WrongIdProvider())
    result = await telemetry_agent.run_telemetry(article_id)
    assert result.article_id == article_id and result.topic == "local"


@pytest.mark.asyncio
async def test_simulation_reranks_only_open_leads(client, db, admin_headers):
    await db.lead_inbox.insert_many(
        [
            {"lead_id": f"open-{index}", "headline": f"Open lead number {index}", "topic": "technology", "geo": "global", "status": "pending"}
            for index in range(3)
        ]
        + [
            {"lead_id": "done-rejected", "headline": "Rejected lead", "topic": "technology", "geo": "global", "status": "rejected"},
            {"lead_id": "done-published", "headline": "Published lead", "topic": "technology", "geo": "global", "status": "published"},
        ]
    )
    response = await client.post("/api/v1/telemetry/simulate", headers=admin_headers, json={"topic": "technology", "geo": "global", "sample_size": 100})
    assert response.status_code == 200
    assert response.json()["affected_leads_count"] == 3


def test_hero_image_requires_a_title_that_shares_a_real_word_with_the_headline():
    headline = "City council approves $40 million transit expansion"
    assert is_relevant_page(headline, "Bus rapid transit")
    assert is_relevant_page(headline, "City council")
    assert not is_relevant_page(headline, "Microsoft Office")
    assert not is_relevant_page(headline, "The and With")
