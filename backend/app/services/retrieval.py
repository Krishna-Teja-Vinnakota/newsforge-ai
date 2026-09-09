import re

from app.core.database import get_database


async def retrieve_editorial_context(topic: str, limit: int = 3) -> list[dict[str, str]]:
    """Local deterministic retrieval fallback; Phase 7 can replace scoring with Gemini embeddings."""
    cursor = get_database().articles.find({"status": "published", "$or": [{"topic": topic.lower()}, {"tags": topic.lower()}]}, {"slug": 1, "title": 1, "dek": 1, "content_html": 1}).limit(limit)
    sources = []
    async for article in cursor:
        text = re.sub(r"<[^>]+>", " ", article.get("content_html", ""))
        sources.append({"slug": article["slug"], "title": article["title"], "excerpt": (article.get("dek") or text).strip()[:500]})
    return sources
