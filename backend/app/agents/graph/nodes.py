from datetime import UTC, datetime

from app.agents.production_agent import run_production
from app.agents.selection_agent import run_selection
from app.agents.telemetry_agent import update_ranking_signal
from app.models.agents import LeadInput
from app.services.retrieval import retrieve_editorial_context

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
    sources = await retrieve_editorial_context(lead.topic)
    draft = await run_production(
        lead.headline,
        lead.topic,
        state.get("selection_result", {}).get("suggested_angle", ""),
        ["web", "social", "newsletter"],
    )
    return {
        "retrieved_sources": sources,
        "generated_draft": draft.model_dump(mode="json"),
        "editorial_status": "draft",
        "current_step": "rag_draft",
        "execution_history": _trace("rag_draft"),
    }


async def node_editorial_gate(state: NewsroomState) -> dict:
    return {"current_step": "editorial_review", "execution_history": _trace("editorial_review", state.get("editorial_status", "draft"))}


async def node_publish(state: NewsroomState) -> dict:
    return {"editorial_status": "published", "current_step": "publish", "execution_history": _trace("publish")}


async def node_telemetry_rerank(state: NewsroomState) -> dict:
    lead = _lead(state)
    signal = await update_ranking_signal(
        lead.topic,
        lead.geo,
        {"views": 1, "engagement_ratio": 0.0},
    )
    await run_selection([lead])
    return {
        "telemetry_delta": signal.weight_delta,
        "current_step": "telemetry",
        "execution_history": _trace("telemetry"),
    }
