from datetime import UTC, datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from app.agents.production_agent import PROMPT_VERSION as PRODUCTION_PROMPT_VERSION, run_production
from app.agents.selection_agent import PROMPT_VERSION as SELECTION_PROMPT_VERSION, run_selection
from app.agents.telemetry_agent import PROMPT_VERSION as TELEMETRY_PROMPT_VERSION, run_telemetry
from app.api.dependencies import require_roles
from app.core.settings import settings
from app.core.features import require_ai_feature
from app.models.agents import AgentName, AgentRunHistoryListResponse, AgentRunHistoryResponse, AgentRunResponse, LeadDecisionRequest, LeadInboxItem, ProductionRunRequest, SelectionRunRequest, TelemetryRunRequest
from app.models.agents import AgentRunStatus
from app.core.database import get_database
from app.models.user import UserRole
from app.services.agent_runs import record_run

router = APIRouter(prefix="/agents")
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


@router.get("/leads", response_model=list[LeadInboxItem])
async def list_leads(_: dict = Depends(require_roles(*EDITOR_ROLES))) -> list[LeadInboxItem]:
    cursor = get_database().lead_inbox.find({}).sort("updated_at", -1).limit(100)
    return [LeadInboxItem(id=item["lead_id"], headline=item["headline"], topic=item.get("topic", "general"), geo=item.get("geo", "global"), source_url=item.get("source_url"), published_at=item.get("published_at"), status=item.get("status", "pending"), priority_score=item.get("priority_score"), suggested_angle=item.get("suggested_angle"), reasoning=item.get("reasoning")) async for item in cursor]


@router.post("/leads/{lead_id}/approve", response_model=LeadInboxItem)
async def approve_lead(lead_id: str, payload: LeadDecisionRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> LeadInboxItem:
    item = await get_database().lead_inbox.find_one_and_update({"lead_id": lead_id}, {"$set": {"status": "approved", "decision_note": payload.note, "updated_at": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return LeadInboxItem(id=item["lead_id"], headline=item["headline"], topic=item.get("topic", "general"), geo=item.get("geo", "global"), source_url=item.get("source_url"), published_at=item.get("published_at"), status="approved", priority_score=item.get("priority_score"), suggested_angle=item.get("suggested_angle"), reasoning=item.get("reasoning"))


@router.post("/leads/{lead_id}/reject", response_model=LeadInboxItem)
async def reject_lead(lead_id: str, payload: LeadDecisionRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> LeadInboxItem:
    item = await get_database().lead_inbox.find_one_and_update({"lead_id": lead_id}, {"$set": {"status": "rejected", "decision_note": payload.note, "updated_at": datetime.now(UTC)}}, return_document=ReturnDocument.AFTER)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return LeadInboxItem(id=item["lead_id"], headline=item["headline"], topic=item.get("topic", "general"), geo=item.get("geo", "global"), source_url=item.get("source_url"), published_at=item.get("published_at"), status="rejected", priority_score=item.get("priority_score"), suggested_angle=item.get("suggested_angle"), reasoning=item.get("reasoning"))


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
    request = TelemetryRunRequest.model_validate(payload)
    return await telemetry_run(request, _)


@router.post("/selection/run", response_model=AgentRunResponse)
async def selection_run(payload: SelectionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    if not payload.leads:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide at least one lead")
    run = await record_run(AgentName.SELECTION, settings.gemini_selection_model or "mock", SELECTION_PROMPT_VERSION, payload.model_dump(mode="json"), lambda: run_selection(payload.leads))
    ranked = {item["lead_id"]: item for item in run.output.get("ranked", [])}
    for lead in payload.leads:
        result = ranked.get(lead.id, {})
        await get_database().lead_inbox.update_one({"lead_id": lead.id}, {"$set": {**lead.model_dump(mode="json"), "lead_id": lead.id, "status": "pending", "priority_score": result.get("priority_score"), "suggested_angle": result.get("suggested_angle"), "reasoning": result.get("reasoning"), "updated_at": datetime.now(UTC)}}, upsert=True)
    return run


@router.post("/produce", response_model=AgentRunResponse)
async def production_run(payload: ProductionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.PRODUCTION, settings.gemini_production_model or "mock", PRODUCTION_PROMPT_VERSION, payload.model_dump(), lambda: run_production(payload.headline, payload.topic, payload.context, payload.target_platforms))


@router.post("/telemetry/recalculate", response_model=AgentRunResponse)
async def telemetry_run(payload: TelemetryRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.TELEMETRY, settings.gemini_telemetry_model or "mock", TELEMETRY_PROMPT_VERSION, payload.model_dump(), lambda: run_telemetry(payload.article_id))
