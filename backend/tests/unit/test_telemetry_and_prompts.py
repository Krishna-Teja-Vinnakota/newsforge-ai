from datetime import UTC, datetime, timedelta

import pytest

from app.agents.prompts.production import build_production_prompt
from app.agents.prompts.selection import build_selection_prompt
from app.agents.prompts.telemetry import build_telemetry_prompt
from app.agents.selection_agent import SelectionGuidanceResponse
from app.agents.telemetry_agent import _confidence, update_ranking_signal
from app.services.telemetry_retention import prune_operational_history, prune_stale_telemetry


def test_prompt_builders_and_guidance_contract_are_strict():
    assert 'scores' in build_selection_prompt([{'lead_id': 'one'}]).lower()
    production_prompt = build_production_prompt('Headline', 'technology', 'Context', [], ['web'], 'formal').lower()
    assert 'required json schema' in production_prompt
    assert 'measured institutional register' in production_prompt
    assert 'aggregate metrics' in build_telemetry_prompt({'views': 5}, 0.15).lower()
    guidance = SelectionGuidanceResponse.model_validate({'guidance': [{'lead_id': 'one', 'suggested_angle': 'Reader impact', 'editorial_guidance': 'Verify the source.'}]})
    assert guidance.guidance[0].lead_id == 'one'


@pytest.mark.asyncio
async def test_telemetry_confidence_bounds_and_retention(db):
    assert 0.5 <= _confidence(0.9, 1) <= 0.99
    assert _confidence(1.0, 100_000) == 0.99
    signal = await update_ranking_signal('technology', 'Ohio', {'views': 1000, 'engagement_ratio': 0.9})
    assert -0.15 <= signal.weight_delta <= 0.15
    old = datetime.now(UTC) - timedelta(days=400)
    await db.telemetry_events.insert_one({'timestamp': old})
    await db.agent_runs.insert_one({'created_at': old})
    await db.agent_metrics.insert_one({'timestamp': old})
    await db.audit_logs.insert_one({'timestamp': old})
    assert (await prune_stale_telemetry())['deleted_events'] == 1
    deleted = await prune_operational_history()
    assert deleted['deleted_agent_runs'] == deleted['deleted_agent_metrics'] == deleted['deleted_audit_logs'] == 1
