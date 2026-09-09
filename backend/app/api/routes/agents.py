from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.production_agent import PROMPT_VERSION as PRODUCTION_PROMPT_VERSION, run_production
from app.agents.selection_agent import PROMPT_VERSION as SELECTION_PROMPT_VERSION, run_selection
from app.agents.telemetry_agent import PROMPT_VERSION as TELEMETRY_PROMPT_VERSION, run_telemetry
from app.api.dependencies import require_roles
from app.core.settings import settings
from app.core.features import require_ai_feature
from app.models.agents import AgentName, AgentRunResponse, ProductionRunRequest, SelectionRunRequest, TelemetryRunRequest
from app.models.user import UserRole
from app.services.agent_runs import record_run

router = APIRouter(prefix="/agents")
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


@router.post("/selection/run", response_model=AgentRunResponse)
async def selection_run(payload: SelectionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    if not payload.leads:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide at least one lead")
    return await record_run(AgentName.SELECTION, settings.gemini_selection_model or "mock", SELECTION_PROMPT_VERSION, payload.model_dump(mode="json"), lambda: run_selection(payload.leads))


@router.post("/produce", response_model=AgentRunResponse)
async def production_run(payload: ProductionRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.PRODUCTION, settings.gemini_production_model or "mock", PRODUCTION_PROMPT_VERSION, payload.model_dump(), lambda: run_production(payload.headline, payload.topic, payload.context, payload.target_platforms))


@router.post("/telemetry/recalculate", response_model=AgentRunResponse)
async def telemetry_run(payload: TelemetryRunRequest, _: dict = Depends(require_roles(*EDITOR_ROLES)), __: None = Depends(require_ai_feature)) -> AgentRunResponse:
    return await record_run(AgentName.TELEMETRY, settings.gemini_telemetry_model or "mock", TELEMETRY_PROMPT_VERSION, payload.model_dump(), lambda: run_telemetry(payload.article_id))
