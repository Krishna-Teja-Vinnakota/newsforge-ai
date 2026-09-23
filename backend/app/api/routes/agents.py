from datetime import UTC, datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from app.agents.production_agent import PROMPT_VERSION as PRODUCTION_PROMPT_VERSION, run_production
from app.agents.editing_agent import BODY_PROMPT_VERSION, CHAT_PROMPT_VERSION, DEK_PROMPT_VERSION, HEADLINE_PROMPT_VERSION, TAGS_PROMPT_VERSION, run_body, run_chat, run_dek, run_headline, run_tags
from app.agents.selection_agent import PROMPT_VERSION as SELECTION_PROMPT_VERSION, lead_to_item, run_selection
from app.agents.telemetry_agent import PROMPT_VERSION as TELEMETRY_PROMPT_VERSION, run_telemetry
from app.api.dependencies import require_roles
from app.core.settings import settings
from app.core.features import require_ai_feature
from app.models.agents import AgentName, AgentRunHistoryListResponse, AgentRunHistoryResponse, AgentRunResponse, BodyRunRequest, ChatRunRequest, DekRunRequest, HeadlineRunRequest, LeadDecisionRequest, LeadInboxItem, LeadInput, ProductionRunRequest, SelectionRunRequest, TagSuggestionRunRequest, TelemetryRunRequest
from app.models.agents import AgentRunStatus
from app.models.telemetry import TelemetrySimulationRequest, TelemetrySimulationResponse
from app.models.article import ArticleStatus
from app.core.database import get_database
from app.models.user import UserRole
from app.models.trends import TrendRefreshResponse
from app.services.agent_runs import record_run
from app.services.articles import unique_slug
from app.services.content import sanitize_html
from app.services.trends.refresh import get_trend_status, refresh_trends

router = APIRouter(prefix="/agents")
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


