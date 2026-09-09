from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from bson import ObjectId

from app.core.database import get_database
from app.models.agents import AgentName, AgentRunResponse, AgentRunStatus


async def record_run(agent: AgentName, model: str, prompt_version: str, input_data: dict[str, Any], runner):
    started_at, timer = datetime.now(UTC), perf_counter()
    try:
        output = await runner()
        duration_ms = int((perf_counter() - timer) * 1000)
        document = {"agent": agent, "status": AgentRunStatus.SUCCEEDED, "model": model, "prompt_version": prompt_version, "input": input_data, "output": output.model_dump(mode="json"), "duration_ms": duration_ms, "created_at": started_at, "error": None}
        result = await get_database().agent_runs.insert_one(document)
        return AgentRunResponse(id=str(result.inserted_id), agent=agent, status=AgentRunStatus.SUCCEEDED, output=document["output"], model=model, prompt_version=prompt_version, duration_ms=duration_ms, created_at=started_at)
    except Exception as exc:
        duration_ms = int((perf_counter() - timer) * 1000)
        document = {"agent": agent, "status": AgentRunStatus.FAILED, "model": model, "prompt_version": prompt_version, "input": input_data, "output": {}, "duration_ms": duration_ms, "created_at": started_at, "error": str(exc)}
        await get_database().agent_runs.insert_one(document)
        raise
