from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TrendSignal(BaseModel):
    """A cached external observation used as deterministic ranking evidence."""

    topic_id: str
    label: str
    source: str
    geo: str
    country_code: str | None = None
    interest_score: float = Field(ge=0)
    velocity: float = Field(default=1.0, ge=0)
    rank: int | None = Field(default=None, ge=1)
    observed_at: datetime
    fetched_at: datetime
    expires_at: datetime
    source_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def signal_id(self) -> str:
        return f"{self.topic_id}|{self.source}|{self.geo}"


class ConnectorResult(BaseModel):
    source: str
    geo: str
    status: Literal["success", "success_empty", "failed"]
    signals: list[TrendSignal] = Field(default_factory=list)
    processed_count: int | None = None
    error_code: str | None = None


class TrendSourceStatus(BaseModel):
    source: str
    geo: str
    status: str
    count: int = 0
    duration_ms: int = 0
    last_success_at: datetime | None = None
    error_code: str | None = None
    next_refresh_at: datetime | None = None


class TrendRefreshResponse(BaseModel):
    status: str
    sources: list[TrendSourceStatus] = Field(default_factory=list)
