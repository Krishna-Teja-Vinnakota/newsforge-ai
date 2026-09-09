import asyncio

from fastapi import APIRouter

from app.core.database import ping_mongo
from app.core.storage import ping_storage
from app.core.features import ai_feature, storage_feature
from app.models.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    mongo_ready, storage_ready = await asyncio.gather(ping_mongo(), ping_storage())
    ai, storage = ai_feature(), storage_feature()
    return HealthResponse(
        status="ok" if mongo_ready else "degraded",
        services={"mongodb": mongo_ready, "object_storage": storage_ready},
        features={"ai_agents": ai.enabled, "media_uploads": storage.enabled and storage_ready},
    )
