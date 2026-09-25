import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.agents.telemetry_agent import (
    process_article_engagement,
    process_public_event,
    rerank_open_leads,
    update_ranking_signal,
)
from app.api.dependencies import require_roles
from app.core.database import get_database
from app.core.settings import settings
from app.models.telemetry import (
    FeedbackRequest,
    FeedbackResponse,
    RankingSignal,
    TelemetrySimulationRequest,
    TelemetrySimulationResponse,
)
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


def actor_key(visitor_id: str | None, request: Request | None = None) -> str:
    """Hash a stable reader identity.

    Browsers send X-NewsForge-Visitor. A client without it must not get a fresh random identity
    per request (that made every view and like count as a new reader), so it is identified by
    network address and user agent instead.
    """
    if visitor_id:
        raw = visitor_id
    else:
        client = request.client.host if request and request.client else "unknown"
        raw = f"anonymous:{client}:{request.headers.get('user-agent', '') if request else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/telemetry/event", status_code=status.HTTP_202_ACCEPTED, tags=["telemetry"])
async def ingest_public_telemetry_event(
    payload: PublicTelemetryEvent,
    request: Request,
    background_tasks: BackgroundTasks,
    x_newsforge_visitor: str | None = Header(default=None),
) -> dict[str, str]:
    """Accept a rate-limited raw reader event without exposing agent controls."""
    await get_database().telemetry_events.insert_one({
        "topic": payload.topic.lower(), "geo": payload.geo, "event_type": payload.event_type,
        "platform": payload.platform, "visitor_key": actor_key(x_newsforge_visitor, request),
        "duration_sec": payload.duration_sec, "timestamp": datetime.now(UTC), "is_simulation": False,
    })
    background_tasks.add_task(process_public_event, payload.topic.lower(), payload.geo, payload.event_type)
    return {"status": "accepted"}


async def published_article_id_or_404(article_id: str) -> ObjectId:
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    object_id = ObjectId(article_id)
    if not await get_database().articles.find_one({"_id": object_id, "status": "published"}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return object_id


@router.post("/articles/{article_id}/view", response_model=FeedbackResponse, tags=["articles"])
async def track_view(
    article_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_newsforge_visitor: str | None = Header(default=None),
) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    metrics = await record_view(resolved_id, actor_key(x_newsforge_visitor, request))
    background_tasks.add_task(process_article_engagement, article_id)
    return FeedbackResponse(article_id=article_id, viewer_action=None, metrics=metrics)


@router.post("/articles/{article_id}/feedback", response_model=FeedbackResponse, tags=["articles"])
async def submit_feedback(
    article_id: str,
    payload: FeedbackRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    x_newsforge_visitor: str | None = Header(default=None),
) -> FeedbackResponse:
    resolved_id = await published_article_id_or_404(article_id)
    viewer_action, metrics = await record_feedback(resolved_id, actor_key(x_newsforge_visitor, request), payload.action)
    background_tasks.add_task(process_article_engagement, article_id)
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
        observation_id=f"simulation:{payload.topic}|{payload.geo}",
        source="simulation",
    )
    return TelemetrySimulationResponse(
        updated_signal=updated_signal,
        affected_leads_count=await rerank_open_leads(),
    )


@router.get("/telemetry/config", tags=["telemetry"])
async def telemetry_config(_: dict = Depends(require_roles(*EDITOR_ROLES))) -> dict[str, float | bool]:
    return {"max_weight_delta": settings.agent_max_weight_delta, "automatic_processing": True}


@router.get("/telemetry/signals", response_model=list[RankingSignal], tags=["telemetry"])
async def list_ranking_signals(
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> list[RankingSignal]:
    cursor = get_database().ranking_signals.find({}).sort("last_updated", -1).limit(100)
    return [RankingSignal.model_validate(signal) async for signal in cursor]
