from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agents.graph.workflow import newsroom_workflow, workflow_config
from app.api.dependencies import require_roles
from app.core.database import get_database
from app.models.agents import LeadInput
from app.models.user import UserRole

router = APIRouter(prefix="/workflow")
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


class WorkflowStartRequest(BaseModel):
    lead: LeadInput


class WorkflowResumeRequest(BaseModel):
    approval_status: str | None = Field(default=None, pattern="^(approved|rejected)$")
    editorial_status: str | None = Field(default=None, pattern="^(approved)$")
    generated_draft: dict | None = None


def snapshot_response(thread_id: str, snapshot) -> dict:
    values = dict(snapshot.values)
    next_nodes = list(snapshot.next)
    return {
        "thread_id": thread_id,
        "state": values,
        "current_node": values.get("current_step"),
        "execution_history": values.get("execution_history", []),
        "checkpoints": {"next": next_nodes, "metadata": snapshot.metadata},
        "pending_interrupts": [node for node in next_nodes if node in {"approval_gate", "editorial_gate"}],
    }


async def persisted_snapshot(thread_id: str, snapshot) -> dict:
    response = snapshot_response(thread_id, snapshot)
    await get_database().workflow_threads.update_one(
        {"thread_id": thread_id},
        {"$set": {"thread_id": thread_id, "state": response["state"], "current_node": response["current_node"], "pending_interrupts": response["pending_interrupts"], "execution_history": response["execution_history"]}},
        upsert=True,
    )
    return response


@router.post("/start")
async def start_workflow(payload: WorkflowStartRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> dict:
    thread_id = str(uuid4())
    lead = payload.lead.model_dump(mode="json")
    await newsroom_workflow.ainvoke(
        {
            "thread_id": thread_id,
            "lead_id": lead["id"],
            "lead_candidate": lead,
            "approval_status": "pending",
            "editorial_status": "draft",
            "errors": [],
            "execution_history": [],
        },
        workflow_config(thread_id),
    )
    return await persisted_snapshot(thread_id, await newsroom_workflow.aget_state(workflow_config(thread_id)))


@router.post("/{thread_id}/resume")
async def resume_workflow(thread_id: str, payload: WorkflowResumeRequest, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> dict:
    config = workflow_config(thread_id)
    snapshot = await newsroom_workflow.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow thread not found")
    pending = set(snapshot.next)
    updates: dict = {}
    if "approval_gate" in pending:
        if payload.approval_status is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lead approval is required to resume this workflow")
        updates["approval_status"] = payload.approval_status
    elif "editorial_gate" in pending:
        if payload.editorial_status != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Editorial approval is required to resume this workflow")
        updates["editorial_status"] = payload.editorial_status
        if payload.generated_draft is not None:
            updates["generated_draft"] = payload.generated_draft
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow is not paused for human input")
    # Static interrupt_before gates resume only after checkpoint state is updated.
    await newsroom_workflow.aupdate_state(config, updates)
    await newsroom_workflow.ainvoke(None, config)
    return await persisted_snapshot(thread_id, await newsroom_workflow.aget_state(config))


@router.get("/{thread_id}/state")
async def workflow_state(thread_id: str, _: dict = Depends(require_roles(*EDITOR_ROLES))) -> dict:
    snapshot = await newsroom_workflow.aget_state(workflow_config(thread_id))
    if not snapshot.values:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow thread not found")
    return await persisted_snapshot(thread_id, snapshot)
