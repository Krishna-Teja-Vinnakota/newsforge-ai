import bleach

ALLOWED_TAGS = ["p", "br", "h1", "h2", "h3", "h4", "strong", "em", "s", "ul", "ol", "li", "blockquote", "a", "img"]
ALLOWED_ATTRIBUTES = {"a": ["href", "target", "rel"], "img": ["src", "alt", "title"]}


def sanitize_html(value: str) -> str:
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols=["http", "https"], strip=True)
