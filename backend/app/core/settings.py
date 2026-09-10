from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "newsforge"
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_public_base_url: str = ""
    jwt_secret: str = "development-only-change-me"
    jwt_access_token_minutes: int = 30
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_display_name: str = "NewsForge Administrator"
    llm_provider: str = "mock"
    enable_mock_ai: bool = False
    gemini_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gemini_selection_model: str = ""
    gemini_production_model: str = ""
    gemini_telemetry_model: str = ""
    gemini_embedding_model: str = ""
    agent_timeout_seconds: int = 45
    agent_max_weight_delta: float = 0.15
    telemetry_retention_days: int = 30
    agent_run_retention_days: int = 90
    audit_retention_days: int = 365

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
