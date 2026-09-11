import hashlib
import secrets
from datetime import UTC, datetime
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.agents.selection_agent import run_selection
from app.agents.telemetry_agent import update_ranking_signal
from app.api.dependencies import require_roles
from app.core.database import get_database
from app.models.telemetry import (
    FeedbackRequest,
    FeedbackResponse,
    RankingSignal,
    TelemetrySimulationRequest,
    TelemetrySimulationResponse,
)
from app.models.agents import LeadCandidate
from app.models.user import UserRole
from app.services.telemetry import record_feedback, record_view

# Single router instance for all telemetry & article feedback routes
router = APIRouter()
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


class PublicTelemetryEvent(BaseModel):
    topic: str = Field(default="general", max_length=80)
    geo: str = Field(default="global", max_length=120)
    event_type: str = Field(default="view", pattern="^(view|like|save|share)$")
    platform: str = Field(default="web", max_length=40)
    duration_sec: int = Field(default=0, ge=0, le=86400)


def actor_key(visitor_id: str | None) -> str:
    raw = visitor_id or secrets.token_urlsafe(32)
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/telemetry/event", status_code=status.HTTP_202_ACCEPTED, tags=["telemetry"])
async def ingest_public_telemetry_event(payload: PublicTelemetryEvent, x_newsforge_visitor: str | None = Header(default=None)) -> dict[str, str]:
    """Accept a rate-limited raw reader event without exposing agent controls."""
    await get_database().telemetry_events.insert_one({
        "topic": payload.topic.lower(), "geo": payload.geo, "event_type": payload.event_type,
        "platform": payload.platform, "visitor_key": actor_key(x_newsforge_visitor),
        "duration_sec": payload.duration_sec, "timestamp": datetime.now(UTC), "is_simulation": False,
    })
    return {"status": "accepted"}


async def published_article_id_or_404(article_id: str) -> ObjectId:
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    object_id = ObjectId(article_id)
    if not await get_database().articles.find_one({"_id": object_id, "status": "published"}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return object_id


@router.post("/articles/{article_id}/view", response_model=FeedbackResponse, tags=["articles"])
async def track_view(article_id: str, response: Response, x_newsforge_visitor: str | None = Header(default=None)) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    visitor = x_newsforge_visitor or secrets.token_urlsafe(32)
    if not x_newsforge_visitor:
        response.set_cookie("newsforge_visitor", visitor, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    metrics = await record_view(resolved_id, actor_key(visitor))
    return FeedbackResponse(article_id=article_id, viewer_action=None, metrics=metrics)


@router.post("/articles/{article_id}/feedback", response_model=FeedbackResponse, tags=["articles"])
async def submit_feedback(article_id: str, payload: FeedbackRequest, response: Response, x_newsforge_visitor: str | None = Header(default=None)) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    visitor = x_newsforge_visitor or secrets.token_urlsafe(32)
    if not x_newsforge_visitor:
        response.set_cookie("newsforge_visitor", visitor, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax")
    viewer_action, metrics = await record_feedback(resolved_id, actor_key(visitor), payload.action)
    return FeedbackResponse(article_id=article_id, viewer_action=viewer_action, metrics=metrics)


@router.post("/telemetry/simulate", response_model=TelemetrySimulationResponse, tags=["telemetry"])
async def simulate_telemetry(
    payload: TelemetrySimulationRequest,
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> TelemetrySimulationResponse:
    """Create a high-engagement audience spike and run the ranking feedback loop."""
    sample_size = payload.sample_size or 1000
    view_count = round(sample_size * 0.85)
    like_count = round(sample_size * 0.08)
    save_count = round(sample_size * 0.04)
    share_count = sample_size - view_count - like_count - save_count
    simulation_id = f"simulation_{uuid4().hex}"
    timestamp = datetime.now(UTC)
    event_types = (
        [("view", view_count)]
        + [("like", like_count)]
        + [("save", save_count)]
        + [("share", share_count)]
    )
    events = [
        {
            "content_id": simulation_id,
            "topic": payload.topic,
            "geo": payload.geo,
            "event_type": event_type,
            "platform": "web",
            "visitor_key": f"demo_{uuid4().hex}",
            "duration_sec": 180,
            "timestamp": timestamp,
            "is_simulation": True,
        }
        for event_type, count in event_types
        for _ in range(count)
    ]
    await get_database().telemetry_events.insert_many(events)

    updated_signal = await update_ranking_signal(
        payload.topic,
        payload.geo,
        {
            "views": view_count,
            "likes": like_count,
            "saves": save_count,
            "shares": share_count,
            "average_view_duration_seconds": 180,
            "engagement_ratio": 0.9,
        },
    )
    inbox = get_database().lead_inbox
    existing_docs = [document async for document in inbox.find({})]
    candidates = [
        LeadCandidate(
            id=document["lead_id"],
            headline=document["headline"],
            topic=document.get("topic", "general"),
            geo=document.get("geo", "global"),
        )
        for document in existing_docs
    ]
    selection_output = await run_selection(candidates)
    for lead in selection_output.ranked:
        await inbox.update_one(
            {"lead_id": lead.lead_id},
            {"$set": {
                "base_score": lead.base_score,
                "previous_rank": lead.previous_rank,
                "current_rank": lead.current_rank,
                "rank_shift": lead.rank_shift,
                "learned_weight_delta": lead.learned_weight_delta,
                "final_score": lead.final_score,
                "updated_at": datetime.now(UTC),
            }},
        )
    return TelemetrySimulationResponse(
        updated_signal=updated_signal,
        affected_leads_count=len(selection_output.ranked),
    )


@router.get("/telemetry/signals", response_model=list[RankingSignal], tags=["telemetry"])
async def list_ranking_signals(
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> list[RankingSignal]:
    cursor = get_database().ranking_signals.find({}).sort("last_updated", -1).limit(100)
    return [RankingSignal.model_validate(signal) async for signal in cursor]
