import re

import bleach

ALLOWED_TAGS = ["p", "br", "h1", "h2", "h3", "h4", "strong", "em", "s", "ul", "ol", "li", "blockquote", "a", "img"]
ALLOWED_ATTRIBUTES = {"a": ["href", "rel"], "img": ["src", "alt", "title"]}


def sanitize_html(value: str) -> str:
    without_dangerous_elements = re.sub(
        r"<(script|style|iframe)\b[^>]*>.*?</\1\s*>", "", value or "", flags=re.IGNORECASE | re.DOTALL
    )
    return bleach.clean(without_dangerous_elements, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols=["http", "https"], strip=True)
