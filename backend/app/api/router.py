from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.topics import router as topics_router
from app.api.routes.tags import router as tags_router
from app.api.routes.media import router as media_router
from app.api.routes.articles import router as articles_router
from app.api.routes.cms import router as cms_router
from app.api.routes.telemetry import router as telemetry_router
from app.api.routes.agents import router as agents_router
from app.api.routes.image import router as image_router
from app.api.routes.admin import router as admin_router
from app.api.routes.workflow import router as workflow_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(topics_router, tags=["topics"])
api_router.include_router(tags_router, tags=["tags"])
api_router.include_router(media_router, tags=["media"])
api_router.include_router(articles_router, tags=["articles"])
api_router.include_router(cms_router, tags=["cms"])
api_router.include_router(telemetry_router)
api_router.include_router(agents_router, tags=["agents"])
api_router.include_router(image_router, tags=["agents"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(workflow_router, tags=["workflow"])
