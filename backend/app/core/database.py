import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.settings import settings

_client: AsyncIOMotorClient | None = None
logger = logging.getLogger("newsforge.database")


async def connect_to_mongo(retries: int = 5, retry_delay_seconds: float = 2) -> bool:
    """Connect and create indexes without preventing the API from starting.

    Docker normally waits for MongoDB's health check. The retry also covers a
    direct local start while MongoDB is still booting.
    """
    global _client
    _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2500)
    for attempt in range(1, retries + 1):
        try:
            database = get_database()
            await _client.admin.command("ping")
            await database.users.create_index("email", unique=True)
            await database.media.create_index("object_key", unique=True)
            await database.articles.create_index("slug", unique=True)
            await database.articles.create_index([("status", 1), ("published_at", -1)])
            await database.workflow_events.create_index([("article_id", 1), ("created_at", -1)])
            await database.feedback_events.create_index([("article_id", 1), ("actor_key", 1), ("day", 1)], unique=True)
            await database.view_events.create_index([("article_id", 1), ("actor_key", 1), ("day", 1)], unique=True)
            await database.articles.create_index([("status", 1), ("metrics.popularity_score", -1)])
            await database.agent_runs.create_index([("agent", 1), ("created_at", -1)])
            await database.agent_metrics.create_index([("timestamp", -1), ("agent", 1)])
            await database.audit_logs.create_index([("timestamp", -1), ("user_id", 1)])
            await database.telemetry_events.create_index("timestamp")
            await database.workflow_threads.create_index("thread_id", unique=True)
            await database.lead_inbox.create_index("lead_id", unique=True)
            await database.ranking_signals.create_index("key", unique=True)
            await database.editorial_index.create_index("article_id", unique=True)
            await database.editorial_index.create_index([("topic", 1), ("indexed_at", -1)])
            await database.topics.create_index("slug", unique=True)
            await database.tags.create_index("name", unique=True)
            logger.info("Connected to MongoDB")
            return True
        except Exception as error:
            if attempt == retries:
                logger.warning("MongoDB unavailable; API will start in degraded mode: %s", error)
                return False
            logger.warning("MongoDB not ready (attempt %s/%s); retrying", attempt, retries)
            await asyncio.sleep(retry_delay_seconds)
    return False


def get_database():
    if _client is None:
        raise RuntimeError("MongoDB has not been initialized")
    return _client[settings.mongodb_database]


async def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


async def ping_mongo() -> bool:
    if _client is None:
        return False
    try:
        await _client.admin.command("ping")
        return True
    except Exception:
        return False
