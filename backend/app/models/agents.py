from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentName(StrEnum):
    SELECTION = "selection"
    PRODUCTION = "production"
    TELEMETRY = "telemetry"


class AgentRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LeadInput(BaseModel):
    id: str
    headline: str
    topic: str = "general"
    geo: str = "global"
    source_url: str | None = None
    published_at: datetime | None = None


class LeadCandidate(LeadInput):
    """A lead selected from the persisted editorial inbox for ranking."""


class Lead(LeadInput):
    """A candidate lead with its closed-loop ranking state."""

    base_score: float = 0.0
    learned_weight_delta: float = 0.0
    final_score: float = 0.0
    previous_rank: int | None = None
    current_rank: int | None = None
    rank_shift: int = 0


class LeadDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class LeadInboxItem(Lead):
    status: str = "pending"
    priority_score: float | None = None
    suggested_angle: str | None = None
    reasoning: str | None = None


class RankedLead(BaseModel):
    lead_id: str
    headline: str
    priority_score: float = Field(ge=0, le=1)
    base_score: float = 0.0
    learned_weight_delta: float = 0.0
    final_score: float = 0.0
    previous_rank: int | None = None
    current_rank: int | None = None
    rank_shift: int = 0
    suggested_angle: str
    suggested_publish_window: str
    reasoning: str


class SelectionResult(BaseModel):
    ranked: list[RankedLead]


class SelectionRunRequest(BaseModel):
    leads: list[LeadInput] = Field(default_factory=list, max_length=25)


class ProductionRunRequest(BaseModel):
    headline: str = Field(min_length=5, max_length=180)
    topic: str = Field(default="general", max_length=80)
    context: str = Field(default="", max_length=12000)
    target_platforms: list[str] = Field(default_factory=lambda: ["web", "social", "push"])
    source_lead_id: str | None = None


class ProductionResult(BaseModel):
    title: str
    dek: str
    content_json: dict[str, Any]
    content_html: str
    reporter_brief: dict[str, list[str] | str]
    social_posts: list[str]
    push_notification: str
    provenance: list[str] = Field(default_factory=list)
    retrieved_source_ids: list[str] = Field(default_factory=list)
    retrieved_source_slugs: list[str] = Field(default_factory=list)


class TelemetryRunRequest(BaseModel):
    article_id: str


class TelemetryResult(BaseModel):
    article_id: str
    topic: str
    engagement_score: float = Field(ge=0, le=1)
    popularity_rank_hint: float = Field(ge=0)
    weight_delta: float = Field(ge=-0.15, le=0.15)
    insight: str
    seo_recommendations: list[str]


class AgentRunResponse(BaseModel):
    id: str
    agent: AgentName
    status: AgentRunStatus
    output: dict[str, Any]
    model: str
    prompt_version: str
    duration_ms: int
    created_at: datetime


class AgentRunHistoryResponse(AgentRunResponse):
    input: dict[str, Any]
    error: str | None = None


class AgentRunHistoryListResponse(BaseModel):
    items: list[AgentRunHistoryResponse]
    total: int
