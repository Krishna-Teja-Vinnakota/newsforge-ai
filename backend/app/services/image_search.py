import logging

import httpx

logger = logging.getLogger("uvicorn.error")

WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_REQUEST_TIMEOUT_SECONDS = 4.0


async def find_topical_image_url(headline: str, topic: str) -> str | None:
    """Look up a freely licensed, topic-relevant photo from Wikipedia.

    Wikipedia's API is unauthenticated and CC-licensed, which makes it a safe
    default source for an editorial hero image. Any failure (network, no
    match, no usable thumbnail) returns None so the caller can fall back to
    the generated SVG hero instead of breaking story production.
    """
    query = f"{headline} {topic}".strip()
    if not query:
        return None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            search_response = await client.get(
                WIKIPEDIA_SEARCH_URL,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 3,
                    "format": "json",
                },
                headers={"User-Agent": "NewsForgeAI/1.0 (editorial hero image lookup)"},
            )
            search_response.raise_for_status()
            hits = search_response.json().get("query", {}).get("search", [])
            if not hits:
                return None
            for hit in hits:
                title = hit.get("title")
                if not title:
                    continue
                image_response = await client.get(
                    WIKIPEDIA_SEARCH_URL,
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "pageimages",
                        "pithumbsize": 1200,
                        "format": "json",
                    },
                    headers={"User-Agent": "NewsForgeAI/1.0 (editorial hero image lookup)"},
                )
                image_response.raise_for_status()
                pages = image_response.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    thumbnail_url = page.get("thumbnail", {}).get("source")
                    if thumbnail_url:
                        return thumbnail_url
            return None
    except Exception as error:  # noqa: BLE001 - image lookup must never break drafting
        logger.warning("Topical image lookup failed for %r: %s", query, error)
        return None
