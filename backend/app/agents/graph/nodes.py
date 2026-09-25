from datetime import UTC, datetime

from bson import ObjectId

from app.agents.production_agent import PROMPT_VERSION as PRODUCTION_PROMPT_VERSION, run_production
from app.agents.selection_agent import run_selection
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import LeadInput
from app.models.article import ArticleStatus
from app.services.articles import unique_slug
from app.services.content import sanitize_html
from app.services.retrieval import index_published_article

from .state import NewsroomState


def _trace(node: str, status: str = "completed") -> list[dict]:
    return [{"node": node, "status": status, "timestamp": datetime.now(UTC).isoformat()}]


def _lead(state: NewsroomState) -> LeadInput:
    candidate = state["lead_candidate"]
    return LeadInput(
        id=state["lead_id"],
        headline=candidate["headline"],
        topic=candidate.get("topic", "general"),
        geo=candidate.get("geo", "global"),
        source_url=candidate.get("source_url"),
        source_context=candidate.get("source_context"),
    )


async def node_selection(state: NewsroomState) -> dict:
    lead = _lead(state)
    selection = await run_selection([lead])
    result = selection.ranked[0].model_dump(mode="json")
    return {
        "selection_result": result,
        "approval_status": "pending",
        "current_step": "selection",
        "execution_history": _trace("selection"),
    }


async def node_approval_gate(state: NewsroomState) -> dict:
    return {"current_step": "human_approval", "execution_history": _trace("human_approval", "approved" if state.get("approval_status") == "approved" else "rejected")}


async def node_retrieve_and_draft(state: NewsroomState) -> dict:
    lead = _lead(state)
    angle = state.get("selection_result", {}).get("suggested_angle", "")
    # Ground the draft on the reporting supplied with the lead. The model-suggested angle is
    # only guidance, so it is labelled as such and never stands in for the facts.
    context = (lead.source_context or "").strip()
    if angle:
        context = f"{context}\nSuggested angle (guidance, not a source): {angle}".strip()
    draft = await run_production(lead.headline, lead.topic, context, ["web", "social", "newsletter"])
    return {
        "retrieved_sources": [
            {"id": source_id, "slug": source_slug}
            for source_id, source_slug in zip(draft.retrieved_source_ids, draft.retrieved_source_slugs, strict=False)
        ],
        "generated_draft": draft.model_dump(mode="json"),
        "editorial_status": "draft",
        "current_step": "rag_draft",
        "execution_history": _trace("rag_draft"),
    }


async def node_editorial_gate(state: NewsroomState) -> dict:
    return {"current_step": "editorial_review", "execution_history": _trace("editorial_review", state.get("editorial_status", "draft"))}


async def node_publish(state: NewsroomState) -> dict:
    """Persist the human-approved draft as a published article; this is the workflow's real output."""
    lead = _lead(state)
    draft = state.get("generated_draft") or {}
    now = datetime.now(UTC)
    title = str(draft.get("title") or lead.headline)
    content_html = sanitize_html(str(draft.get("content_html", "")))
    articles = get_database().articles
    existing = await articles.find_one({"source_lead_id": lead.id})
    if existing and existing["status"] == ArticleStatus.PUBLISHED:
        # A retried node must not publish the same lead twice.
        return {"article_id": str(existing["_id"]), "editorial_status": "published", "current_step": "publish", "execution_history": _trace("publish")}
    actor_id = ObjectId(state["actor_id"])
    changes = {
        "title": title, "dek": draft.get("dek", ""), "content_html": content_html, "content_json": draft.get("content_json", {}),
        "topic": lead.topic, "geo": lead.geo, "status": ArticleStatus.PUBLISHED, "editor_id": actor_id, "updated_at": now,
        "published_at": now, "scheduled_for": None, "hero_url": draft.get("hero_url"), "source_lead_id": lead.id,
        "prompt_version": PRODUCTION_PROMPT_VERSION, "model_name": settings.gemini_production_model or "mock",
        "retrieved_sources": state.get("retrieved_sources", []),
    }
    if existing:
        changes["slug"] = await unique_slug(title, existing["_id"])
        await articles.update_one({"_id": existing["_id"]}, {"$set": changes})
        article = {**existing, **changes}
    else:
        article = {
            **changes, "slug": await unique_slug(title), "tags": ["ai-assisted"], "creator_id": actor_id, "hero_media_id": None,
            "created_at": now,
            "metrics": {"views": 0, "likes": 0, "dislikes": 0, "engagement_ratio": 0, "popularity_score": 0, "seo_score": None},
        }
        article["_id"] = (await articles.insert_one(dict(article))).inserted_id
    await index_published_article(article)
    await get_database().lead_inbox.update_one({"lead_id": lead.id}, {"$set": {"status": "published", "updated_at": now}})
    return {"article_id": str(article["_id"]), "editorial_status": "published", "current_step": "publish", "execution_history": _trace("publish")}


async def node_telemetry_rerank(state: NewsroomState) -> dict:
    """Re-rank after publication using the signal audience behaviour has actually produced so far.

    A newly published story has no reader data yet, so this must not invent an observation;
    the ranking signal changes only when real telemetry arrives.
    """
    lead = _lead(state)
    signal = await get_database().ranking_signals.find_one({"_id": f"{lead.topic}|{lead.geo}"}, {"weight_delta": 1})
    await run_selection([lead])
    return {
        "telemetry_delta": float((signal or {}).get("weight_delta", 0.0) or 0.0),
        "current_step": "telemetry",
        "execution_history": _trace("telemetry"),
    }
