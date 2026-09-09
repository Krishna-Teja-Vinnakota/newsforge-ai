import hashlib
import secrets

from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException, Response, status

from app.core.database import get_database
from app.models.telemetry import FeedbackRequest, FeedbackResponse
from app.services.telemetry import metrics_from_article, record_feedback, record_view

router = APIRouter(prefix="/articles")


def actor_key(visitor_id: str | None) -> str:
    raw = visitor_id or secrets.token_urlsafe(32)
    return hashlib.sha256(raw.encode()).hexdigest()


async def published_article_id_or_404(article_id: str) -> ObjectId:
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    object_id = ObjectId(article_id)
    if not await get_database().articles.find_one({"_id": object_id, "status": "published"}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return object_id


@router.post("/{article_id}/view", response_model=FeedbackResponse)
async def track_view(article_id: str, response: Response, x_newsforge_visitor: str | None = Header(default=None)) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    visitor = x_newsforge_visitor or secrets.token_urlsafe(32)
    if not x_newsforge_visitor:
        response.set_cookie("newsforge_visitor", visitor, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    metrics = await record_view(resolved_id, actor_key(visitor))
    return FeedbackResponse(article_id=article_id, viewer_action=None, metrics=metrics)


@router.post("/{article_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(article_id: str, payload: FeedbackRequest, response: Response, x_newsforge_visitor: str | None = Header(default=None)) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    visitor = x_newsforge_visitor or secrets.token_urlsafe(32)
    if not x_newsforge_visitor:
        response.set_cookie("newsforge_visitor", visitor, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    viewer_action, metrics = await record_feedback(resolved_id, actor_key(visitor), payload.action)
    return FeedbackResponse(article_id=article_id, viewer_action=viewer_action, metrics=metrics)
