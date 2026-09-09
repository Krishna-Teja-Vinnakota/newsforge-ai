from app.agents.provider import get_provider
from app.core.database import get_database
from app.core.settings import settings
from app.models.agents import LeadInput, RankedLead, SelectionResult

PROMPT_VERSION = "selection-v1"


async def run_selection(leads: list[LeadInput]) -> SelectionResult:
    signals = {item["key"]: item["weight"] async for item in get_database().ranking_signals.find({}, {"key": 1, "weight": 1})}
    ordered = sorted(leads, key=lambda lead: signals.get(f"{lead.topic}|{lead.geo}", 0), reverse=True)
    fallback = {"ranked": [RankedLead(lead_id=lead.id, headline=lead.headline, priority_score=round(min(1, max(0, 0.65 + signals.get(f"{lead.topic}|{lead.geo}", 0))), 2), suggested_angle=f"Focus on the local impact of {lead.topic}.", suggested_publish_window="Next audience peak", reasoning="Ranked using current NewsForge engagement signals.").model_dump() for lead in ordered[:5]]}
    prompt = f"You are NewsForge's editorial strategy agent. Rank these leads using learned signals {signals}. Return only the requested JSON schema. Leads: {[lead.model_dump(mode='json') for lead in leads]}"
    return await get_provider().generate_json(model=settings.gemini_selection_model, prompt=prompt, schema=SelectionResult, fallback=fallback)
