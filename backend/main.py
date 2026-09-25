from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.settings import settings
from app.core.config import validate_production_configuration
from app.core.features import ai_feature, storage_feature
from app.core.database import ping_mongo
from app.services.bootstrap import ensure_bootstrap_admin, ensure_default_topics
from app.services.users import deactivate_legacy_role_users
from app.middleware.audit import AuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.trends import start_refresh_loop, stop_refresh_loop

logger = logging.getLogger("newsforge.startup")

LOCAL_DEV_CORS_ORIGINS = {
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_configuration()
    for name, feature in {"AI agents": ai_feature(), "media uploads": storage_feature()}.items():
        if not feature.enabled:
            logger.warning("%s disabled: %s", name, feature.reason)
    mongo_connected = await connect_to_mongo()
    if mongo_connected and await ping_mongo():
        migrated_users = await deactivate_legacy_role_users()
        if migrated_users:
            logger.warning("Deactivated and converted %d legacy reporter/audience accounts to editors", migrated_users)
        await ensure_bootstrap_admin()
        await ensure_default_topics()
        start_refresh_loop()
    yield
    await stop_refresh_loop()
    await close_mongo_connection()


app = FastAPI(title="NewsForge API", version="0.1.0", lifespan=lifespan)
app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(
        LOCAL_DEV_CORS_ORIGINS
        | {origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()}
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-NewsForge-Visitor"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)
