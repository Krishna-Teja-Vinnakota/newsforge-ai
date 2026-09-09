import logging
from datetime import UTC, datetime

from app.core.database import get_database
from app.core.security import hash_password
from app.core.settings import settings
from app.services.users import new_user_document

logger = logging.getLogger("newsforge.bootstrap")


async def ensure_bootstrap_admin() -> None:
    """Create the configured local administrator once, without overwriting it."""
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        logger.warning("Bootstrap admin skipped: BOOTSTRAP_ADMIN_EMAIL or BOOTSTRAP_ADMIN_PASSWORD is not configured")
        return
    email = settings.bootstrap_admin_email.lower()
    existing = await get_database().users.find_one({"email": email})
    if existing:
        logger.info("Bootstrap admin already exists: %s", email)
        return
    document = new_user_document(
        email=email,
        password_hash=hash_password(settings.bootstrap_admin_password),
        display_name=settings.bootstrap_admin_display_name,
        role="admin",
    )
    await get_database().users.insert_one(document)
    logger.warning("Created bootstrap administrator: %s", email)


async def ensure_default_topics() -> None:
    database = get_database()
    for name, slug in [("Cities", "cities"), ("Culture", "culture"), ("Climate", "climate"), ("Technology", "technology"), ("Design", "design"), ("Community", "community")]:
        await database.topics.update_one({"slug": slug}, {"$setOnInsert": {"name": name, "slug": slug, "is_active": True, "created_at": datetime.now(UTC)}}, upsert=True)
