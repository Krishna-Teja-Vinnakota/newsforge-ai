"""Production-only configuration validation for secrets and external services."""

import os

from app.core.settings import settings
from app.core.security import DEFAULT_JWT_SECRET, uses_development_jwt_secret


def validate_production_configuration() -> None:
    """Fail fast when a production process relies on development configuration."""
    environment = os.getenv("ENVIRONMENT", settings.app_env).lower()
    if environment != "production":
        return
    required = {
        "JWT_SECRET": os.getenv("JWT_SECRET"),
        "MONGODB_URI or MONGO_URI": os.getenv("MONGODB_URI") or os.getenv("MONGO_URI"),
    }
    if settings.llm_provider == "gemini_enterprise":
        required["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")
        required["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")
    missing = [name for name, value in required.items() if not value]
    if uses_development_jwt_secret(os.getenv("JWT_SECRET")):
        missing.append("JWT_SECRET must not use the development default")
    if missing:
        raise RuntimeError(f"Production configuration is incomplete: {', '.join(missing)}")
