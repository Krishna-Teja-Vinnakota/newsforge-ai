import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter

from bson import ObjectId

from app.agents.prompts.image import PROMPT_VERSION, build_image_brief_prompt
from app.agents.provider import get_provider
from app.core.database import get_database
from app.core.settings import settings
from app.core.storage import upload_public_object
from app.models.agents import HeroProposal, ImageBrief, ImageResult, ImageRunRequest
from app.services.agent_metrics import record_agent_metrics
from app.services.image_compose import DISCLOSURE, compose_hero
from app.services.image_prompt import apply_policy, build_image_prompt, fallback_brief, plain_text, source_hash

BODY_CHAR_BUDGET = 8000

__all__ = ["PROMPT_VERSION", "run_image"]


def cached_brief(article: dict, digest: str) -> ImageBrief | None:
    """Reuse the brief written with the draft only if it was written for exactly this text."""
    stored = ((article.get("ai_insights") or {}).get("image_brief")) or None
    if not stored or stored.get("source_hash") != digest:
        return None
    try:
        return ImageBrief.model_validate(stored)
    except ValueError:
        return None


async def generate_brief(request: ImageRunRequest, digest: str, topic: str) -> ImageBrief:
    body = plain_text(request.content_html)[:BODY_CHAR_BUDGET]
    prompt = build_image_brief_prompt(request.title, request.dek, body)
    started = perf_counter()
    brief = await get_provider().generate_json(
        model=settings.gemini_production_model,
        prompt=prompt,
        schema=ImageBrief,
        fallback=fallback_brief(request.title, topic).model_dump(mode="json"),
    )
    await record_agent_metrics("image_brief", settings.gemini_production_model or "mock", "image brief", brief.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    # The hash is server-controlled: the model cannot claim its brief matches other content.
    return brief.model_copy(update={"source_hash": digest})


async def run_image(article: dict, request: ImageRunRequest, user_id: ObjectId) -> ImageResult:
    """Brief -> policy -> image model -> disclosure strip -> storage. Returns a proposal; the article is untouched."""
    started = perf_counter()
    topic = article.get("topic", "")
    digest = source_hash(request.title, request.dek, request.content_html)
    brief = cached_brief(article, digest) or await generate_brief(request, digest, topic)
    brief = apply_policy(brief, title=request.title, topic=topic)
    prompt = build_image_prompt(brief)

    generated = await get_provider().generate_image(model=settings.gemini_image_model, prompt=prompt, aspect_ratio="16:9")
    composed = await asyncio.to_thread(compose_hero, generated, max_bytes=settings.image_max_bytes)
    object_key, url = await upload_public_object(composed.data, composed.content_type, "ai-hero.jpg")

    now = datetime.now(UTC)
    media = {
        "object_key": object_key,
        "url": url,
        "content_type": composed.content_type,
        "size_bytes": len(composed.data),
        "purpose": "hero",
        "uploader_id": user_id,
        "created_at": now,
        "ai_generated": True,
        "ai_model": settings.gemini_image_model or "mock",
        "alt_text": brief.alt_text,
        "disclosure": DISCLOSURE,
        "source_hash": digest,
        "brief": brief.model_dump(mode="json"),
        "article_id": article["_id"],
        "idempotency_key": request.idempotency_key,
        "status": "pending",
        "expires_at": now + timedelta(hours=settings.image_pending_ttl_hours),
    }
    inserted = await get_database().media.insert_one(media)
    await record_agent_metrics("image", settings.gemini_image_model or "mock", prompt, {"bytes": len(composed.data)}, int((perf_counter() - started) * 1000))
    hero = HeroProposal(url=url, media_id=str(inserted.inserted_id), alt_text=brief.alt_text, ai_generated=True, disclosure=DISCLOSURE)
    return ImageResult(hero=hero, brief=brief)
