from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RankingSignal(BaseModel):
    """Learned ranking adjustment for a topic and geography pair."""

    model_config = ConfigDict(populate_by_name=True)

    # MongoDB stores this composite key in `_id`; the API exposes its clearer name.
    topic_geo_key: str = Field(validation_alias="_id")
    topic: str
    geo: str
    weight_delta: float
    sample_size: int
    confidence: float
    last_updated: datetime


class TelemetrySimulationRequest(BaseModel):
    """Inputs used to model a high-engagement audience spike for a live demo."""

    topic: str
    geo: str
    sample_size: int | None = Field(default=1000, ge=1, le=10_000)


class TelemetrySimulationResponse(BaseModel):
    status: Literal["success"] = "success"
    updated_signal: RankingSignal
    affected_leads_count: int


class FeedbackRequest(BaseModel):
    action: Literal["like", "dislike"]


class ArticleMetrics(BaseModel):
    views: int
    likes: int
    dislikes: int
    engagement_ratio: float
    popularity_score: float


class FeedbackResponse(BaseModel):
    article_id: str
    viewer_action: Literal["like", "dislike"] | None
    metrics: ArticleMetrics