@router.post("/telemetry/simulate", response_model=TelemetrySimulationResponse)
async def simulate_telemetry_agent_alias(
    payload: TelemetrySimulationRequest,
    user: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> TelemetrySimulationResponse:
    from app.api.routes.telemetry import simulate_telemetry
    return await simulate_telemetry(payload, user)

@router.get("/leads", response_model=list[LeadInboxItem])
async def list_leads(_: dict = Depends(require_roles(*EDITOR_ROLES))) -> list[LeadInboxItem]:
    published_lead_ids = [
        article["source_lead_id"]
        async for article in get_database().articles.find(
            {"status": ArticleStatus.PUBLISHED, "source_lead_id": {"$exists": True, "$ne": None}},
            {"source_lead_id": 1},
        )
    ]
    cursor = get_database().lead_inbox.find({"lead_id": {"$nin": published_lead_ids}}).sort([("current_rank", 1), ("final_score", -1), ("updated_at", -1)]).limit(100)
    return [lead_to_item(item) async for item in cursor]


@router.post("/leads/{lead_id}/approve", response_model=LeadInboxItem)
async def approve_lead(lead_id: str, payload: LeadDecisionRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> LeadInboxItem:
    item = await get_database().lead_inbox.find_one_and_update({"lead_id": lead_id}, {"$set": {"status": "approved", "decision_note": payload.note, "updated_at": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead_to_item(item)


@router.post("/leads/{lead_id}/reject", response_model=LeadInboxItem)
async def reject_lead(lead_id: str, payload: LeadDecisionRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> LeadInboxItem:
    item = await get_database().lead_inbox.find_one_and_update({"lead_id": lead_id}, {"$set": {"status": "rejected", "decision_note": payload.note, "updated_at": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead_to_item(item)


@router.post("/trends/refresh", response_model=TrendRefreshResponse)
async def manual_trend_refresh(
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> TrendRefreshResponse:
    return await refresh_trends()


@router.get("/trends/status", response_model=TrendRefreshResponse)
async def trend_status(
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> TrendRefreshResponse:
    return await get_trend_status()


@router.get("/runs", response_model=AgentRunHistoryListResponse)
async def list_agent_runs(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50),
    agent: AgentName | None = None, run_status: AgentRunStatus | None = Query(default=None, alias="status"),
    _: dict = Depends(require_roles(*EDITOR_ROLES)),
) -> AgentRunHistoryListResponse:
    criteria: dict = {}
    if agent:
        criteria["agent"] = agent
    if run_status:
        criteria["status"] = run_status
    collection = get_database().agent_runs
    total = await collection.count_documents(criteria)
    cursor = collection.find(criteria).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    items = [AgentRunHistoryResponse(id=str(item["_id"]), agent=item["agent"], status=item["status"], output=item.get("output", {}), input=item.get("input", {}), error=item.get("error"), model=item["model"], prompt_version=item["prompt_version"], duration_ms=item["duration_ms"], created_at=item["created_at"]) async for item in cursor]
    return AgentRunHistoryListResponse(items=items, total=total)


@router.post("/runs/{run_id}/retry", response_model=AgentRunResponse)
async def retry_agent_run(run_id: str, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    """Re-run a prior, auditable agent input without silently changing it."""
    if not ObjectId.is_valid(run_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    previous = await get_database().agent_runs.find_one({"_id": ObjectId(run_id)})
    if previous is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    agent = AgentName(previous["agent"])
    payload = previous.get("input", {})
    if agent is AgentName.SELECTION:
        request = SelectionRunRequest.model_validate(payload)
        return await selection_run(request, _)
    if agent is AgentName.PRODUCTION:
        request = ProductionRunRequest.model_validate(payload)
        return await production_run(request, _)
    if agent is AgentName.HEADLINE:
        return await headline_run(HeadlineRunRequest.model_validate(payload), _)
    if agent is AgentName.DEK:
        return await dek_run(DekRunRequest.model_validate(payload), _)
    if agent is AgentName.BODY:
        return await body_run(BodyRunRequest.model_validate(payload), _)
    if agent is AgentName.TAGS:
        return await tag_suggestion_run(TagSuggestionRunRequest.model_validate(payload), _)
    if agent is AgentName.CHAT:
        return await chat_run(ChatRunRequest.model_validate(payload), _)
    request = TelemetryRunRequest.model_validate(payload)
    return await telemetry_run(request, _)


@router.post("/selection/run", response_model=AgentRunResponse)
async def selection_run(payload: SelectionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    leads = payload.leads
    if not leads:
        cursor = get_database().lead_inbox.find({}).sort([("current_rank", 1), ("updated_at", -1)]).limit(25)
        leads = [
            LeadInput(
                id=document["lead_id"],
                headline=document["headline"],
                topic=document.get("topic", "general"),
                geo=document.get("geo", "global"),
                source_url=document.get("source_url"),
                published_at=document.get("published_at"),
            )
            async for document in cursor
        ]
    if not leads:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No leads are available to rank")
    selection_payload = SelectionRunRequest(leads=leads)
    run = await record_run(AgentName.SELECTION, settings.gemini_selection_model or "mock", SELECTION_PROMPT_VERSION, selection_payload.model_dump(mode="json"), lambda: run_selection(leads))
    return run


@router.post("/produce", response_model=AgentRunResponse)
async def production_run(payload: ProductionRunRequest, current_user: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    run = await record_run(
        AgentName.PRODUCTION,
        settings.gemini_production_model or "mock",
        PRODUCTION_PROMPT_VERSION,
        payload.model_dump(),
        lambda: run_production(payload.headline, payload.topic, payload.context, payload.target_platforms, payload.tone),
    )
    output = run.output
    now = datetime.now(UTC)
    title = str(output.get("title") or payload.headline)
    content_html = sanitize_html(str(output.get("content_html", "")))
    retrieved_sources = [
        {"id": source_id, "slug": source_slug}
        for source_id, source_slug in zip(output.get("retrieved_source_ids", []), output.get("retrieved_source_slugs", []), strict=False)
    ]
    ai_insights = {
        "reporter_brief": output.get("reporter_brief", {}),
        "social_posts": output.get("social_posts", []),
        "push_notification": output.get("push_notification", ""),
        "provenance": output.get("provenance", []),
        "model_name": settings.gemini_production_model or "mock",
        "generated_at": now,
    }

    # Enhancing an existing story is deliberately generation-only.  The
    # editor presents the result as a proposal and is the only client allowed
    # to persist a human-approved change through the CMS update endpoint.
    # Lead drafting remains an intentional creation workflow used by AI Desk.
    if payload.article_id:
        if not ObjectId.is_valid(payload.article_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        existing = await get_database().articles.find_one({"_id": ObjectId(payload.article_id)})
        if not existing or existing["status"] == ArticleStatus.PUBLISHED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose an editable draft story")
        if existing["creator_id"] != current_user["_id"] and current_user["role"] not in EDITOR_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot enhance this story")
        run.output["ai_insights"] = ai_insights
        await get_database().agent_runs.update_one({"_id": ObjectId(run.id)}, {"$set": {"output.ai_insights": ai_insights}})
        return run

    document = {
        "title": title,
        "slug": await unique_slug(title),
        "summary": output.get("dek", ""),
        "content": content_html,
        "dek": output.get("dek", ""),
        "content_html": content_html,
        "content_json": output.get("content_json", {}),
        "topic": payload.topic,
        "tags": ["ai-assisted"],
        "status": ArticleStatus.DRAFT,
        "source_lead_id": payload.source_lead_id,
        "creator_id": current_user["_id"],
        "editor_id": None,
        "hero_media_id": None,
        "hero_url": output.get("hero_url"),
        "ai_insights": ai_insights,
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "scheduled_for": None,
        "prompt_version": PRODUCTION_PROMPT_VERSION,
        "model_name": settings.gemini_production_model or "mock",
        "retrieved_sources": retrieved_sources,
        "metrics": {"views": 0, "likes": 0, "dislikes": 0, "engagement_ratio": 0, "popularity_score": 0, "seo_score": None},
    }
    existing = None
    if payload.source_lead_id:
        existing = await get_database().articles.find_one({"source_lead_id": payload.source_lead_id, "status": ArticleStatus.DRAFT})
    if existing:
        document["slug"] = await unique_slug(title, existing["_id"])
        document["created_at"] = existing["created_at"]
        document["source_lead_id"] = existing.get("source_lead_id")
        document["creator_id"] = existing["creator_id"]
        await get_database().articles.update_one({"_id": existing["_id"]}, {"$set": document})
        article_id = existing["_id"]
    else:
        inserted = await get_database().articles.insert_one(document)
        article_id = inserted.inserted_id
    article = {"id": str(article_id), "title": title, "slug": document["slug"], "dek": document["dek"], "content_html": document["content_html"], "content_json": document["content_json"], "topic": document["topic"], "status": "draft", "source_lead_id": document["source_lead_id"]}
    run.output["article"] = article
    await get_database().agent_runs.update_one({"_id": ObjectId(run.id)}, {"$set": {"output.article": article}})
    if payload.source_lead_id:
        await get_database().lead_inbox.update_one({"lead_id": payload.source_lead_id}, {"$set": {"status": "approved", "updated_at": now}})
    return run


@router.post("/headline", response_model=AgentRunResponse)
async def headline_run(payload: HeadlineRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.HEADLINE, settings.gemini_production_model or "mock", HEADLINE_PROMPT_VERSION, payload.model_dump(), lambda: run_headline(payload.title, payload.topic, payload.context, payload.mode))


@router.post("/dek", response_model=AgentRunResponse)
async def dek_run(payload: DekRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.DEK, settings.gemini_production_model or "mock", DEK_PROMPT_VERSION, payload.model_dump(), lambda: run_dek(payload.dek, payload.title, payload.context, payload.mode))


@router.post("/body", response_model=AgentRunResponse)
async def body_run(payload: BodyRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.BODY, settings.gemini_production_model or "mock", BODY_PROMPT_VERSION, payload.model_dump(), lambda: run_body(payload.content_html, payload.title, payload.dek, payload.notes, payload.mode))


@router.post("/chat", response_model=AgentRunResponse)
async def chat_run(payload: ChatRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.CHAT, settings.gemini_production_model or "mock", CHAT_PROMPT_VERSION, payload.model_dump(), lambda: run_chat(payload.title, payload.dek, payload.content_html, payload.history, payload.message))


@router.post("/tags", response_model=AgentRunResponse)
async def tag_suggestion_run(payload: TagSuggestionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.TAGS, settings.gemini_production_model or "mock", TAGS_PROMPT_VERSION, payload.model_dump(), lambda: run_tags(payload.title, payload.dek, payload.content_html, payload.topic, payload.existing_tags))


@router.post("/telemetry/recalculate", response_model=AgentRunResponse)
async def telemetry_run(payload: TelemetryRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.TELEMETRY, settings.gemini_telemetry_model or "mock", TELEMETRY_PROMPT_VERSION, payload.model_dump(), lambda: run_telemetry(payload.article_id))
