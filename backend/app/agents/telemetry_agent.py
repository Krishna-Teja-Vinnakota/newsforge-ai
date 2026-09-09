from bson import ObjectId
from datetime import UTC, datetime

from app.agents.provider import get_provider
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import TelemetryResult

PROMPT_VERSION = "telemetry-v1"


async def run_telemetry(article_id: str) -> TelemetryResult:
    article = await get_database().articles.find_one({"_id": ObjectId(article_id)})
    if article is None:
        raise ValueError("Article not found")
    metrics = article.get("metrics", {})
    score = max(0, min(1, (metrics.get("engagement_ratio", 0) + 1) / 2))
    raw_delta = round((score - 0.5) * 0.2, 4)
    bounded_delta = max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, raw_delta))
    fallback = {"article_id": article_id, "topic": article.get("topic", "general"), "engagement_score": score, "popularity_rank_hint": max(0, metrics.get("popularity_score", 0)), "weight_delta": bounded_delta, "insight": "Audience interaction has been converted into a bounded future-ranking signal.", "seo_recommendations": ["Use a specific reader-focused headline.", "Add verified descriptive metadata."]}
    prompt = f"You are NewsForge's audience telemetry agent. Analyze only these aggregate metrics: {metrics}. Propose a bounded ranking change of no more than {settings.agent_max_weight_delta}. Return only the required JSON schema."
    result = await get_provider().generate_json(model=settings.gemini_telemetry_model, prompt=prompt, schema=TelemetryResult, fallback=fallback)
    result.weight_delta = max(-settings.agent_max_weight_delta, min(settings.agent_max_weight_delta, result.weight_delta))
    key = f"{result.topic}|global"
    await get_database().ranking_signals.update_one({"key": key}, {"$inc": {"weight": result.weight_delta}, "$set": {"updated_at": datetime.now(UTC)}}, upsert=True)
    return result
