import re
from datetime import UTC, datetime

from app.core.database import get_database


async def index_published_article(article: dict) -> None:
    """Persist a retrievable, provenance-preserving record for Phase 7 RAG."""
    text = re.sub(r"<[^>]+>", " ", article.get("content_html", "")).strip()
    await get_database().editorial_index.update_one(
        {"article_id": article["_id"]},
        {"$set": {"article_id": article["_id"], "slug": article["slug"], "title": article["title"], "topic": article["topic"], "tags": article.get("tags", []), "excerpt": (article.get("dek") or text)[:500], "media_id": article.get("hero_media_id"), "indexed_at": datetime.now(UTC)}},
        upsert=True,
    )


async def retrieve_editorial_context(topic: str, limit: int = 3) -> list[dict[str, str]]:
    """Local deterministic retrieval fallback; Phase 7 can replace scoring with Gemini embeddings."""
    cursor = get_database().editorial_index.find({"$or": [{"topic": topic.lower()}, {"tags": topic.lower()}]}, {"slug": 1, "title": 1, "excerpt": 1}).limit(limit)
    sources = []
    async for article in cursor:
        sources.append({"id": str(article.get("_id", article.get("article_id", ""))), "slug": article["slug"], "title": article["title"], "excerpt": article.get("excerpt", "")})
    return sources
