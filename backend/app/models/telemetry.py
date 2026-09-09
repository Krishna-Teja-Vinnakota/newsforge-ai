from typing import Literal

from pydantic import BaseModel


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
