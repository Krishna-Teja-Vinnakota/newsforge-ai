import logging
from datetime import UTC, datetime

from app.core.database import get_database
from app.core.storage import delete_object

logger = logging.getLogger("uvicorn.error")


async def sweep_expired_pending_media(limit: int = 20) -> int:
    """Delete AI images that were generated but never applied to a story.

    An image still referenced by an article (applied in the editor but saved
    late) is kept and simply promoted to applied.
    """
    db = get_database()
    removed = 0
    cursor = db.media.find({"status": "pending", "expires_at": {"$lt": datetime.now(UTC)}}).limit(limit)
    async for media in cursor:
        if await db.articles.find_one({"hero_media_id": media["_id"]}, {"_id": 1}):
            await db.media.update_one({"_id": media["_id"]}, {"$set": {"status": "applied"}, "$unset": {"expires_at": ""}})
            continue
        try:
            await delete_object(media["object_key"])
        except Exception as error:  # noqa: BLE001 - keep the document so a later sweep retries the object
            logger.warning("Could not delete expired AI image %s: %s", media["object_key"], error)
            continue
        await db.media.delete_one({"_id": media["_id"]})
        removed += 1
    return removed
