from dataclasses import dataclass

from fastapi import HTTPException, status

from app.core.settings import settings


@dataclass(frozen=True)
class FeatureStatus:
    enabled: bool
    reason: str | None = None


def ai_feature() -> FeatureStatus:
    if settings.llm_provider == "mock" and settings.enable_mock_ai:
        return FeatureStatus(True)
    if settings.llm_provider != "gemini_enterprise":
        return FeatureStatus(False, "Set LLM_PROVIDER=gemini_enterprise and configure Gemini Enterprise, or explicitly set ENABLE_MOCK_AI=true for local fixtures.")
    required = {"GOOGLE_CLOUD_PROJECT": settings.google_cloud_project, "GEMINI_SELECTION_MODEL": settings.gemini_selection_model, "GEMINI_PRODUCTION_MODEL": settings.gemini_production_model, "GEMINI_TELEMETRY_MODEL": settings.gemini_telemetry_model}
    missing = [name for name, value in required.items() if not value]
    credential_hint = "Configure GEMINI_API_KEY or Application Default Credentials."
    return FeatureStatus(not missing, f"Missing AI configuration: {', '.join(missing)}. {credential_hint}" if missing else None)


def storage_feature() -> FeatureStatus:
    required = {"S3_ENDPOINT_URL": settings.s3_endpoint_url, "S3_BUCKET": settings.s3_bucket, "S3_ACCESS_KEY": settings.s3_access_key, "S3_SECRET_KEY": settings.s3_secret_key}
    missing = [name for name, value in required.items() if not value]
    return FeatureStatus(not missing, f"Missing object storage configuration: {', '.join(missing)}" if missing else None)


def require_ai_feature() -> None:
    feature = ai_feature()
    if not feature.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"AI features are disabled. {feature.reason}")


def require_storage_feature() -> None:
    feature = storage_feature()
    if not feature.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Media uploads are disabled. {feature.reason}")
