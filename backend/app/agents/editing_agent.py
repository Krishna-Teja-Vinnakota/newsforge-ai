from html import escape
from time import perf_counter

from app.agents.provider import get_provider
from app.core.settings import settings
from app.models.agents import BodyResult, ChatMessage, ChatResult, DekResult, HeadlineResult, TagSuggestionResult
from app.services.agent_metrics import record_agent_metrics
from app.services.content import clean_editorial_context, sanitize_html

HEADLINE_PROMPT_VERSION = "headline_v1"
DEK_PROMPT_VERSION = "dek_v1"
BODY_PROMPT_VERSION = "body_v1"
TAGS_PROMPT_VERSION = "tags_v1"
CHAT_PROMPT_VERSION = "chat_v1"
CHAT_PROMPT_CHAR_BUDGET = 60_000


def prompt(task: str, payload: dict) -> str:
    return (
        "You are NewsForge's editorial copy assistant. Work only with the supplied material. "
        "Do not invent facts, names, quotations, dates, or figures. Return only a JSON object matching "
        f"the requested schema. Task: {task}. Input: {payload!r}"
    )


async def _generate(schema, task: str, payload: dict, fallback):
    started = perf_counter()
    result = await get_provider().generate_json(
        model=settings.gemini_production_model,
        prompt=prompt(task, payload),
        schema=schema,
        fallback=fallback,
    )
    await record_agent_metrics("editing", settings.gemini_production_model or "mock", task, result.model_dump(mode="json"), int((perf_counter() - started) * 1000))
    return result


async def run_headline(title: str, topic: str, context: str, mode: str) -> HeadlineResult:
    base = title.strip() or f"Latest {topic.replace('-', ' ')} update"
    fallback = {"title": base}
    task = "Create a concise, accurate news headline." if mode == "generate" else "Correct grammar only; preserve meaning and facts in this headline."
    if mode == "options":
        fallback = {"title": base, "options": [base, f"{base}: what we know", f"What to know: {base}"]}
        task = (
            "Write exactly three distinct, concise, accurate news headline options, each under 120 characters, "
            "using different angles or phrasing. Put them in `options` and set `title` to the first option."
        )
    clean_context = clean_editorial_context(context, title)
    result = await _generate(HeadlineResult, task, {"title": title, "topic": topic, "context": clean_context}, fallback)
    if mode == "options":
        result.options = list(dict.fromkeys(option.strip() for option in result.options if option.strip()))[:3]
        if not result.options:
            result.options = [result.title]
    return result


async def run_dek(dek: str, title: str, context: str, mode: str) -> DekResult:
    fallback = {"dek": dek.strip() or f"The latest verified details on {title}."}
    task = "Write a clear, factual reader summary under 220 characters." if mode == "generate" else "Correct grammar only; preserve meaning and facts in this reader summary."
    clean_context = clean_editorial_context(context, title)
    return await _generate(DekResult, task, {"title": title, "dek": dek, "context": clean_context}, fallback)


async def run_body(content_html: str, title: str, dek: str, notes: str, mode: str) -> BodyResult:
    if mode == "notes_to_story":
        body = f"<p>{escape(notes)}</p>" if notes else "<p>Add reporting notes before generating a story.</p>"
        task = "Turn the supplied notes into a factual, structured news draft."
    else:
        body = sanitize_html(content_html)
        task = "Rewrite this story for clarity and newsroom style without adding facts." if mode == "rewrite" else "Correct grammar only; preserve the structure and facts in this story."
    fallback = {"content_html": body, "content_json": {"type": "doc", "content": []}}
    result = await _generate(BodyResult, task, {"title": title, "dek": dek, "content_html": content_html, "notes": notes}, fallback)
    result.content_html = sanitize_html(result.content_html)
    return result


def chat_history_within_budget(title: str, dek: str, content_html: str, history: list[ChatMessage], message: str) -> list[ChatMessage]:
    """Keep the newest context without allowing accumulated chat to dominate the prompt."""
    retained = list(history[-8:])
    fixed_size = len(title) + len(dek) + len(content_html) + len(message)
    while retained and fixed_size + sum(len(item.content) for item in retained) > CHAT_PROMPT_CHAR_BUDGET:
        retained.pop(0)
    return retained


async def run_chat(title: str, dek: str, content_html: str, history: list[ChatMessage], message: str) -> ChatResult:
    fallback = {
        "reply": "I couldn't process that — try rephrasing your request.",
        "title": None,
        "dek": None,
        "content_html": None,
    }
    bounded_history = chat_history_within_budget(title, dek, content_html, history, message)
    task = (
        "Discuss this news draft with its editor. You are a draft-refinement assistant, not a general support or "
        "research bot. Work only with the supplied title, dek, draft, and conversation. Do not invent facts, names, "
        "quotations, dates, figures, or source claims. If the editor asks for information not in the supplied material, "
        "explain that you cannot verify it and ask for source or reporting context. For advice-only questions, reply "
        "conversationally and leave title, dek, and content_html null. If the editor asks for a concrete change, return "
        "only the fields that change: title and dek must be complete replacements, and content_html must be the complete "
        "draft, never a fragment. Leave every unchanged field null."
    )
    result = await _generate(
        ChatResult,
        task,
        {
            "title": title,
            "dek": dek,
            "content_html": sanitize_html(content_html),
            "history": [item.model_dump() for item in bounded_history],
            "message": message,
        },
        fallback,
    )
    if result.content_html is not None:
        result.content_html = sanitize_html(result.content_html)
    return result


async def run_tags(title: str, dek: str, content_html: str, topic: str, existing_tags: list[str]) -> TagSuggestionResult:
    fallback = {"suggested_tags": [topic.replace("-", " ")] if topic and topic not in existing_tags else []}
    result = await _generate(
        TagSuggestionResult,
        "Suggest up to five specific, useful newsroom tags. Exclude existing tags and broad filler.",
        {"title": title, "dek": dek, "content_html": sanitize_html(content_html), "topic": topic, "existing_tags": existing_tags},
        fallback,
    )
    result.suggested_tags = list(dict.fromkeys(tag.strip().lower() for tag in result.suggested_tags if tag.strip() and tag.lower() not in {item.lower() for item in existing_tags}))[:5]
    return result
