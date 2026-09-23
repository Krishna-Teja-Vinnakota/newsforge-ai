from collections.abc import Iterable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from app.agents.prompts.selection import PROMPT_VERSION, build_selection_prompt
from app.agents.provider import get_provider
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import LeadInboxItem, LeadInput, RankedLead, SelectionResult
from app.models.trends import TrendSignal
from app.services.agent_metrics import record_agent_metrics
from app.services.articles import load_recent_published_article_metadata
from app.services.trends.scoring import (
    SCORING_VERSION,
    count_recent_coverage,
    score_trend_adjustment,
    suggested_format,
)
from app.services.trends.refresh import load_fresh_signals


class SelectionGuidanceItem(BaseModel):
    lead_id: str
    suggested_angle: str = Field(min_length=1)
    why_now: str | None = None


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
    """Score a new lead before audience learning is available."""
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


def _as_utc(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _candidate_from_document(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize seeded MongoDB leads and API-provided leads to one shape."""
    return {
        "lead_id": str(document.get("lead_id", document.get("id", document.get("_id")))),
        "headline": document["headline"],
        "topic": document.get("topic", "general"),
        "geo": document.get("geo", "global"),
        "source_url": document.get("source_url"),
        "source_context": document.get("source_context"),
        "published_at": document.get("published_at"),
        "status": document.get("status", "pending"),
        "base_score": (
            float(document["base_score"])
            if document.get("base_score") is not None
            else (float(document["priority_score"]) if document.get("priority_score") is not None else None)
        ),
        "previous_rank": document.get("current_rank", document.get("previous_rank")),
        "updated_at": _as_utc(document.get("updated_at")),
    }


async def _load_candidates(leads: list[LeadInput]) -> list[dict[str, Any]]:
    requested_ids = [lead.id for lead in leads]
    criteria = {"lead_id": {"$in": requested_ids}} if requested_ids else {}
    persisted = [_candidate_from_document(item) async for item in get_database().lead_inbox.find(criteria)]
    persisted_ids = {item["lead_id"] for item in persisted}
    persisted.extend(_candidate_from_document(lead.model_dump()) for lead in leads if lead.id not in persisted_ids)
    return persisted


async def _load_signal_deltas() -> dict[str, float]:
    return {
        str(item.get("_id", item.get("topic_geo_key"))): float(item.get("weight_delta", 0.0) or 0.0)
        async for item in get_database().ranking_signals.find({}, {"_id": 1, "topic_geo_key": 1, "weight_delta": 1})
    }


async def _load_trend_signals(now: datetime) -> list[TrendSignal]:
    return await load_fresh_signals(now, settings.trends_max_age_hours)


def lead_to_item(document: dict[str, Any]) -> LeadInboxItem:
    """Map the stored lead shape consistently for list and decision endpoints."""
    return LeadInboxItem(
        id=str(document.get("lead_id", document.get("id", document.get("_id")))),
        headline=document["headline"],
        topic=document.get("topic", "general"),
        geo=document.get("geo", "global"),
        source_url=document.get("source_url"),
        source_context=document.get("source_context"),
        published_at=document.get("published_at"),
        status=document.get("status", "pending"),
        priority_score=document.get("priority_score"),
        suggested_angle=document.get("suggested_angle"),
        reasoning=document.get("reasoning"),
        base_score=float(document.get("base_score", 0.0) or 0.0),
        learned_weight_delta=float(document.get("learned_weight_delta", 0.0) or 0.0),
        final_score=float(document.get("final_score", 0.0) or 0.0),
        previous_rank=document.get("previous_rank"),
        current_rank=document.get("current_rank"),
        rank_shift=int(document.get("rank_shift", 0) or 0),
        trend_boost=float(document.get("trend_boost", 0.0) or 0.0),
        coverage_adjustment=float(document.get("coverage_adjustment", 0.0) or 0.0),
        trend_evidence=document.get("trend_evidence") or [],
        suggested_format=document.get("suggested_format", "standard"),
        why_now=document.get("why_now"),
        origin=document.get("origin", "manual"),
        score_audit=document.get("score_audit") or {},
    )


async def persist_ranked_leads(ranked: Iterable[RankedLead], candidates: dict[str, dict[str, Any]]) -> None:
    collection = get_database().lead_inbox
    updated_at = datetime.now(UTC)
    for lead in ranked:
        candidate = candidates[lead.lead_id]
        values: dict[str, Any] = {
            "headline": lead.headline,
            "topic": candidate["topic"],
            "geo": candidate["geo"],
            "source_url": candidate.get("source_url"),
            "source_context": candidate.get("source_context"),
            "published_at": candidate.get("published_at"),
            "base_score": lead.base_score,
            "learned_weight_delta": lead.learned_weight_delta,
            "final_score": lead.final_score,
            "previous_rank": lead.previous_rank,
            "current_rank": lead.current_rank,
            "rank_shift": lead.rank_shift,
            "priority_score": lead.priority_score,
            "suggested_angle": lead.suggested_angle,
            "suggested_publish_window": lead.suggested_publish_window,
            "reasoning": lead.reasoning,
            "score_audit": lead.score_audit,
            "updated_at": updated_at,
        }
        if "trend_boost" in lead.score_audit:
            values.update(
                {
                    "trend_boost": lead.trend_boost,
                    "coverage_adjustment": lead.coverage_adjustment,
                    "trend_evidence": lead.trend_evidence,
                    "suggested_format": lead.suggested_format,
                    "why_now": lead.why_now,
                }
            )
        update: dict[str, Any] = {
            "$set": values,
            "$setOnInsert": {"lead_id": lead.lead_id, "status": candidate.get("status", "pending")},
        }
        if not settings.trends_scoring_enabled:
            update["$unset"] = {
                "trend_boost": "",
                "coverage_adjustment": "",
                "trend_evidence": "",
                "suggested_format": "",
                "why_now": "",
            }
        await collection.update_one(
            {"lead_id": lead.lead_id},
            update,
            upsert=True,
        )


_persist_ranked_leads = persist_ranked_leads


def _legacy_audit(candidate: dict[str, Any], current_rank: int, rank_shift: int) -> dict[str, Any]:
    return {
        "base_score": candidate["base_score"],
        "learned_delta": candidate["learned_weight_delta"],
        "final_score": candidate["final_score"],
        "previous_rank": candidate["previous_rank"],
        "current_rank": current_rank,
        "rank_shift": rank_shift,
    }


def _deterministic_reason(candidate: dict[str, Any], trend_score: dict[str, Any] | None, shadow: bool) -> str:
    reason = f"Base editorial score {candidate['base_score']:.2f} with telemetry delta {candidate['learned_weight_delta']:+.2f}."
    if trend_score and not shadow:
        reason += (
            f" Cached trend evidence adds {trend_score['trend_boost']:+.2f} and coverage adds "
            f"{trend_score['coverage_adjustment']:+.2f}."
        )
    return reason


async def run_selection(leads: list[LeadInput]) -> SelectionResult:
    """Rank candidates deterministically from cached signals; never fetch externally."""
    started = perf_counter()
    now = datetime.now(UTC)
    candidates = await _load_candidates(leads)
    signal_deltas = await _load_signal_deltas()
    trend_mode = settings.trends_refresh_enabled or settings.trends_scoring_enabled
    shadow_mode = settings.trends_refresh_enabled and not settings.trends_scoring_enabled
    trend_signals: list[TrendSignal] = []
    recent_articles: list[dict[str, Any]] = []
    if trend_mode:
        trend_signals = await _load_trend_signals(now)
        recent_articles = await load_recent_published_article_metadata(now=now)

    for candidate in candidates:
        if candidate["base_score"] is None:
            candidate["base_score"] = baseline_editorial_score(candidate)
        candidate["learned_weight_delta"] = signal_deltas.get(f"{candidate['topic']}|{candidate['geo']}", 0.0)
        candidate["trend_score"] = None
        base_final = candidate["base_score"] + candidate["learned_weight_delta"]
        if trend_mode:
            stories = count_recent_coverage(candidate, recent_articles)
            candidate["trend_score"] = score_trend_adjustment(
                candidate,
                trend_signals,
                stories,
                now=now,
                max_total_adjustment=settings.trends_max_total_adjustment,
                default_country=settings.trends_geo,
                max_signal_age_hours=settings.trends_max_age_hours,
            )
            if settings.trends_scoring_enabled:
                base_final += candidate["trend_score"]["trend_boost"] + candidate["trend_score"]["coverage_adjustment"]
        candidate["final_score"] = round(base_final, 4)

    sorted_candidates = sorted(
        candidates,
        key=lambda item: (-item["final_score"], -item["updated_at"].timestamp(), item["lead_id"]),
    )
    deterministic_ranked: list[RankedLead] = []
    for current_rank, candidate in enumerate(sorted_candidates, start=1):
        previous_rank = candidate["previous_rank"]
        rank_shift = (previous_rank - current_rank) if previous_rank is not None else 0
        trend_score = candidate["trend_score"]
        audit = _legacy_audit(candidate, current_rank, rank_shift)
        applied_evidence: list[dict[str, Any]] = []
        applied_trend_boost = 0.0
        applied_coverage = 0.0
        format_name = "standard"
        if trend_score:
            audit.update(
                {
                    "scoring_version": SCORING_VERSION,
                    "stories_published_7d": trend_score["stories_published_7d"],
                    "trend_config": trend_score["trend_config"],
                    "trend_evidence": trend_score["trend_evidence"],
                }
            )
            if shadow_mode:
                audit.update(
                    {
                        "shadow_trend_boost": trend_score["trend_boost"],
                        "shadow_coverage_adjustment": trend_score["coverage_adjustment"],
                    }
                )
            else:
                applied_trend_boost = trend_score["trend_boost"]
                applied_coverage = trend_score["coverage_adjustment"]
                applied_evidence = trend_score["trend_evidence"]
                format_name = suggested_format(trend_score)
                audit.update({"trend_boost": applied_trend_boost, "coverage_adjustment": applied_coverage})
        deterministic_ranked.append(
            RankedLead(
                lead_id=candidate["lead_id"],
                headline=candidate["headline"],
                priority_score=_clamp_priority_score(candidate["final_score"]),
                base_score=candidate["base_score"],
                learned_weight_delta=candidate["learned_weight_delta"],
                final_score=candidate["final_score"],
                previous_rank=previous_rank,
                current_rank=current_rank,
                rank_shift=rank_shift,
                trend_boost=applied_trend_boost,
                coverage_adjustment=applied_coverage,
                trend_evidence=applied_evidence,
                suggested_format=format_name,
                suggested_angle=f"Focus on the local impact of {candidate['topic']}.",
                suggested_publish_window="Next audience peak",
                reasoning=_deterministic_reason(candidate, trend_score, shadow_mode),
                score_audit=audit,
            )
        )

    fallback = {
        "guidance": [
            {
                "lead_id": item.lead_id,
                "suggested_angle": item.suggested_angle,
                "why_now": "Matched cached signals indicate timely reader interest." if item.trend_evidence else None,
            }
            for item in deterministic_ranked
        ]
    }
    ranked_by_id = {item.lead_id: item for item in deterministic_ranked}
    prompt_candidates = [
        {
            "lead_id": candidate["lead_id"],
            "headline": candidate["headline"],
            "topic": candidate["topic"],
            "geo": candidate["geo"],
            "trend_evidence": [
                {"source": evidence["source"], "label": str(evidence["label"])[:180]}
                for evidence in ranked_by_id[candidate["lead_id"]].trend_evidence[:5]
            ],
        }
        for candidate in candidates
    ]
    prompt = build_selection_prompt(prompt_candidates)
    generated = await get_provider().generate_json(
        model=settings.gemini_selection_model,
        prompt=prompt,
        schema=SelectionGuidanceResponse,
        fallback=fallback,
    )
    generated_by_id = {item.lead_id: item for item in generated.guidance}
    ranked = [
        (
            deterministic.model_copy(
                update={
                    "suggested_angle": generated_by_id[deterministic.lead_id].suggested_angle,
                    "why_now": generated_by_id[deterministic.lead_id].why_now,
                }
            )
            if deterministic.lead_id in generated_by_id
            else deterministic
        )
        for deterministic in deterministic_ranked
    ]
    await persist_ranked_leads(ranked, {item["lead_id"]: item for item in candidates})
    result = SelectionResult(ranked=ranked)
    await record_agent_metrics(
        "selection",
        settings.gemini_selection_model or "mock",
        prompt,
        result.model_dump(mode="json"),
        int((perf_counter() - started) * 1000),
    )
    return result
