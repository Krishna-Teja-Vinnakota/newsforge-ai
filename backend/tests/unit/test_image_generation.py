"""AI hero image generation: policy, compositing, provider errors, and the /agents/image route."""

import io
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from bson import ObjectId
from google import genai
from PIL import Image

from app.agents import image_agent, provider as provider_module
from app.agents.prompts.image import build_image_brief_prompt
from app.agents.provider import (
    GeneratedImage,
    ImageBlockedError,
    ImageEmptyError,
    ImageGenerationError,
    ImageQuotaError,
    ImageTimeoutError,
    VertexGeminiProvider,
)
from app.core.features import image_feature, require_image_feature, require_storage_feature
from app.core.security import create_access_token
from app.core.settings import settings
from app.models.agents import ImageBrief, ProductionResult
from app.services import media_cleanup
from app.services.image_compose import DISCLOSURE, InvalidImageError, compose_hero, load_disclosure_font
from app.services.image_prompt import ImageRefusedError, apply_policy, build_image_prompt, fallback_brief, source_hash
from main import app


def png_bytes(size=(640, 360), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


# --- compositing -----------------------------------------------------------------------------------


def test_compose_outputs_16_9_jpeg_with_a_legible_disclosure_strip():
    result = compose_hero(GeneratedImage(png_bytes((1000, 500), (255, 255, 255)), "image/png"), max_bytes=10_000_000)
    image = Image.open(io.BytesIO(result.data))
    assert result.content_type == "image/jpeg"
    assert image.size == (1600, 900)
    band_top = int(900 * (1 - 0.075))
    bright_rows = [
        y for y in range(band_top, 900)
        if sum(1 for x in range(0, 800) if sum(image.getpixel((x, y))) / 3 > 200) > 3
    ]
    # White text on the dark band: it must have real height (not a few stray pixels) and sit inside the band.
    assert bright_rows and bright_rows[-1] - bright_rows[0] >= 16
    assert image.getpixel((1500, band_top + 5))[0] < 90  # band background is dark
    assert DISCLOSURE == "AI-generated image — illustrative purposes only."


def test_disclosure_font_has_every_glyph_of_the_exact_text():
    font = load_disclosure_font(40)
    def pixels(character: str) -> bytes:
        mask = font.getmask(character)
        return bytes(mask)[: mask.size[0] * mask.size[1]] if hasattr(mask, "size") else b""

    missing = pixels("\U0010ffff")  # a code point no font covers renders as the .notdef box
    for character in set(DISCLOSURE) - {" "}:
        assert pixels(character) != missing, f"no glyph for {character!r}"


def test_compose_applies_exif_orientation_before_cropping():
    source = Image.new("RGB", (640, 360), (255, 0, 0))
    source.paste((0, 0, 255), (0, 180, 640, 360))  # blue bottom half
    exif = Image.Exif()
    exif[0x0112] = 3  # stored upside-down: the blue half must end up on top
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif.tobytes())
    result = compose_hero(GeneratedImage(buffer.getvalue(), "image/jpeg"), max_bytes=10_000_000)
    top_pixel = Image.open(io.BytesIO(result.data)).getpixel((800, 100))
    assert top_pixel[2] > 150 and top_pixel[0] < 100


@pytest.mark.parametrize(
    "generated",
    [
        GeneratedImage(b"", "image/png"),
        GeneratedImage(b"not an image", "image/png"),
        GeneratedImage(png_bytes(), "image/gif"),
    ],
)
def test_compose_rejects_unusable_images(generated):
    with pytest.raises(InvalidImageError):
        compose_hero(generated, max_bytes=10_000_000)


def test_compose_rejects_oversized_images():
    with pytest.raises(InvalidImageError):
        compose_hero(GeneratedImage(png_bytes(), "image/png"), max_bytes=10)


# --- brief policy and prompt -----------------------------------------------------------------------


def brief(**overrides) -> ImageBrief:
    values: dict[str, Any] = {"subject": "A city council chamber", "setting": "Interior", "depiction_mode": "documentary", "alt_text": "A chamber."}
    return ImageBrief(**{**values, **overrides})


@pytest.mark.parametrize("flag", ["allegation", "real_person", "minors"])
def test_policy_forces_symbolic_for_sensitive_flags(flag):
    assert apply_policy(brief(risk_flags=[flag])).depiction_mode == "symbolic"


@pytest.mark.parametrize("flag", ["politics", "violence"])
def test_policy_rules_out_documentary_for_politics_and_violence(flag):
    assert apply_policy(brief(risk_flags=[flag])).depiction_mode == "editorial_illustration"


