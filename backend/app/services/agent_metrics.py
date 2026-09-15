from datetime import UTC, datetime
import logging

from app.core.database import get_database

# Uvicorn configures this logger at INFO level in the container, so agent
# metrics are visible with `podman compose logs -f backend`.
logger = logging.getLogger("uvicorn.error")


def _token_estimate(value: object) -> int:
    return len(str(value).split())


async def record_agent_metrics(agent: str, model: str, prompt: str, output: object, latency_ms: int) -> None:
    input_tokens, output_tokens = _token_estimate(prompt), _token_estimate(output)
    # Conservative generic estimates; providers can replace these with billed usage.
    estimated_cost_usd = round((input_tokens * 0.0000005) + (output_tokens * 0.0000015), 8)
    logger.info(
        "agent_metric agent=%s model=%s input_tokens=%s output_tokens=%s latency_ms=%s estimated_cost_usd=%s",
        agent, model or "mock", input_tokens, output_tokens, latency_ms, estimated_cost_usd,
    )
    await get_database().agent_metrics.insert_one({
        "timestamp": datetime.now(UTC), "agent": agent, "model": model or "mock",
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost_usd, "latency_ms": latency_ms,
    })
