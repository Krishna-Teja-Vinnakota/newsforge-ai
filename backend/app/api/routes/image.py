import asyncio
from collections import defaultdict

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.image_agent import PROMPT_VERSION as IMAGE_PROMPT_VERSION, run_image
from app.agents.provider import ImageGenerationError
from app.api.dependencies import require_roles
from app.api.routes.cms import AUTHORING_ROLES, can_edit
from app.core.database import get_database
from app.core.features import require_ai_feature, require_image_feature, require_storage_feature
from app.core.settings import settings
from app.models.agents import AgentName, AgentRunResponse, AgentRunStatus, ImageRunRequest
from app.models.article import ArticleStatus
from app.services.agent_runs import record_run
from app.services.articles import get_article_or_404
from app.services.media_cleanup import sweep_expired_pending_media

router = APIRouter(prefix="/agents/image")

# Generating is only allowed while the story is still being written. Stories in review
# or approved must go back through the editorial workflow before their hero changes.
GENERATABLE_STATUSES = {ArticleStatus.DRAFT, ArticleStatus.REJECTED, ArticleStatus.UNPUBLISHED}

_key_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_in_flight: dict[str, int] = defaultdict(int)


async def _existing_result(user_id: ObjectId, article_id: ObjectId, key: str) -> AgentRunResponse | None:
    media = await get_database().media.find_one({"uploader_id": user_id, "article_id": article_id, "idempotency_key": key})
    if media is None:
        return None
    run_id = media.get("generation_run_id")
    run = await get_database().agent_runs.find_one({"_id": run_id}) if run_id else None
    if run is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This image request is still being processed.")
    return AgentRunResponse(
        id=str(run["_id"]), agent=AgentName.IMAGE, status=AgentRunStatus.SUCCEEDED, output=run["output"], model=run["model"],
        prompt_version=run["prompt_version"], duration_ms=run["duration_ms"], created_at=run["created_at"], used_fallback=run.get("used_fallback", False),
    )


@router.post("", response_model=AgentRunResponse)
async def generate_hero_image(
    payload: ImageRunRequest,
    current_user: dict = Depends(require_roles(*AUTHORING_ROLES)),
    _ai: None = Depends(require_ai_feature),
    _image: None = Depends(require_image_feature),
    _storage: None = Depends(require_storage_feature),
) -> AgentRunResponse:
    article = await get_article_or_404(payload.article_id)
    if not can_edit(article, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot edit this article")
    if article["status"] not in GENERATABLE_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Images can only be generated for drafts, rejected or unpublished stories")

    user_key = str(current_user["_id"])
    lock_key = f"{user_key}:{payload.article_id}:{payload.idempotency_key}"
    async with _key_locks[lock_key]:
        try:
            replay = await _existing_result(current_user["_id"], article["_id"], payload.idempotency_key)
            if replay is not None:
                return replay
            if _in_flight[user_key] >= settings.image_max_concurrent:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many images are being generated. Wait for one to finish.")
            _in_flight[user_key] += 1
            try:
                await sweep_expired_pending_media()
                # Only ids and the idempotency key are stored with the run; the unpublished body is not.
                run_input = {"article_id": payload.article_id, "title": payload.title, "idempotency_key": payload.idempotency_key}
                run = await record_run(
                    AgentName.IMAGE,
                    settings.gemini_image_model or "mock",
                    IMAGE_PROMPT_VERSION,
                    run_input,
                    lambda: run_image(article, payload, current_user["_id"]),
                )
            except ImageGenerationError as error:
                raise HTTPException(status_code=error.status_code, detail=error.user_message) from error
            finally:
                _in_flight[user_key] -= 1
            await get_database().media.update_one({"_id": ObjectId(run.output["hero"]["media_id"])}, {"$set": {"generation_run_id": ObjectId(run.id)}})
            return run
        finally:
            _key_locks.pop(lock_key, None)