def test_policy_keeps_documentary_when_nothing_is_flagged():
    assert apply_policy(brief()).depiction_mode == "documentary"


@pytest.mark.parametrize("flag", ["violence", "minors"])
def test_policy_refuses_unsafe_severe_briefs_without_rewriting(flag):
    with pytest.raises(ImageRefusedError):
        apply_policy(brief(safe_to_generate=False, risk_flags=[flag]))


def test_policy_falls_back_to_generic_symbolic_when_detail_is_insufficient():
    result = apply_policy(brief(safe_to_generate=False, risk_flags=["politics"]), title="A story", topic="politics")
    assert result.depiction_mode == "symbolic" and result.safe_to_generate


def test_policy_does_not_trust_safe_flag_alone():
    assert apply_policy(brief(safe_to_generate=True, risk_flags=["allegation"])).depiction_mode == "symbolic"


def test_image_prompt_is_built_from_structured_fields_only():
    prompt = build_image_prompt(apply_policy(brief(visual_elements=["gavel"], risk_flags=["real_person"])))
    assert "gavel" in prompt and "no text" in prompt and "16:9" in prompt
    assert "photorealistic likeness of any real person" in prompt


def test_source_hash_tracks_content_not_markup_or_whitespace():
    base = source_hash("Title here", "Dek", "<p>Hello   world</p>")
    assert base == source_hash("  Title here ", "Dek", "<div>Hello world</div>")
    assert base != source_hash("Title here", "Dek", "<p>Hello changed world</p>")


def test_brief_prompt_carries_the_safety_policy():
    prompt = build_image_brief_prompt("Title", "Dek", "Body")
    for phrase in ("allegation", "real_person", "minors", "untrusted data", "never request a photorealistic likeness"):
        assert phrase in prompt


def test_production_result_validates_with_and_without_image_brief():
    base = {"title": "t", "dek": "d", "content_json": {}, "content_html": "", "reporter_brief": {}, "social_posts": [], "push_notification": ""}
    assert ProductionResult.model_validate(base).image_brief is None
    parsed = ProductionResult.model_validate({**base, "image_brief": {"subject": "s", "depiction_mode": "photo", "risk_flags": ["allegation", "bogus"]}})
    assert parsed.image_brief.depiction_mode == "symbolic"
    assert parsed.image_brief.risk_flags == ["allegation"]


# --- provider --------------------------------------------------------------------------------------


class FakeImageGenAI:
    """Stand-in for google.genai.Client returning an image, a blocked response, or raising."""

    mode: str = "image"
    error: Exception | None = None
    calls: int = 0
    configs: list = []

    def __init__(self, **_: Any) -> None:
        self.models = self

    def generate_content(self, **kwargs: Any):
        FakeImageGenAI.calls += 1
        FakeImageGenAI.configs.append(kwargs["config"])
        if FakeImageGenAI.error:
            raise FakeImageGenAI.error

        class Inline:
            data = png_bytes()
            mime_type = "image/png"

        class Part:
            inline_data = Inline()

        class Content:
            parts = [Part()]

        class Candidate:
            content = Content()
            finish_reason = "STOP"

        class Blocked:
            content = None
            finish_reason = "IMAGE_SAFETY"

        class Response:
            prompt_feedback = None
            candidates = [Candidate()] if FakeImageGenAI.mode == "image" else [Blocked()] if FakeImageGenAI.mode == "blocked" else []

        return Response()


@pytest.fixture
def image_gemini(monkeypatch):
    FakeImageGenAI.mode, FakeImageGenAI.error, FakeImageGenAI.calls, FakeImageGenAI.configs = "image", None, 0, []
    monkeypatch.setattr(genai, "Client", FakeImageGenAI)
    monkeypatch.setattr(settings, "llm_provider", "gemini_enterprise")
    monkeypatch.setattr(settings, "google_cloud_project", "")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(provider_module.asyncio, "sleep", no_sleep)
    return FakeImageGenAI


@pytest.mark.asyncio
async def test_generate_image_works_with_an_api_key_and_no_cloud_project(image_gemini):
    result = await VertexGeminiProvider().generate_image(model="img", prompt="p")
    assert result.content_type == "image/png" and result.data
    assert image_gemini.configs[0].image_config.aspect_ratio == "16:9"


@pytest.mark.asyncio
async def test_generate_json_also_works_with_an_api_key_and_no_cloud_project(image_gemini, monkeypatch):
    monkeypatch.setattr(image_gemini, "generate_content", lambda self, **_: type("R", (), {"text": '{"subject": "x"}'})())
    result = await VertexGeminiProvider().generate_json(model="m", prompt="p", schema=ImageBrief, fallback={})
    assert result.subject == "x"


