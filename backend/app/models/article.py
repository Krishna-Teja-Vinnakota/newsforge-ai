from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.user import UserRole


class ArticleStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


class ArticleCreateRequest(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    dek: str = Field(default="", max_length=400)
    content_json: dict[str, Any] = Field(default_factory=dict)
    content_html: str = ""
    topic: str = Field(default="general", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=10)
    hero_media_id: str | None = None
    hero_url: str | None = Field(default=None, max_length=2000)


class ArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=180)
    dek: str | None = Field(default=None, max_length=400)
    content_json: dict[str, Any] | None = None
    content_html: str | None = None
    topic: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=10)
    hero_media_id: str | None = None
    hero_url: str | None = Field(default=None, max_length=2000)
    ai_insights: dict[str, Any] | None = None


class ArticleAuthor(BaseModel):
    id: str
    display_name: str
    avatar_url: str | None = None


class ArticleResponse(BaseModel):
    id: str
    slug: str
    status: ArticleStatus
    title: str
    dek: str
    content_json: dict[str, Any]
    content_html: str
    topic: str
    tags: list[str]
    hero_media_id: str | None = None
    hero_url: str | None = None
    ai_insights: dict[str, Any] | None = None
    creator: ArticleAuthor
    editor: ArticleAuthor | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    scheduled_for: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    page: int
    page_size: int
    total: int


class ArticleNeighborsResponse(BaseModel):
    previous: ArticleResponse | None = None
    next: ArticleResponse | None = None


class WorkflowTransitionRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class PublishRequest(WorkflowTransitionRequest):
    scheduled_for: datetime | None = None
