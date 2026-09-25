"""Persisted editorial priorities used by deterministic lead selection."""

from datetime import UTC, datetime

from app.core.database import get_database
from app.models.agents import SelectionWeights, SelectionWeightsResponse

CONFIG_ID = "global"
DEFAULT_SELECTION_WEIGHTS = SelectionWeights()


async def load_selection_weights() -> SelectionWeightsResponse:
    document = await get_database().selection_settings.find_one({"_id": CONFIG_ID})
    if document is None:
        return SelectionWeightsResponse(**DEFAULT_SELECTION_WEIGHTS.model_dump())
    return SelectionWeightsResponse.model_validate(document)


async def save_selection_weights(weights: SelectionWeights, user_id: str) -> SelectionWeightsResponse:
    updated_at = datetime.now(UTC)
    values = {
        **weights.model_dump(),
        "updated_at": updated_at,
        "updated_by": user_id,
    }
    await get_database().selection_settings.update_one(
        {"_id": CONFIG_ID},
        {"$set": values},
        upsert=True,
    )
    return SelectionWeightsResponse(**values)