@pytest.mark.asyncio
async def test_generate_image_requires_credentials_and_a_model(image_gemini, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(RuntimeError):
        await VertexGeminiProvider().generate_image(model="img", prompt="p")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "error", "expected"),
    [
        ("blocked", None, ImageBlockedError),
        ("empty", None, ImageEmptyError),
        ("image", RuntimeError("429 RESOURCE_EXHAUSTED quota"), ImageQuotaError),
        ("image", TimeoutError(), ImageTimeoutError),
        ("image", RuntimeError("400 something else"), ImageGenerationError),
    ],
)
async def test_generate_image_maps_failures_to_controlled_errors(image_gemini, mode, error, expected):
    image_gemini.mode, image_gemini.error = mode, error
    with pytest.raises(expected) as raised:
        await VertexGeminiProvider().generate_image(model="img", prompt="p")
    assert type(raised.value) is expected
    assert "429" not in raised.value.user_message


@pytest.mark.asyncio
async def test_generate_image_retries_a_transient_503_once_but_not_quota(image_gemini):
    image_gemini.error = RuntimeError("503 UNAVAILABLE")
    with pytest.raises(ImageGenerationError):
        await VertexGeminiProvider().generate_image(model="img", prompt="p")
    assert image_gemini.calls == 2
    image_gemini.calls, image_gemini.error = 0, RuntimeError("429 RESOURCE_EXHAUSTED")
    with pytest.raises(ImageQuotaError):
        await VertexGeminiProvider().generate_image(model="img", prompt="p")
    assert image_gemini.calls == 1


# --- feature flag ----------------------------------------------------------------------------------


def test_image_feature_needs_text_model_image_model_and_storage(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini_enterprise")
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    for name in ("gemini_selection_model", "gemini_production_model", "gemini_telemetry_model"):
        monkeypatch.setattr(settings, name, "m")
    for name in ("s3_endpoint_url", "s3_bucket", "s3_access_key", "s3_secret_key"):
        monkeypatch.setattr(settings, name, "x")
    monkeypatch.setattr(settings, "gemini_image_model", "")
    assert not image_feature().enabled and "GEMINI_IMAGE_MODEL" in image_feature().reason
    monkeypatch.setattr(settings, "gemini_image_model", "img")
    assert image_feature().enabled
    monkeypatch.setattr(settings, "s3_bucket", "")
    assert not image_feature().enabled
    monkeypatch.setattr(settings, "s3_bucket", "x")
    monkeypatch.setattr(settings, "gemini_production_model", "")
    assert not image_feature().enabled


# --- route -----------------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def image_client(client, db, monkeypatch):
    uploads: list[str] = []

    async def fake_upload(content: bytes, content_type: str, filename: str):
        key = f"uploads/{uuid4().hex}-{filename}"
        uploads.append(key)
        return key, f"http://media.test/{key}"

    monkeypatch.setattr(image_agent, "upload_public_object", fake_upload)
    monkeypatch.setattr(settings, "image_rate_limit_per_minute", 1000)
    app.dependency_overrides[require_image_feature] = lambda: None
    app.dependency_overrides[require_storage_feature] = lambda: None
    client.uploads = uploads
    return client


async def make_user(db, role: str) -> tuple[dict, dict]:
    user = {"_id": ObjectId(), "email": f"{role}-{uuid4().hex[:6]}@test.newsforge", "display_name": role.title(), "role": role, "is_active": True, "password_hash": "unused"}
    await db.users.insert_one(user)
    return user, {"Authorization": f"Bearer {create_access_token(str(user['_id']), role)}"}


async def make_article(db, creator: dict, status: str = "draft", **extra) -> dict:
    now = datetime.now(UTC)
    article = {
        "_id": ObjectId(), "slug": f"story-{uuid4().hex[:8]}", "status": status, "title": "Council votes on the budget", "dek": "A dek",
        "content_json": {}, "content_html": "<p>Body</p>", "topic": "politics", "tags": [], "hero_media_id": None,
        "hero_url": "https://example.test/old.jpg", "creator_id": creator["_id"], "editor_id": None, "created_at": now, "updated_at": now,
        "published_at": None, "scheduled_for": None, "metrics": {}, **extra,
    }
    await db.articles.insert_one(article)
    return article


def payload(article: dict, key: str | None = None, **overrides) -> dict:
    return {"article_id": str(article["_id"]), "title": "Council votes on the budget", "dek": "A dek", "content_html": "<p>Current body</p>", "idempotency_key": key or uuid4().hex, **overrides}


@pytest.mark.asyncio
async def test_generation_creates_pending_media_and_leaves_the_article_unchanged(image_client, db, admin_user, admin_headers):
    article = await make_article(db, admin_user)
    response = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))
    assert response.status_code == 200, response.text
    body = response.json()
    hero = body["output"]["hero"]
    assert body["agent"] == "image" and hero["ai_generated"] is True and hero["disclosure"] == DISCLOSURE
    media = await db.media.find_one({"_id": ObjectId(hero["media_id"])})
    assert media["status"] == "pending" and media["ai_generated"] is True and media["purpose"] == "hero"
    assert media["expires_at"].replace(tzinfo=None) > datetime.now(UTC).replace(tzinfo=None)
    assert media["source_hash"] and media["brief"]["subject"] and media["generation_run_id"] == ObjectId(body["id"])
    stored = await db.articles.find_one({"_id": article["_id"]})
    assert stored["hero_url"] == "https://example.test/old.jpg" and stored["hero_media_id"] is None
    run = await db.agent_runs.find_one({"_id": ObjectId(body["id"])})
    assert "Current body" not in str(run["input"])  # the unpublished body is never stored with the run


