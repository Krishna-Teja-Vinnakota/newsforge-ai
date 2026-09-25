import hashlib
import re
from html import unescape

from app.agents.provider import ImageGenerationError
from app.models.agents import ImageBrief

# Flags that always force a non-photographic, non-specific depiction.
SYMBOLIC_FLAGS = {"allegation", "real_person", "minors"}
# Flags that rule out a documentary (photo-like) depiction but allow an editorial illustration.
ILLUSTRATION_FLAGS = {"politics", "violence"}
# A brief that is unsafe *and* carries one of these is refused outright, never rewritten.
REFUSAL_FLAGS = {"violence", "minors"}

# Each entry is a positive description; image models follow these better than "do not" lists.
STYLE_SUFFIX = (
    "Composition: 16:9 landscape, a single strong focal subject, natural lighting, restrained professional colour "
    "grading, calm and informative rather than sensational. Keep the bottom edge of the frame visually calm and "
    "uncluttered. The frame contains only the scene itself: no text, lettering, captions, watermarks, logos, "
    "flags, signage, screenshots or documents; any people are shown from behind, at a distance or as silhouettes, "
    "with no identifiable faces."
)
MODE_STYLE = {
    "documentary": "Clean, realistic editorial scene in a generic, non-specific setting, in the style of a wire-service feature photograph.",
    "editorial_illustration": "Refined editorial illustration with a muted palette and clear shapes, in the style of a major newspaper's opinion and features section.",
    "symbolic": "Symbolic conceptual editorial image built from objects, textures and environments that suggest the topic without depicting any specific event or person.",
}


class ImageRefusedError(ImageGenerationError):
    status_code = 422
    user_message = "This story is too sensitive to illustrate automatically. Please choose or upload a hero image."


def plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return " ".join(unescape(text).split())


def source_hash(title: str, dek: str, content_html: str) -> str:
    """Identify the exact story text a brief was written for, so a stale brief is never reused."""
    normalized = "\n".join([" ".join((title or "").split()), " ".join((dek or "").split()), plain_text(content_html)])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fallback_brief(title: str, topic: str = "") -> ImageBrief:
    """A deterministic, deliberately generic brief used when the model cannot supply a safe one."""
    subject_area = (topic or "current affairs").replace("-", " ")
    return ImageBrief(
        subject=f"A symbolic editorial image representing {subject_area} news",
        setting="An abstract, non-specific environment",
        visual_elements=["abstract shapes", "soft directional light", "a muted editorial colour palette"],
        avoid=["identifiable people", "text", "logos", "specific real events"],
        depiction_mode="symbolic",
        risk_flags=[],
        alt_text=f"Abstract editorial illustration representing {subject_area} news.",
        safe_to_generate=True,
    )


def apply_policy(brief: ImageBrief, *, title: str = "", topic: str = "") -> ImageBrief:
    """Server-side guardrails. `safe_to_generate` informs this but never authorizes on its own."""
    flags = set(brief.risk_flags)
    if not brief.safe_to_generate:
        if flags & REFUSAL_FLAGS:
            raise ImageRefusedError()
        # Not enough factual detail to depict specifically: fall back to a generic symbolic image.
        replacement = fallback_brief(title, topic)
        replacement.risk_flags = brief.risk_flags
        replacement.source_hash = brief.source_hash
        return replacement

    updates: dict = {}
    if flags & SYMBOLIC_FLAGS:
        updates["depiction_mode"] = "symbolic"
    elif flags & ILLUSTRATION_FLAGS and brief.depiction_mode == "documentary":
        updates["depiction_mode"] = "editorial_illustration"
    avoid = list(brief.avoid)
    if "real_person" in flags:
        avoid.append("photorealistic likeness of any real person")
    if "minors" in flags:
        avoid.append("children or minors")
    if "allegation" in flags:
        avoid.append("any depiction that suggests wrongdoing has been proven")
    updates["avoid"] = avoid
    return brief.model_copy(update=updates)


def build_image_prompt(brief: ImageBrief) -> str:
    """Assemble the image model's prompt from structured fields plus fixed, reviewed wording."""
    parts = [
        MODE_STYLE[brief.depiction_mode],
        f"Subject: {brief.subject}." if brief.subject else "",
        f"Setting: {brief.setting}." if brief.setting else "",
        f"Visual elements: {', '.join(brief.visual_elements)}." if brief.visual_elements else "",
        f"Leave out: {', '.join(brief.avoid)}." if brief.avoid else "",
        STYLE_SUFFIX,
    ]
    return " ".join(part for part in parts if part)
