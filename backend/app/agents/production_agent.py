from html import escape
from time import perf_counter
from urllib.parse import quote

from app.agents.prompts.production import PROMPT_VERSION, build_production_prompt
from app.agents.provider import get_provider
from app.core.settings import settings
from app.models.agents import ProductionResult
from app.services.content import clean_editorial_context, sanitize_html
from app.services.agent_metrics import record_agent_metrics
from app.services.image_prompt import fallback_brief
from app.services.image_search import find_topical_image_url
from app.services.retrieval import retrieve_editorial_context


def generated_hero_url(headline: str, topic: str) -> str:
    """Create a safe, self-contained editorial hero when no licensed image exists.

    Keeping the SVG inline means an AI draft always has a usable visual without
    relying on a placeholder object that may not exist in storage.
    """
    palette = {
        "technology": ("#163a70", "#0bb99d"), "science": ("#432c78", "#3ba7ff"),
        "sports": ("#7a2d18", "#f39b42"), "business": ("#145448", "#51c69e"),
        "climate": ("#155c55", "#8bd450"), "health": ("#8c294b", "#ff9bb4"),
    }
    start, end = palette.get(topic.lower(), ("#15233b", "#2778e8"))
    words = headline.split()
    title = " ".join(words[:9]) + ("…" if len(words) > 9 else "")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
<defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/></linearGradient></defs>
<rect width="1600" height="900" fill="url(#g)"/><circle cx="1320" cy="170" r="290" fill="#fff" opacity=".12"/><circle cx="220" cy="790" r="330" fill="#fff" opacity=".08"/>
<text x="120" y="580" fill="white" font-family="Georgia,serif" font-size="74" font-weight="700">{escape(title)}</text>
<text x="125" y="670" fill="white" opacity=".82" font-family="Arial,sans-serif" font-size="28" letter-spacing="7">NEWSFORGE • {escape(topic.upper())}</text></svg>'''
    return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"


def fallback_draft(headline: str, topic: str, context: str, sources: list[dict]) -> dict:
    """Build a complete, editable newsroom draft when a model is unavailable.

    The structure mirrors a standard online news story while keeping every
    factual statement bounded by the supplied lead and retrieved context.
    """
    evidence = " ".join(context.split())
    source_excerpts = [" ".join(str(source.get("excerpt", "")).split()) for source in sources[:3]]
    source_excerpts = [excerpt for excerpt in source_excerpts if excerpt]
    dek = f"The verified details available so far on this {topic.replace('-', ' ')} development."
    lede = f"{headline}. {evidence}" if evidence else f"{headline}. This draft needs source reporting before publication."
    known = evidence or "No verified reporting context was supplied with this lead."
    reporting = source_excerpts or ["No retrieved source excerpts are available for this draft."]
    verification = (
        "Before publication, confirm the central claim with a primary document or named source, "
        "then add the affected people, timing, location, and any material figures."
    )
    sections = [
        (None, [lede]),
        ("What is known", [known]),
        ("Reporting and source context", reporting),
        ("Details still to verify", [verification]),
    ]
    content_html = "".join(
        (f"<h2>{escape(heading)}</h2>" if heading else "")
        + "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        for heading, paragraphs in sections
    )
    content: list[dict] = []
    for heading, paragraphs in sections:
        if heading:
            content.append({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": heading}]})
        content.extend({"type": "paragraph", "content": [{"type": "text", "text": paragraph}]} for paragraph in paragraphs)
    content_json = {"type": "doc", "content": content}
    return {
        "title": headline,
        "dek": dek,
        "content_json": content_json,
        "content_html": content_html,
        "reporter_brief": {
            "background": f"Confirm the central facts and reader impact for this {topic} story.",
            "key_questions": ["What changed?", "Who is affected?", "What primary source confirms it?"],
            "shot_list": ["Establishing scene", "Primary document or data", "People affected"],
        },
        "social_posts": [f"{headline} — what it could mean for readers. #NewsForge"],
        "push_notification": headline[:110],
        "provenance": [source["slug"] for source in sources] or ["Editor-supplied lead; verify before publication."],
        "hero_url": generated_hero_url(headline, topic),
        "image_brief": fallback_brief(headline, topic).model_dump(mode="json"),
    }


async def run_production(
    headline: str,
    topic: str,
    context: str,
    target_platforms: list[str],
    tone: str | None = None,
) -> ProductionResult:
    started = perf_counter()
    sources = await retrieve_editorial_context(topic)
    editorial_context = clean_editorial_context(context, headline)
    grounded_context = editorial_context or "\n".join(source["excerpt"] for source in sources)
    source_ids = [source["id"] for source in sources]
    source_slugs = [source["slug"] for source in sources]
    fallback = fallback_draft(headline, topic, grounded_context, sources)
    prompt = build_production_prompt(headline, topic, grounded_context, sources, target_platforms, tone)
    result = await get_provider().generate_json(model=settings.gemini_production_model, prompt=prompt, schema=ProductionResult, fallback=fallback)
    # Retrieval provenance is server-controlled and cannot be supplied by the model.
    result.retrieved_source_ids = source_ids
    result.retrieved_source_slugs = source_slugs
    result.content_html = sanitize_html(result.content_html)
    # Image URLs returned by a text model are not trusted as available media.
    # Prefer a real, topic-relevant photo from Wikipedia; fall back to the
    # generated SVG hero when no suitable match is found.
    result.hero_url = await find_topical_image_url(result.title or headline, topic) or generated_hero_url(result.title or headline, topic)
    await record_agent_metrics("production", settings.gemini_production_model or "mock", prompt, result.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    return result
