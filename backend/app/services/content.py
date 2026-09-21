import re
from html import unescape

import bleach

ALLOWED_TAGS = ["p", "br", "h1", "h2", "h3", "h4", "strong", "em", "s", "ul", "ol", "li", "blockquote", "a", "img"]
ALLOWED_ATTRIBUTES = {"a": ["href", "rel"], "img": ["src", "alt", "title"]}


def sanitize_html(value: str) -> str:
    without_dangerous_elements = re.sub(
        r"<(script|style|iframe)\b[^>]*>.*?</\1\s*>", "", value or "", flags=re.IGNORECASE | re.DOTALL
    )
    return bleach.clean(without_dangerous_elements, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols=["http", "https"], strip=True)


def clean_editorial_context(context: str, headline: str = "") -> str:
    """Turn Studio's labelled HTML/editor context into clean prose for a prompt.

    Editor context can arrive as raw Tiptap HTML (`content_html`) or as a
    labelled block like "Current draft: <p>...</p>". Stripping tags and the
    label keeps the model's input to plain, readable prose either way.
    """
    draft_context = context.partition("Current draft:")[2] or context
    text = unescape(draft_context)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"Current (?:summary|draft):", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if headline and text.casefold().startswith(headline.casefold()):
        text = text[len(headline) :].strip()
    return text
