from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.settings import settings
from app.core.features import ai_feature, storage_feature
from app.core.database import ping_mongo
from app.services.bootstrap import ensure_bootstrap_admin, ensure_default_topics

logger = logging.getLogger("newsforge.startup")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for name, feature in {"AI agents": ai_feature(), "media uploads": storage_feature()}.items():
        if not feature.enabled:
            logger.warning("%s disabled: %s", name, feature.reason)
    mongo_connected = await connect_to_mongo()
    if mongo_connected and await ping_mongo():
        await ensure_bootstrap_admin()
        await ensure_default_topics()
    yield
    await close_mongo_connection()


app = FastAPI(title="NewsForge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-NewsForge-Visitor"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
