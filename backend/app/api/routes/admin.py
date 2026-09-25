from fastapi import APIRouter, Depends

from app.api.dependencies import require_roles
from app.models.user import EDITORIAL_ROLES
from scripts.seed_demo import reset_demo_data
from app.services.telemetry_retention import prune_operational_history, prune_stale_telemetry

router = APIRouter()


@router.post("/reset-demo")
async def reset_demo(_: dict = Depends(require_roles(*EDITORIAL_ROLES))) -> dict[str, str | int]:
    result = await reset_demo_data()
    return {
        "status": "success",
        "seeded_leads": result["seeded_leads"],
        "indexed_sources": result["indexed_sources"],
        "message": "Demo scenario reset successfully.",
    }


@router.post("/maintenance/prune-telemetry")
async def prune_telemetry(_: dict = Depends(require_roles(*EDITORIAL_ROLES))) -> dict[str, int | str]:
    result = await prune_stale_telemetry()
    return {"status": "success", **result}


@router.post("/maintenance/prune-operational-history")
async def prune_history(_: dict = Depends(require_roles(*EDITORIAL_ROLES))) -> dict[str, int | str]:
    return {"status": "success", **(await prune_operational_history())}
