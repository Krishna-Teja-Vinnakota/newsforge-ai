from datetime import UTC, datetime, timedelta

from app.core.database import get_database
from app.core.settings import settings


async def prune_stale_telemetry() -> dict[str, int]:
    """Delete expired raw events while deliberately preserving ranking aggregates."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.telemetry_retention_days)
    result = await get_database().telemetry_events.delete_many({"timestamp": {"$lt": cutoff}})
    return {"deleted_events": result.deleted_count, "retention_days": settings.telemetry_retention_days}


async def prune_operational_history() -> dict[str, int]:
    """Remove expired raw prompts/runs and audit records under configured policy."""
    database = get_database()
    now = datetime.now(UTC)
    runs = await database.agent_runs.delete_many({"created_at": {"$lt": now - timedelta(days=settings.agent_run_retention_days)}})
    metrics = await database.agent_metrics.delete_many({"timestamp": {"$lt": now - timedelta(days=settings.agent_run_retention_days)}})
    audits = await database.audit_logs.delete_many({"timestamp": {"$lt": now - timedelta(days=settings.audit_retention_days)}})
    return {"deleted_agent_runs": runs.deleted_count, "deleted_agent_metrics": metrics.deleted_count, "deleted_audit_logs": audits.deleted_count}
