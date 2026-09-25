from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from app.agents.prompts.telemetry import PROMPT_VERSION, build_telemetry_prompt
from app.agents.provider import get_provider
from app.agents.selection_agent import run_selection
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import LeadCandidate, TelemetryResult
from app.models.telemetry import RankingSignal
from app.services.agent_metrics import record_agent_metrics


def _sample_size(metrics: dict) -> int:
    """Use the available aggregate audience as the evidence count."""
    return max(1, int(metrics.get("views", metrics.get("total_events", metrics.get("unique_users", 1))) or 1))


def _confidence(engagement_score: float, sample_size: int) -> float:
    """Increase confidence with more observations while keeping it bounded."""
    evidence_confidence = min(0.45, sample_size / 1_000 * 0.45)
    return round(min(0.99, 0.5 + evidence_confidence + engagement_score * 0.05), 4)


def _bounded(value: float) -> float:
    return round(max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, value)), 4)


def _metrics_fingerprint(metrics: dict[str, Any]) -> str:
    payload = json.dumps(metrics, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def _rebuild_ranking_signal(topic: str, geo: str) -> RankingSignal:
    topic_geo_key = f"{topic}|{geo}"
    contributions = [
        item async for item in get_database().ranking_signal_contributions.find({"topic_geo_key": topic_geo_key})
    ]
    total = sum(max(1, int(item.get("sample_size", 1))) for item in contributions)
    weighted_delta = sum(
        float(item.get("weight_delta", 0.0)) * max(1, int(item.get("sample_size", 1)))
        for item in contributions
    ) / max(1, total)
    weighted_engagement = sum(
        float(item.get("engagement_score", 0.5)) * max(1, int(item.get("sample_size", 1)))
        for item in contributions
    ) / max(1, total)
    document = {
        "_id": topic_geo_key,
        "topic": topic,
        "geo": geo,
        "weight_delta": _bounded(weighted_delta),
        "sample_size": total,
        "confidence": _confidence(weighted_engagement, total),
        "last_updated": datetime.now(UTC),
    }
    await get_database().ranking_signals.replace_one({"_id": topic_geo_key}, document, upsert=True)
    return RankingSignal.model_validate(document)


async def update_ranking_signal(
    topic: str,
    geo: str,
    metrics: dict,
    *,
    engagement_score: float | None = None,
    weight_delta: float | None = None,
    observation_id: str | None = None,
    source: str = "aggregate",
    metrics_fingerprint: str | None = None,
    analysis_result: dict[str, Any] | None = None,
) -> RankingSignal:
    """Replace one observation and recompute its channel signal without double-counting."""
    score = engagement_score if engagement_score is not None else max(
        0, min(1, (metrics.get("engagement_ratio", 0) + 1) / 2)
    )
    raw_delta = (score - 0.5) * 0.2 if weight_delta is None else weight_delta
    topic_geo_key = f"{topic}|{geo}"
    contribution_id = observation_id or f"aggregate:{topic_geo_key}"
    document: dict[str, Any] = {
        "_id": contribution_id,
        "topic_geo_key": topic_geo_key,
        "topic": topic,
        "geo": geo,
        "weight_delta": _bounded(raw_delta),
        "engagement_score": round(score, 4),
        "sample_size": _sample_size(metrics),
        "source": source,
        "metrics_fingerprint": metrics_fingerprint or _metrics_fingerprint(metrics),
        "updated_at": datetime.now(UTC),
    }
    if analysis_result is not None:
        document["analysis_result"] = analysis_result
        document["analysis_fingerprint"] = document["metrics_fingerprint"]
    await get_database().ranking_signal_contributions.replace_one(
        {"_id": contribution_id}, document, upsert=True
    )
    return await _rebuild_ranking_signal(topic, geo)


async def rerank_open_leads() -> int:
    cursor = get_database().lead_inbox.find({"status": {"$nin": ["rejected", "published"]}}).sort(
        [("current_rank", 1), ("updated_at", -1)]
    ).limit(25)
    candidates = [
        LeadCandidate(
            id=document["lead_id"],
            headline=document["headline"],
            topic=document.get("topic", "general"),
            geo=document.get("geo", "global"),
        )
        async for document in cursor
    ]
    if not candidates:
        return 0
    result = await run_selection(candidates, generate_guidance=False)
    return len(result.ranked)


def _signal_changed(previous: dict[str, Any] | None, current: RankingSignal) -> bool:
    """Rerank when either the score or the forecast evidence changes."""
    return (
        previous is None
        or abs(float(previous.get("weight_delta", 0.0)) - current.weight_delta) >= 0.0001
        or int(previous.get("sample_size", 0) or 0) != current.sample_size
        or abs(float(previous.get("confidence", 0.0)) - current.confidence) >= 0.0001
    )


async def process_article_engagement(article_id: str) -> RankingSignal | None:
    """Apply real article metrics once per distinct snapshot and rerank open leads."""
    if not ObjectId.is_valid(article_id):
        return None
    article = await get_database().articles.find_one({"_id": ObjectId(article_id)})
    if article is None:
        return None
    metrics = article.get("metrics", {})
    fingerprint = _metrics_fingerprint(metrics)
    contribution_id = f"article:{article_id}"
    existing = await get_database().ranking_signal_contributions.find_one({"_id": contribution_id})
    if existing and existing.get("metrics_fingerprint") == fingerprint:
        return None
    topic = article.get("topic", "general")
    geo = article.get("geo", "global")
    previous_signal = await get_database().ranking_signals.find_one({"_id": f"{topic}|{geo}"})
    signal = await update_ranking_signal(
        topic,
        geo,
        metrics,
        observation_id=contribution_id,
        source="reader_engagement",
        metrics_fingerprint=fingerprint,
    )
    if _signal_changed(previous_signal, signal):
        await rerank_open_leads()
    return signal


async def process_public_event(topic: str, geo: str, event_type: str) -> RankingSignal:
    """Aggregate generic events into a replaceable channel contribution."""
    key = f"{topic}|{geo}"
    previous_signal = await get_database().ranking_signals.find_one({"_id": key})
    await get_database().telemetry_rollups.find_one_and_update(
        {"_id": key},
        {
            "$set": {"topic": topic, "geo": geo, "updated_at": datetime.now(UTC)},
            "$inc": {f"counts.{event_type}": 1, "total_events": 1},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    rollup = await get_database().telemetry_rollups.find_one({"_id": key})
    counts = rollup.get("counts", {})
    total = max(1, int(rollup.get("total_events", 1)))
    event_values = {"view": 0.5, "like": 0.75, "save": 0.85, "share": 0.95}
    engagement = sum(int(counts.get(name, 0)) * value for name, value in event_values.items()) / total
    signal = await update_ranking_signal(
        topic,
        geo,
        {"total_events": total},
        engagement_score=engagement,
        observation_id=f"events:{key}",
        source="public_events",
        metrics_fingerprint=_metrics_fingerprint({"counts": counts, "total_events": total}),
    )
    if _signal_changed(previous_signal, signal):
        await rerank_open_leads()
    return signal


async def run_telemetry(article_id: str) -> TelemetryResult:
    started = perf_counter()
    article = await get_database().articles.find_one({"_id": ObjectId(article_id)})
    if article is None:
        raise ValueError("Article not found")
    metrics = article.get("metrics", {})
    fingerprint = _metrics_fingerprint(metrics)
    contribution_id = f"article:{article_id}"
    previous = await get_database().ranking_signal_contributions.find_one({"_id": contribution_id})
    if previous and previous.get("analysis_fingerprint") == fingerprint and previous.get("analysis_result"):
        cached = TelemetryResult.model_validate(previous["analysis_result"])
        cached.affected_leads_count = await rerank_open_leads()
        return cached

    score = max(0, min(1, (metrics.get("engagement_ratio", 0) + 1) / 2))
    bounded_delta = _bounded((score - 0.5) * 0.2)
    topic = article.get("topic", "general")
    geo = article.get("geo", "global")
    fallback = {
        "article_id": article_id,
        "topic": topic,
        "engagement_score": score,
        "popularity_rank_hint": max(0, metrics.get("popularity_score", 0)),
        "weight_delta": bounded_delta,
        "insight": "Audience interaction has been converted into a bounded future-ranking signal.",
        "seo_recommendations": [
            "Use a specific reader-focused headline.",
            "Add verified descriptive metadata.",
        ],
    }
    prompt = build_telemetry_prompt(metrics, settings.agent_max_weight_delta)
    result = await get_provider().generate_json(
        model=settings.gemini_telemetry_model,
        prompt=prompt,
        schema=TelemetryResult,
        fallback=fallback,
    )
    result.weight_delta = _bounded(result.weight_delta)
    result.topic = topic
    result.article_id = article_id
    signal = await update_ranking_signal(
        topic,
        geo,
        metrics,
        engagement_score=result.engagement_score,
        weight_delta=result.weight_delta,
        observation_id=contribution_id,
        source="telemetry_agent",
        metrics_fingerprint=fingerprint,
        analysis_result=result.model_dump(mode="json"),
    )
    result.topic_geo_key = signal.topic_geo_key
    result.signal_confidence = signal.confidence
    result.signal_sample_size = signal.sample_size
    result.affected_leads_count = await rerank_open_leads()
    await get_database().ranking_signal_contributions.update_one(
        {"_id": contribution_id}, {"$set": {"analysis_result": result.model_dump(mode="json")}}
    )
    await record_agent_metrics(
        "telemetry",
        settings.gemini_telemetry_model or "mock",
        prompt,
        result.model_dump(mode="json"),
        int((perf_counter() - started) * 1000),
    )
    return result
