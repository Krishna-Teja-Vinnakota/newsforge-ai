from html import escape
from time import perf_counter

from app.agents.prompts.production import PROMPT_VERSION, build_production_prompt
from app.agents.provider import get_provider
from app.core.settings import settings
from app.models.agents import ProductionResult
from app.services.content import sanitize_html
from app.services.agent_metrics import record_agent_metrics
from app.services.retrieval import retrieve_editorial_context


async def run_production(headline: str, topic: str, context: str, target_platforms: list[str]) -> ProductionResult:
    started = perf_counter()
    sources = await retrieve_editorial_context(topic)
    grounded_context = context or "\n".join(source["excerpt"] for source in sources)
    source_ids = [source["id"] for source in sources]
    source_slugs = [source["slug"] for source in sources]
    safe_title, safe_context = escape(headline), escape(grounded_context)
    fallback = {"title": headline, "dek": f"What NewsForge readers need to know about {topic}.", "content_json": {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": headline}]}, {"type": "paragraph", "content": [{"type": "text", "text": grounded_context or f"A NewsForge draft on {topic}, pending editorial verification."}]}]}, "content_html": f"<h2>{safe_title}</h2><p>{safe_context or 'A NewsForge draft, pending editorial verification.'}</p>", "reporter_brief": {"background": f"Verify the central facts and audience relevance for {topic}.", "key_questions": ["What changed?", "Who is affected?", "What evidence supports this?"], "shot_list": ["Establishing context", "Primary source interview", "Relevant data or document"]}, "social_posts": [f"{headline} — what it means for readers. #NewsForge"], "push_notification": headline[:110], "provenance": [source["slug"] for source in sources] or ["Editor-supplied context only; verify before publication."]}
    prompt = build_production_prompt(headline, topic, grounded_context, sources, target_platforms)
    result = await get_provider().generate_json(model=settings.gemini_production_model, prompt=prompt, schema=ProductionResult, fallback=fallback)
    # Retrieval provenance is server-controlled and cannot be supplied by the model.
    result.retrieved_source_ids = source_ids
    result.retrieved_source_slugs = source_slugs
    result.content_html = sanitize_html(result.content_html)
    await record_agent_metrics("production", settings.gemini_production_model or "mock", prompt, result.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    return result