@pytest.mark.asyncio
async def test_current_editor_text_is_used_unless_the_cached_brief_matches(image_client, db, admin_user, admin_headers, monkeypatch):
    calls: list[str] = []
    real = image_agent.generate_brief

    async def spy(request, digest, topic):
        calls.append(digest)
        return await real(request, digest, topic)

    monkeypatch.setattr(image_agent, "generate_brief", spy)
    stale = fallback_brief("x").model_copy(update={"source_hash": "stale"}).model_dump(mode="json")
    article = await make_article(db, admin_user, ai_insights={"image_brief": stale})
    assert (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))).status_code == 200
    assert len(calls) == 1  # the saved brief was for older text, so a fresh one was written

    current = source_hash("Council votes on the budget", "A dek", "<p>Current body</p>")
    fresh = fallback_brief("x").model_copy(update={"source_hash": current}).model_dump(mode="json")
    await db.articles.update_one({"_id": article["_id"]}, {"$set": {"ai_insights": {"image_brief": fresh}}})
    assert (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))).status_code == 200
    assert len(calls) == 1  # matching hash: reused, no new brief


@pytest.mark.asyncio
async def test_replayed_idempotency_key_returns_the_same_image(image_client, db, admin_user, admin_headers):
    article = await make_article(db, admin_user)
    first = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article, "same-key-123"))
    again = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article, "same-key-123"))
    assert first.status_code == again.status_code == 200
    assert first.json()["output"]["hero"] == again.json()["output"]["hero"] and first.json()["id"] == again.json()["id"]
    assert len(image_client.uploads) == 1 and await db.media.count_documents({"ai_generated": True}) == 1
    other = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article, "different-key-1"))
    assert other.json()["output"]["hero"]["media_id"] != first.json()["output"]["hero"]["media_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "own", "expected"),
    [("editor", True, 200), ("editor", False, 200), ("admin", False, 200), ("reporter", True, 401), ("audience", True, 401)],
)
async def test_authorization_matrix(image_client, db, role, own, expected):
    actor, headers = await make_user(db, role)
    owner = actor if own else (await make_user(db, "editor"))[0]
    article = await make_article(db, owner)
    response = await image_client.post("/api/v1/agents/image", headers=headers, json=payload(article))
    assert response.status_code == expected, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [("draft", 200), ("rejected", 200), ("unpublished", 200), ("under_review", 409), ("approved", 409), ("published", 409)],
)
async def test_only_editable_statuses_can_generate(image_client, db, admin_user, admin_headers, status, expected):
    article = await make_article(db, admin_user, status=status)
    assert (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))).status_code == expected


@pytest.mark.asyncio
async def test_unknown_article_and_disabled_feature(image_client, db, admin_user, admin_headers, monkeypatch):
    missing = {"article_id": str(ObjectId()), "title": "A valid title", "idempotency_key": "key-missing-1"}
    assert (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=missing)).status_code == 404
    app.dependency_overrides.pop(require_image_feature)
    # Do not let the host/container environment decide this assertion. The shared
    # db fixture enables mock AI, which intentionally makes image generation
    # available without GEMINI_IMAGE_MODEL for local end-to-end testing.
    monkeypatch.setattr(settings, "enable_mock_ai", False)
    article = await make_article(db, admin_user)
    response = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))
    assert response.status_code == 503 and "Image generation is disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_provider_errors_become_clean_http_errors_and_are_recorded(image_client, db, admin_user, admin_headers, monkeypatch):
    async def blocked(self, **_):
        raise ImageBlockedError()

    monkeypatch.setattr(provider_module.MockGeminiProvider, "generate_image", blocked)
    article = await make_article(db, admin_user)
    response = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))
    assert response.status_code == 422 and "declined" in response.json()["detail"]
    assert await db.media.count_documents({"ai_generated": True}) == 0
    assert (await db.agent_runs.find_one({"agent": "image"}))["status"] == "failed"


