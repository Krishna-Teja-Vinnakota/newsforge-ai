import re
import unicodedata
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.database import get_database
from app.models.article import ArticleAuthor, ArticleResponse, ArticleStatus


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:100] or "untitled-story"


async def unique_slug(title: str, exclude_id: ObjectId | None = None) -> str:
    base = slugify(title)
    candidate, sequence = base, 2
    query: dict = {"slug": candidate}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    while await get_database().articles.find_one(query, {"_id": 1}):
        candidate = f"{base}-{sequence}"
        sequence += 1
        query["slug"] = candidate
    return candidate


async def author_response(user_id: ObjectId | None) -> ArticleAuthor | None:
    if user_id is None:
        return None
    user = await get_database().users.find_one({"_id": user_id})
    if user is None:
        return None
    avatar_url = None
    if user.get("avatar_media_id"):
        media = await get_database().media.find_one({"_id": user["avatar_media_id"]})
        avatar_url = media.get("url") if media else None
    return ArticleAuthor(id=str(user["_id"]), display_name=user["display_name"], avatar_url=avatar_url)


async def article_response(article: dict) -> ArticleResponse:
    # Demo/imported stories can provide a public image URL directly, while CMS
    # uploads use a MinIO media reference. Support both sources.
    hero_url = article.get("hero_url")
    if article.get("hero_media_id"):
        media = await get_database().media.find_one({"_id": article["hero_media_id"]})
        hero_url = media.get("url") if media else hero_url
    creator = await author_response(article["creator_id"])
    if creator is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Article creator is unavailable")
    return ArticleResponse(
        id=str(article["_id"]), slug=article["slug"], status=article["status"], title=article["title"], dek=article["dek"],
        content_json=article["content_json"], content_html=article["content_html"], topic=article["topic"], tags=article["tags"],
        hero_media_id=str(article["hero_media_id"]) if article.get("hero_media_id") else None, hero_url=hero_url, creator=creator, editor=await author_response(article.get("editor_id")), created_at=article["created_at"],
        updated_at=article["updated_at"], published_at=article.get("published_at"), scheduled_for=article.get("scheduled_for"),
    )


async def get_article_or_404(article_id: str) -> dict:
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article = await get_database().articles.find_one({"_id": ObjectId(article_id)})
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


async def add_workflow_event(article_id: ObjectId, actor_id: ObjectId, from_status: str | None, to_status: str, note: str) -> None:
    await get_database().workflow_events.insert_one({"article_id": article_id, "actor_id": actor_id, "from_status": from_status, "to_status": to_status, "note": note, "created_at": datetime.now(UTC)})
