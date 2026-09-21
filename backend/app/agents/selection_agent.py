from collections.abc import Iterable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from app.agents.prompts.selection import PROMPT_VERSION, build_selection_prompt
from app.agents.provider import get_provider
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import LeadInput, RankedLead, SelectionResult
from app.services.agent_metrics import record_agent_metrics


class SelectionGuidanceItem(BaseModel):
    lead_id: str
    suggested_angle: str = Field(min_length=1)
    editorial_guidance: str = Field(min_length=1)


class SelectionGuidanceResponse(BaseModel):
    guidance: list[SelectionGuidanceItem]

TOPIC_PRIORITY = {
    "nation-world": 0.08,
    "business": 0.07,
    "technology": 0.07,
    "climate": 0.06,
    "health": 0.06,
    "science": 0.05,
    "local": 0.05,
    "sports": 0.04,
    "culture": 0.03,
}


def baseline_editorial_score(candidate: dict[str, Any]) -> float:
    """Score a new lead before audience learning is available.

    This intentionally uses explainable editorial signals. Telemetry is applied
    separately, so past readership can improve a ranking without replacing the
    initial judgement about the incoming story itself.
    """
    headline = str(candidate["headline"]).strip()
    context = str(candidate.get("source_context") or "").strip()
    word_count = len(headline.split())
    context_words = len(context.split())
    score = 0.45 + TOPIC_PRIORITY.get(str(candidate.get("topic", "")).lower(), 0.03)
    if 6 <= word_count <= 20:
        score += 0.05
    if context_words >= 20:
        score += 0.10
    elif context_words >= 8:
        score += 0.06
    if any(character.isdigit() for character in f"{headline} {context}"):
        score += 0.03
    if str(candidate.get("geo", "global")).casefold() != "global":
        score += 0.03
    if candidate.get("source_url"):
        score += 0.02
    return _clamp_priority_score(score)


def _clamp_priority_score(score: float) -> float:
    return round(min(1.0, max(0.0, score)), 4)


def _candidate_from_document(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize seeded MongoDB leads and API-provided leads to one shape."""
    return {
        "lead_id": str(document.get("lead_id", document.get("id", document.get("_id")))),
        "headline": document["headline"],
        "topic": document.get("topic", "general"),
        "geo": document.get("geo", "global"),
        "source_url": document.get("source_url"),
        "source_context": document.get("source_context"),
        "base_score": (
            float(document["base_score"])
            if document.get("base_score") is not None
            else (float(document["priority_score"]) if document.get("priority_score") is not None else None)
        ),
        "previous_rank": document.get("current_rank", document.get("previous_rank")),
        "updated_at": document.get("updated_at", datetime.min.replace(tzinfo=UTC)),
    }


async def _load_candidates(leads: list[LeadInput]) -> list[dict[str, Any]]:
    """Read persisted candidates first, retaining ad-hoc API leads if needed."""
    requested_ids = [lead.id for lead in leads]
    criteria = {"lead_id": {"$in": requested_ids}} if requested_ids else {}
    persisted = [_candidate_from_document(item) async for item in get_database().lead_inbox.find(criteria)]
    persisted_ids = {item["lead_id"] for item in persisted}
    persisted.extend(
        _candidate_from_document(lead.model_dump(mode="json"))
        for lead in leads
        if lead.id not in persisted_ids
    )
    return persisted


async def _load_signal_deltas() -> dict[str, float]:
    return {
        str(item.get("_id", item.get("topic_geo_key"))): float(item.get("weight_delta", 0.0) or 0.0)
        async for item in get_database().ranking_signals.find({}, {"_id": 1, "topic_geo_key": 1, "weight_delta": 1})
    }


async def _persist_ranked_leads(ranked: Iterable[RankedLead], candidates: dict[str, dict[str, Any]]) -> None:
    collection = get_database().lead_inbox
    for lead in ranked:
        candidate = candidates[lead.lead_id]
        await collection.update_one(
            {"lead_id": lead.lead_id},
            {"$set": {
                "headline": lead.headline,
                "topic": candidate["topic"],
                "geo": candidate["geo"],
                "base_score": lead.base_score,
                "learned_weight_delta": lead.learned_weight_delta,
                "final_score": lead.final_score,
                "previous_rank": lead.previous_rank,
                "current_rank": lead.current_rank,
                "rank_shift": lead.rank_shift,
                "priority_score": lead.priority_score,
                "score_audit": {
                    "base_score": lead.base_score,
                    "learned_delta": lead.learned_weight_delta,
                    "final_score": lead.final_score,
                    "previous_rank": lead.previous_rank,
                    "current_rank": lead.current_rank,
                    "rank_shift": lead.rank_shift,
                },
                "updated_at": datetime.now(UTC),
            }},
            upsert=True,
        )


async def run_selection(leads: list[LeadInput]) -> SelectionResult:
    """Rank candidates deterministically from the latest closed-loop signals."""
    started = perf_counter()
    candidates = await _load_candidates(leads)
    signal_deltas = await _load_signal_deltas()
    for candidate in candidates:
        if candidate["base_score"] is None:
            candidate["base_score"] = baseline_editorial_score(candidate)
        candidate["learned_weight_delta"] = signal_deltas.get(f"{candidate['topic']}|{candidate['geo']}", 0.0)
        candidate["final_score"] = round(candidate["base_score"] + candidate["learned_weight_delta"], 4)

    deterministic_ranked: list[RankedLead] = []
    for current_rank, candidate in enumerate(sorted(
        candidates,
        key=lambda item: (-item["final_score"], -item["updated_at"].timestamp(), item["lead_id"]),
    ), start=1):
        previous_rank = candidate["previous_rank"]
        deterministic_ranked.append(RankedLead(
            lead_id=candidate["lead_id"], headline=candidate["headline"],
            priority_score=_clamp_priority_score(candidate["final_score"]),
            base_score=candidate["base_score"], learned_weight_delta=candidate["learned_weight_delta"],
            final_score=candidate["final_score"], previous_rank=previous_rank,
            current_rank=current_rank,
            rank_shift=(previous_rank - current_rank) if previous_rank is not None else 0,
            suggested_angle=f"Focus on the local impact of {candidate['topic']}.",
            suggested_publish_window="Next audience peak",
            reasoning="Ranked using the current topic and geography engagement signal.",
        ))

    fallback = {"guidance": [{"lead_id": item.lead_id, "suggested_angle": item.suggested_angle, "editorial_guidance": item.reasoning} for item in deterministic_ranked]}
    prompt = build_selection_prompt([{"lead_id": item["lead_id"], "headline": item["headline"], "topic": item["topic"], "geo": item["geo"]} for item in candidates])
    generated = await get_provider().generate_json(
        model=settings.gemini_selection_model,
        prompt=prompt,
        schema=SelectionGuidanceResponse,
        fallback=fallback,
    )
    generated_by_id = {item.lead_id: item for item in generated.guidance}
    ranked = [
        deterministic.model_copy(update={
            "suggested_angle": generated_by_id[deterministic.lead_id].suggested_angle,
            "reasoning": generated_by_id[deterministic.lead_id].editorial_guidance,
        }) if deterministic.lead_id in generated_by_id else deterministic
        for deterministic in deterministic_ranked
    ]
    await _persist_ranked_leads(ranked, {item["lead_id"]: item for item in candidates})
    result = SelectionResult(ranked=ranked)
    await record_agent_metrics("selection", settings.gemini_selection_model or "mock", prompt, result.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    return result
