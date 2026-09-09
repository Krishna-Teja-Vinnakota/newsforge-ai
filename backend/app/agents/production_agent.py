from html import escape

from app.agents.provider import get_provider
from app.core.settings import settings
from app.models.agents import ProductionResult
from app.services.retrieval import retrieve_editorial_context

PROMPT_VERSION = "production-v1"


async def run_production(headline: str, topic: str, context: str, target_platforms: list[str]) -> ProductionResult:
    sources = await retrieve_editorial_context(topic)
    grounded_context = context or "\n".join(source["excerpt"] for source in sources)
    safe_title, safe_context = escape(headline), escape(grounded_context)
    fallback = {"title": headline, "dek": f"What NewsForge readers need to know about {topic}.", "content_json": {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": headline}]}, {"type": "paragraph", "content": [{"type": "text", "text": grounded_context or f"A NewsForge draft on {topic}, pending editorial verification."}]}]}, "content_html": f"<h2>{safe_title}</h2><p>{safe_context or 'A NewsForge draft, pending editorial verification.'}</p>", "reporter_brief": {"background": f"Verify the central facts and audience relevance for {topic}.", "key_questions": ["What changed?", "Who is affected?", "What evidence supports this?"], "shot_list": ["Establishing context", "Primary source interview", "Relevant data or document"]}, "social_posts": [f"{headline} — what it means for readers. #NewsForge"], "push_notification": headline[:110], "provenance": [source["slug"] for source in sources] or ["Editor-supplied context only; verify before publication."]}
    prompt = f"You are NewsForge's production agent. Create a fact-grounded draft for headline={headline!r}, topic={topic!r}, context={grounded_context!r}, retrieved_sources={sources!r}, platforms={target_platforms!r}. Do not invent facts. Return only the required JSON schema."
    return await get_provider().generate_json(model=settings.gemini_production_model, prompt=prompt, schema=ProductionResult, fallback=fallback)