@pytest.mark.asyncio
async def test_refused_brief_never_reaches_the_image_model(image_client, db, admin_user, admin_headers, monkeypatch):
    async def unsafe(request, digest, topic):
        return ImageBrief(safe_to_generate=False, risk_flags=["minors"], source_hash=digest)

    async def must_not_run(self, **_):
        raise AssertionError("image model was called")

    monkeypatch.setattr(image_agent, "generate_brief", unsafe)
    monkeypatch.setattr(provider_module.MockGeminiProvider, "generate_image", must_not_run)
    article = await make_article(db, admin_user)
    response = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))
    assert response.status_code == 422 and "too sensitive" in response.json()["detail"]


@pytest.mark.asyncio
async def test_image_rate_limit_and_concurrency_cap(image_client, db, admin_user, admin_headers, monkeypatch):
    article = await make_article(db, admin_user)
    monkeypatch.setattr(settings, "image_max_concurrent", 0)
    capped = await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))
    assert capped.status_code == 429 and "being generated" in capped.json()["detail"]
    monkeypatch.setattr(settings, "image_max_concurrent", 3)
    monkeypatch.setattr(settings, "image_rate_limit_per_minute", 1)
    user, headers = await make_user(db, "admin")
    mine = await make_article(db, user)
    assert (await image_client.post("/api/v1/agents/image", headers=headers, json=payload(mine))).status_code == 200
    limited = await image_client.post("/api/v1/agents/image", headers=headers, json=payload(mine))
    assert limited.status_code == 429 and "Rate limit" in limited.json()["detail"]


@pytest.mark.asyncio
async def test_image_runs_cannot_be_retried_from_history(image_client, db, admin_user, admin_headers):
    article = await make_article(db, admin_user)
    run = (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))).json()
    retry = await image_client.post(f"/api/v1/agents/runs/{run['id']}/retry", headers=admin_headers)
    assert retry.status_code == 409 and await db.media.count_documents({"ai_generated": True}) == 1


@pytest.mark.asyncio
async def test_applying_updates_url_and_media_id_together_and_marks_media_applied(image_client, db, admin_user, admin_headers):
    article = await make_article(db, admin_user)
    hero = (await image_client.post("/api/v1/agents/image", headers=admin_headers, json=payload(article))).json()["output"]["hero"]
    saved = await image_client.patch(
        f"/api/v1/cms/articles/{article['_id']}", headers=admin_headers, json={"hero_media_id": hero["media_id"], "hero_url": hero["url"]}
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["hero_media_id"] == hero["media_id"] and body["hero_url"] == hero["url"]
    assert body["hero_ai_generated"] is True and body["hero_disclosure"] == DISCLOSURE and body["hero_alt_text"]
    media = await db.media.find_one({"_id": ObjectId(hero["media_id"])})
    assert media["status"] == "applied" and "expires_at" not in media


@pytest.mark.asyncio
async def test_expired_unapplied_images_are_swept_but_used_ones_are_kept(db, admin_user, monkeypatch):
    deleted: list[str] = []

    async def fake_delete(key: str) -> None:
        deleted.append(key)

    monkeypatch.setattr(media_cleanup, "delete_object", fake_delete)
    past = datetime.now(UTC) - timedelta(hours=1)
    base = {"content_type": "image/jpeg", "size_bytes": 1, "purpose": "hero", "uploader_id": admin_user["_id"], "created_at": past, "status": "pending", "expires_at": past}
    stale = (await db.media.insert_one({**base, "object_key": "uploads/stale", "url": "u1"})).inserted_id
    used = (await db.media.insert_one({**base, "object_key": "uploads/used", "url": "u2"})).inserted_id
    fresh = (await db.media.insert_one({**base, "object_key": "uploads/fresh", "url": "u3", "expires_at": datetime.now(UTC) + timedelta(hours=1)})).inserted_id
    await make_article(db, admin_user, hero_media_id=used)
    assert await media_cleanup.sweep_expired_pending_media() == 1
    assert deleted == ["uploads/stale"]
    assert await db.media.find_one({"_id": stale}) is None
    assert (await db.media.find_one({"_id": used}))["status"] == "applied"
    assert await db.media.find_one({"_id": fresh}) is not None
