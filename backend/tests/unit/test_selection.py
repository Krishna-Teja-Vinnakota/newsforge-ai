from datetime import UTC, datetime, timedelta

import pytest

from app.agents.selection_agent import _clamp_priority_score, run_selection
from app.models.agents import LeadInput


@pytest.mark.asyncio
async def test_selection_is_deterministic_and_uses_requested_tie_breaks(db):
    now = datetime.now(UTC)
    await db.lead_inbox.insert_many([
        {"lead_id": "alpha", "headline": "Alpha", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 3, "updated_at": now},
        {"lead_id": "bravo", "headline": "Bravo", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 2, "updated_at": now},
        {"lead_id": "newer", "headline": "Newer", "topic": "technology", "geo": "global", "base_score": 0.65, "current_rank": 1, "updated_at": now + timedelta(seconds=1)},
    ])
    leads = [LeadInput(id=item, headline=item.title(), topic="technology", geo="global") for item in ["alpha", "bravo", "newer"]]
    result = await run_selection(leads)
    assert [item.lead_id for item in result.ranked] == ["newer", "alpha", "bravo"]
    assert [item.current_rank for item in result.ranked] == [1, 2, 3]
    assert all(item.final_score == round(item.base_score + item.learned_weight_delta, 4) for item in result.ranked)


def test_priority_scores_are_strictly_clamped():
    assert _clamp_priority_score(-5) == 0.0
    assert _clamp_priority_score(0.123456) == 0.1235
    assert _clamp_priority_score(5) == 1.0
