import json

from app.agents.prompts.image import IMAGE_BRIEF_KEY_GUIDANCE

PROMPT_VERSION = "production_v1.4"


def build_production_prompt(
    headline: str,
    topic: str,
    context: str,
    sources: list[dict],
    target_platforms: list[str],
    tone: str | None = None,
) -> str:
    tone_guidance = {
        "formal": "Use a measured institutional register, precise attribution, and no contractions.",
        "conversational": "Use a direct, approachable voice with active verbs, short sentences, and no slang.",
        "urgent": "Use a breaking-news frame: lead with what just changed and why it is immediate, while remaining calm and factual.",
    }
    requested_tone = tone_guidance.get(tone or "")
    prompt = (
        "You are NewsForge's production agent. Create a complete, compelling online news "
        "draft in a clean newsroom style using only the supplied context and retrieved "
        "sources. Lead with the news in one substantial lede, followed by four to six meaningful, "
        "topic-specific H2 sections. Give each section two to three substantive paragraphs when "
        "the evidence supports them, targeting roughly 500 to 800 words overall. Use concrete "
        "names, numbers, dates, quotations, and attribution from the supplied reporting; do not "
        "merely restate the headline. Vary section headings to fit the story rather than reusing "
        "generic headings. Never use vague filler such as 'what this means for readers' or 'the "
        "available information points to a story that is still developing.' If a fact is unconfirmed, "
        "state exactly what remains unconfirmed and what reporting is needed. Do not invent facts, "
        "names, quotes, figures, sources, or attribution. Return one JSON object matching the "
        "required JSON schema with these exact keys: "
        "title, dek, content_html, content_json, reporter_brief, social_posts, push_notification, "
        "provenance, and image_brief. Do not use headline or summary as substitute keys. "
        f"{IMAGE_BRIEF_KEY_GUIDANCE} "
        f"headline={headline!r}; topic={topic!r}; context={context!r}; "
        f"retrieved_sources={json.dumps(sources, default=str)}; platforms={target_platforms!r}."
    )
    return f"{prompt} Tone instruction: {requested_tone}" if requested_tone else prompt
