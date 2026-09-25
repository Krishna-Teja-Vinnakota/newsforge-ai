from datetime import UTC, datetime
from time import perf_counter

from bson import ObjectId
from pymongo import ReturnDocument

from app.agents.provider import get_provider
from app.agents.prompts.telemetry import PROMPT_VERSION, build_telemetry_prompt
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import TelemetryResult
from app.models.telemetry import RankingSignal
from app.services.agent_metrics import record_agent_metrics


def _sample_size(metrics: dict) -> int:
    """Use the available aggregate audience as the evidence count."""
    return max(1, int(metrics.get("views", metrics.get("unique_users", 1)) or 1))


def _confidence(engagement_score: float, sample_size: int) -> float:
    """Increase confidence with more observations while keeping it bounded."""
    evidence_confidence = min(0.45, sample_size / 1_000 * 0.45)
    return round(min(0.99, 0.5 + evidence_confidence + engagement_score * 0.05), 4)


async def update_ranking_signal(
    topic: str,
    geo: str,
    metrics: dict,
    *,
    engagement_score: float | None = None,
    weight_delta: float | None = None,
) -> RankingSignal:
    """Apply one evaluated telemetry observation to its topic/geography signal."""
    score = engagement_score if engagement_score is not None else max(
        0, min(1, (metrics.get("engagement_ratio", 0) + 1) / 2)
    )
    raw_delta = (score - 0.5) * 0.2 if weight_delta is None else weight_delta
    bounded_delta = max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, raw_delta))
    sample_size = _sample_size(metrics)
    topic_geo_key = f"{topic}|{geo}"
    updated = await get_database().ranking_signals.find_one_and_update(
        {"_id": topic_geo_key},
        {
            "$set": {
                "topic": topic,
                "geo": geo,
                "confidence": _confidence(score, sample_size),
                "last_updated": datetime.now(UTC),
            },
            "$inc": {"weight_delta": bounded_delta, "sample_size": sample_size},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return RankingSignal.model_validate(updated)


async def run_telemetry(article_id: str) -> TelemetryResult:
    started = perf_counter()
    article = await get_database().articles.find_one({"_id": ObjectId(article_id)})
    if article is None:
        raise ValueError("Article not found")
    metrics = article.get("metrics", {})
    score = max(0, min(1, (metrics.get("engagement_ratio", 0) + 1) / 2))
    raw_delta = round((score - 0.5) * 0.2, 4)
    bounded_delta = max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, raw_delta))
    topic = article.get("topic", "general")
    geo = article.get("geo", "global")
    fallback = {"article_id": article_id, "topic": topic, "engagement_score": score, "popularity_rank_hint": max(0, metrics.get("popularity_score", 0)), "weight_delta": bounded_delta, "insight": "Audience interaction has been converted into a bounded future-ranking signal.", "seo_recommendations": ["Use a specific reader-focused headline.", "Add verified descriptive metadata."]}
    prompt = build_telemetry_prompt(metrics, settings.agent_max_weight_delta)
    result = await get_provider().generate_json(model=settings.gemini_telemetry_model, prompt=prompt, schema=TelemetryResult, fallback=fallback)
    result.weight_delta = max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, result.weight_delta))
    # Keep the article metadata authoritative; the LLM evaluates engagement, not taxonomy or identity.
    result.topic = topic
    result.article_id = article_id
    await update_ranking_signal(
        topic,
        geo,
        metrics,
        engagement_score=result.engagement_score,
        weight_delta=result.weight_delta,
    )
    await record_agent_metrics("telemetry", settings.gemini_telemetry_model or "mock", prompt, result.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    return result
