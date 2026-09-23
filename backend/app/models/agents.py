from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AgentName(StrEnum):
    SELECTION = "selection"
    PRODUCTION = "production"
    TELEMETRY = "telemetry"
    HEADLINE = "headline"
    DEK = "dek"
    BODY = "body"
    TAGS = "tags"
    CHAT = "chat"


class AgentRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LeadInput(BaseModel):
    id: str
    headline: str
    topic: str = "general"
    geo: str = "global"
    source_url: str | None = None
    source_context: str | None = None
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
    trend_boost: float = 0.0
    coverage_adjustment: float = 0.0
    trend_evidence: list[dict[str, Any]] = Field(default_factory=list)
    suggested_format: str = "standard"
    why_now: str | None = None
    origin: str = "manual"


class LeadDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class LeadInboxItem(Lead):
    status: str = "pending"
    priority_score: float | None = None
    suggested_angle: str | None = None
    reasoning: str | None = None
    score_audit: dict[str, Any] = Field(default_factory=dict)


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
    trend_boost: float = 0.0
    coverage_adjustment: float = 0.0
    trend_evidence: list[dict[str, Any]] = Field(default_factory=list)
    suggested_format: str = "standard"
    why_now: str | None = None
    suggested_angle: str
    suggested_publish_window: str
    reasoning: str
    score_audit: dict[str, Any] = Field(default_factory=dict)


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
    article_id: str | None = None
    tone: Literal["formal", "conversational", "urgent"] | None = None


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
    hero_url: str = ""

    @field_validator("content_json", mode="before")
    @classmethod
    def normalize_tiptap_content(cls, value: Any) -> dict[str, Any]:
        # Gemini sometimes returns the Tiptap block list directly instead of
        # wrapping it in the document object expected by the editor.
        if isinstance(value, list):
            return {"type": "doc", "content": value}
        return value

    @field_validator("reporter_brief", mode="before")
    @classmethod
    def normalize_reporter_brief(cls, value: Any) -> dict[str, list[str] | str]:
        if isinstance(value, str):
            return {"background": value, "key_questions": [], "shot_list": []}
        return value

    @field_validator("social_posts", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [str(item) for item in value.values() if item]
        if isinstance(value, list):
            # Gemini sometimes returns social posts as {platform, text} objects
            # instead of plain strings; keep only the human-readable copy.
            return [
                str(item.get("text") or item.get("copy") or item.get("post") or item)
                if isinstance(item, dict)
                else str(item)
                for item in value
            ]
        return value

    @field_validator("provenance", mode="before")
    @classmethod
    def normalize_provenance(cls, value: Any) -> list[str]:
        def expand(entry: Any) -> list[str]:
            if isinstance(entry, dict) and ("claims" in entry or "note" in entry):
                # Gemini sometimes returns a single {confidence, claims, note}
                # object instead of plain strings; surface the readable parts
                # (the claims needing verification and the note) and drop the
                # bare confidence score.
                items = [str(claim) for claim in entry.get("claims") or [] if claim]
                if entry.get("note"):
                    items.append(str(entry["note"]))
                return items
            if isinstance(entry, dict):
                return [str(item) for item in entry.values() if item]
            return [str(entry)]

        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return expand(value)
        if isinstance(value, list):
            return [item for entry in value for item in expand(entry)]
        return value


class HeadlineRunRequest(BaseModel):
    title: str = Field(default="", max_length=180)
    topic: str = Field(default="general", max_length=80)
    context: str = Field(default="", max_length=12000)
    mode: Literal["generate", "grammar", "options"]


class HeadlineResult(BaseModel):
    title: str
    options: list[str] = Field(default_factory=list)


class DekRunRequest(BaseModel):
    dek: str = Field(default="", max_length=400)
    title: str = Field(min_length=5, max_length=180)
    context: str = Field(default="", max_length=12000)
    mode: Literal["generate", "grammar"]


class DekResult(BaseModel):
    dek: str


class BodyRunRequest(BaseModel):
    content_html: str = Field(default="", max_length=50000)
    title: str = Field(min_length=5, max_length=180)
    dek: str = Field(default="", max_length=400)
    notes: str = Field(default="", max_length=12000)
    mode: Literal["rewrite", "notes_to_story", "grammar"]


class BodyResult(BaseModel):
    content_html: str
    content_json: dict[str, Any]

    @field_validator("content_json", mode="before")
    @classmethod
    def normalize_tiptap_content(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, list):
            return {"type": "doc", "content": value}
        return value


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRunRequest(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    dek: str = Field(default="", max_length=400)
    content_html: str = Field(default="", max_length=50000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)
    message: str = Field(min_length=1, max_length=4000)


class ChatResult(BaseModel):
    reply: str
    title: str | None = None
    dek: str | None = None
    content_html: str | None = None


class TagSuggestionRunRequest(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    dek: str = Field(default="", max_length=400)
    content_html: str = Field(default="", max_length=50000)
    topic: str = Field(default="general", max_length=80)
    existing_tags: list[str] = Field(default_factory=list, max_length=10)


class TagSuggestionResult(BaseModel):
    suggested_tags: list[str] = Field(default_factory=list, max_length=8)


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
