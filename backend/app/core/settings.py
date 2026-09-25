from functools import lru_cache

from pydantic import Field
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
    gemini_image_model: str = ""
    agent_timeout_seconds: int = 45
    image_timeout_seconds: int = 90
    image_max_bytes: int = 12 * 1024 * 1024
    image_rate_limit_per_minute: int = 4
    image_max_concurrent: int = 3
    image_pending_ttl_hours: int = 24
    agent_max_weight_delta: float = 0.15
    audience_subscriber_count: int = Field(default=0, ge=0)
    audience_subscriber_view_rate: float = Field(default=0.20, ge=0, le=1)
    audience_forecast_min_baseline_stories: int = Field(default=3, ge=1)
    audience_forecast_min_model_stories: int = Field(default=30, ge=3)
    telemetry_retention_days: int = 30
    agent_run_retention_days: int = 90
    audit_retention_days: int = 365
    trends_refresh_enabled: bool = False
    trends_scoring_enabled: bool = False
    trends_refresh_minutes: int = 30
    trends_max_total_adjustment: float = 0.10
    trends_max_age_hours: int = 6
    trends_geo: str = "US"
    trends_sources: str = "google_news,weather,government,wikipedia"
    trends_connector_timeout_seconds: float = 5.0
    trends_max_signals_per_source: int = 50
    trends_lead_intake_enabled: bool = False
    trends_lead_min_strength: float = 0.5
    trends_lead_max_per_refresh: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
