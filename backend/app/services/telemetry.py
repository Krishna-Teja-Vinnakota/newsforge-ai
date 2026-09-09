from datetime import UTC, datetime

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.models.telemetry import ArticleMetrics


def current_day() -> str:
    return datetime.now(UTC).date().isoformat()


def metrics_from_article(article: dict) -> ArticleMetrics:
    metrics = article.get("metrics", {})
    return ArticleMetrics(
        views=metrics.get("views", 0), likes=metrics.get("likes", 0), dislikes=metrics.get("dislikes", 0),
        engagement_ratio=metrics.get("engagement_ratio", 0), popularity_score=metrics.get("popularity_score", 0),
    )


async def refresh_article_score(article_id: ObjectId) -> ArticleMetrics:
    article = await get_database().articles.find_one({"_id": article_id}, {"metrics": 1})
    metrics = article.get("metrics", {}) if article else {}
    likes, dislikes, views = metrics.get("likes", 0), metrics.get("dislikes", 0), metrics.get("views", 0)
    engagement_ratio = round((likes - dislikes) / max(1, likes + dislikes), 4)
    popularity_score = round((likes * 3) - (dislikes * 2) + min(views, 5000) * 0.08 + engagement_ratio * 20, 4)
    await get_database().articles.update_one({"_id": article_id}, {"$set": {"metrics.engagement_ratio": engagement_ratio, "metrics.popularity_score": popularity_score}})
    return ArticleMetrics(views=views, likes=likes, dislikes=dislikes, engagement_ratio=engagement_ratio, popularity_score=popularity_score)


async def record_view(article_id: ObjectId, actor_key: str) -> ArticleMetrics:
    try:
        await get_database().view_events.insert_one({"article_id": article_id, "actor_key": actor_key, "day": current_day(), "created_at": datetime.now(UTC)})
        await get_database().articles.update_one({"_id": article_id}, {"$inc": {"metrics.views": 1}})
    except DuplicateKeyError:
        pass
    return await refresh_article_score(article_id)


async def record_feedback(article_id: ObjectId, actor_key: str, action: str) -> tuple[str, ArticleMetrics]:
    day = current_day()
    events = get_database().feedback_events
    existing = await events.find_one({"article_id": article_id, "actor_key": actor_key, "day": day})
    previous = existing.get("action") if existing else None
    if previous != action:
        delta = {"metrics.likes": 0, "metrics.dislikes": 0}
        if previous == "like": delta["metrics.likes"] -= 1
        if previous == "dislike": delta["metrics.dislikes"] -= 1
        delta[f"metrics.{action}s"] += 1
        if existing:
            await events.update_one({"_id": existing["_id"]}, {"$set": {"action": action, "updated_at": datetime.now(UTC)}})
        else:
            try:
                await events.insert_one({"article_id": article_id, "actor_key": actor_key, "day": day, "action": action, "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)})
            except DuplicateKeyError:
                return await record_feedback(article_id, actor_key, action)
        await get_database().articles.update_one({"_id": article_id}, {"$inc": delta})
    return action, await refresh_article_score(article_id)
