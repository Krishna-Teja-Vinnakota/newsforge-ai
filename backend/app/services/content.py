import re
from html import escape, unescape
from html.parser import HTMLParser

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


_BLOCK_NODES = {"p": "paragraph", "blockquote": "blockquote", "ul": "bulletList", "ol": "orderedList", "li": "listItem"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
_MARKS = {"strong": "bold", "b": "bold", "em": "italic", "i": "italic", "s": "strike"}
_TEXT_CONTAINERS = {"paragraph", "heading"}


class _TiptapBuilder(HTMLParser):
    """Convert the small sanitized HTML subset into a Tiptap document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict = {"type": "doc", "content": []}
        self._stack: list[dict] = [self.root]
        self._marks: list[dict] = []

    def _open(self, node: dict) -> None:
        node.setdefault("content", [])
        self._stack[-1]["content"].append(node)
        self._stack.append(node)

    def _text_target(self) -> dict:
        """Return the paragraph-like node that text should land in, creating one when needed."""
        current = self._stack[-1]
        if current["type"] in _TEXT_CONTAINERS:
            return current
        paragraph: dict = {"type": "paragraph", "content": []}
        current["content"].append(paragraph)
        return paragraph

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _HEADINGS:
            self._open({"type": "heading", "attrs": {"level": _HEADINGS[tag]}})
        elif tag in _BLOCK_NODES:
            self._open({"type": _BLOCK_NODES[tag]})
        elif tag == "br":
            self._text_target()["content"].append({"type": "hardBreak"})
        elif tag in _MARKS:
            self._marks.append({"type": _MARKS[tag]})
        elif tag == "a":
            href = dict(attrs).get("href")
            self._marks.append({"type": "link", "attrs": {"href": href}} if href else {"type": "_ignored"})

    def handle_endtag(self, tag: str) -> None:
        if tag in _HEADINGS or tag in _BLOCK_NODES:
            if len(self._stack) > 1:
                self._stack.pop()
        elif tag in _MARKS or tag == "a":
            if self._marks:
                self._marks.pop()

    def handle_data(self, data: str) -> None:
        if not data.strip() and self._stack[-1]["type"] not in _TEXT_CONTAINERS:
            return
        node: dict = {"type": "text", "text": data}
        marks = [mark for mark in self._marks if mark["type"] != "_ignored"]
        if marks:
            node["marks"] = [dict(mark) for mark in marks]
        self._text_target()["content"].append(node)


def html_to_tiptap(value: str) -> dict:
    """Build editor JSON from sanitized HTML so both stored representations describe the same story."""
    builder = _TiptapBuilder()
    builder.feed(sanitize_html(value))
    builder.close()
    return builder.root


def _inline_html(nodes: list[dict]) -> str:
    rendered = []
    for node in nodes:
        if node.get("type") == "hardBreak":
            rendered.append("<br>")
            continue
        text = escape(str(node.get("text", "")))
        for mark in reversed(node.get("marks") or []):
            kind = mark.get("type")
            if kind == "bold":
                text = f"<strong>{text}</strong>"
            elif kind == "italic":
                text = f"<em>{text}</em>"
            elif kind == "strike":
                text = f"<s>{text}</s>"
            elif kind == "link" and (mark.get("attrs") or {}).get("href"):
                text = f'<a href="{escape(str(mark["attrs"]["href"]), quote=True)}">{text}</a>'
        rendered.append(text)
    return "".join(rendered)


def tiptap_to_html(document: dict) -> str:
    """Render editor JSON to sanitized HTML; the inverse of html_to_tiptap for the supported subset."""

    def render(node: dict) -> str:
        kind = node.get("type")
        children = node.get("content") or []
        if kind == "heading":
            level = min(4, max(1, int((node.get("attrs") or {}).get("level", 2))))
            return f"<h{level}>{_inline_html(children)}</h{level}>"
        if kind == "paragraph":
            return f"<p>{_inline_html(children)}</p>"
        tag = {"blockquote": "blockquote", "bulletList": "ul", "orderedList": "ol", "listItem": "li"}.get(kind or "")
        if tag:
            return f"<{tag}>{''.join(render(child) for child in children)}</{tag}>"
        return "".join(render(child) for child in children) if kind == "doc" else ""

    return sanitize_html(render(document if isinstance(document, dict) else {}))


def reconcile_document(payload: dict) -> None:
    """Make html and JSON agree when a model returned only one of the pair (mutates payload)."""
    html_value, json_value = payload.get("content_html"), payload.get("content_json")
    if isinstance(json_value, list):
        json_value = {"type": "doc", "content": json_value}
    has_html = isinstance(html_value, str) and bool(html_value.strip())
    has_json = isinstance(json_value, dict) and bool(json_value.get("content"))
    if has_html and not has_json:
        payload["content_json"] = html_to_tiptap(html_value)
    elif has_json and not has_html:
        payload["content_html"] = tiptap_to_html(json_value)
