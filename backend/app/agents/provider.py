import asyncio
import io
import json
import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.settings import settings
from app.services.content import reconcile_document

Schema = TypeVar("Schema", bound=BaseModel)
logger = logging.getLogger("uvicorn.error")

# True when the most recent generation in this task returned the agent's templated
# fallback instead of model output. record_run reads it so the run history and the
# UI can tell an editor that a result was not written by the model.
fallback_used: ContextVar[bool] = ContextVar("fallback_used", default=False)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    content_type: str


class ImageGenerationError(Exception):
    """An image could not be produced. `user_message` is safe to show to an editor."""

    status_code = 502
    user_message = "Image generation failed. Please try again."

    def __init__(self, user_message: str | None = None):
        self.user_message = user_message or type(self).user_message
        super().__init__(self.user_message)


class ImageBlockedError(ImageGenerationError):
    status_code = 422
    user_message = "The image model declined to create an image for this story. Try another hero image or upload one."


class ImageEmptyError(ImageGenerationError):
    status_code = 502
    user_message = "The image model returned no image. Please try again."


class ImageTimeoutError(ImageGenerationError):
    status_code = 504
    user_message = "Image generation timed out. Please try again."


class ImageQuotaError(ImageGenerationError):
    status_code = 429
    user_message = (
        "Gemini image-generation quota is unavailable or exhausted. "
        "Check billing and image-model rate limits in Google AI Studio, or try again later."
    )


def _genai_client():
    from google import genai

    # The Google Gen AI SDK supports two mutually exclusive modes: Gemini
    # Developer API with an API key, or Vertex AI with a project/location and
    # Application Default Credentials. Do not pass project/location alongside
    # an API key.
    if settings.gemini_api_key:
        client_options: dict[str, Any] = {"api_key": settings.gemini_api_key}
    else:
        client_options = {
            "vertexai": True,
            "project": settings.google_cloud_project,
            "location": settings.google_cloud_location,
        }
    return genai.Client(**client_options)


def _has_credentials() -> bool:
    return bool(settings.gemini_api_key or settings.google_cloud_project)


class GeminiProvider(ABC):
    name: str

    @abstractmethod
    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema: ...

    async def generate_image(self, *, model: str, prompt: str, aspect_ratio: str = "16:9") -> GeneratedImage:
        raise ImageGenerationError("This provider cannot generate images.")


class MockGeminiProvider(GeminiProvider):
    name = "mock-gemini"

    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema:
        fallback_used.set(True)
        return schema.model_validate(fallback)

    async def generate_image(self, *, model: str, prompt: str, aspect_ratio: str = "16:9") -> GeneratedImage:
        """Return a neutral placeholder so the full flow works without a model."""
        fallback_used.set(True)

        def render() -> bytes:
            from PIL import Image, ImageDraw

            width, height = 1280, 720
            image = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(image)
            for y in range(height):
                ratio = y / height
                draw.line([(0, y), (width, y)], fill=(int(21 + 40 * ratio), int(35 + 70 * ratio), int(59 + 130 * ratio)))
            draw.ellipse((width - 520, -180, width + 80, 420), fill=(60, 110, 190))
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()

        return GeneratedImage(data=await asyncio.to_thread(render), content_type="image/png")


class VertexGeminiProvider(GeminiProvider):
    name = "gemini-enterprise"

    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema:
        if not _has_credentials() or not model:
            raise RuntimeError("Gemini Enterprise requires GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT, and an enabled model ID")

        def request() -> Schema:
            from google.genai import types

            client = _genai_client()
            # Gemini structured output does not accept JSON Schema's
            # `additionalProperties`. ProductionResult deliberately contains
            # flexible Tiptap/reporter-brief objects, so send it in JSON mode
            # and validate the returned JSON with Pydantic locally. Simpler
            # schemas (such as selection guidance) retain provider-side schema
            # enforcement.
            json_schema = schema.model_json_schema()
            def has_additional_properties(value: Any) -> bool:
                if isinstance(value, dict):
                    return "additionalProperties" in value or any(has_additional_properties(item) for item in value.values())
                if isinstance(value, list):
                    return any(has_additional_properties(item) for item in value)
                return False

            config_options: dict[str, Any] = {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            }
            allows_free_form_objects = has_additional_properties(json_schema)
            if not allows_free_form_objects:
                config_options["response_schema"] = schema
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_options),
            )
            generated = json.loads(response.text)
            if allows_free_form_objects:
                if isinstance(generated, dict):
                    # If the model returned only one of content_html/content_json, derive the
                    # other from it. Otherwise the default merge below would fill the gap with
                    # the templated fallback and leave the two representations disagreeing.
                    reconcile_document(generated)
                # JSON mode permits Gemini to omit fields that are not needed
                # for its prose. Fill those fields from the agent's known-good
                # fallback while retaining every generated story field.
                if isinstance(generated, dict) and "headline" in generated and "title" not in generated:
                    generated["title"] = generated["headline"]
                if isinstance(generated, dict) and "summary" in generated and "dek" not in generated:
                    generated["dek"] = generated["summary"]

                def merge_defaults(default: Any, value: Any) -> Any:
                    if isinstance(default, dict) and isinstance(value, dict):
                        return {
                            key: merge_defaults(default.get(key), value.get(key))
                            for key in default | value
                        }
                    return value if value is not None else default

                generated = merge_defaults(fallback, generated)
            return schema.model_validate(generated)

        fallback_used.set(False)
        # The free tier intermittently returns 503 "high demand" for a few
        # seconds at a time. A short retry with backoff recovers most of
        # those transient failures instead of immediately settling for the
        # templated fallback draft.
        attempts = 3
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(asyncio.to_thread(request), timeout=settings.agent_timeout_seconds)
            except Exception as error:  # noqa: BLE001 - retried below, then handled by the fallback path
                last_error = error
                message = str(error)
                is_retryable = any(marker in message for marker in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                if not is_retryable or attempt == attempts - 1:
                    break
                await asyncio.sleep(2 * (attempt + 1))
        # A newsroom workflow must not strand an approved lead because a
        # remote model is temporarily unavailable or returns malformed
        # structured output. The agent-specific fallback remains editable
        # and the error stays visible in container logs for follow-up.
        logger.error("Gemini generation failed; using the structured agent fallback: %s", last_error, exc_info=last_error)
        fallback_used.set(True)
        return schema.model_validate(fallback)

    async def generate_image(self, *, model: str, prompt: str, aspect_ratio: str = "16:9") -> GeneratedImage:
        if not _has_credentials() or not model:
            raise RuntimeError("Image generation requires GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT, and GEMINI_IMAGE_MODEL")

        def request() -> GeneratedImage:
            from google.genai import types

            client = _genai_client()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                ),
            )
            candidate = (getattr(response, "candidates", None) or [None])[0]
            parts = getattr(getattr(candidate, "content", None), "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    return GeneratedImage(data=inline.data, content_type=getattr(inline, "mime_type", None) or "image/png")
            feedback = getattr(response, "prompt_feedback", None)
            finish_reason = str(getattr(candidate, "finish_reason", "") or "")
            if getattr(feedback, "block_reason", None) or any(marker in finish_reason for marker in ("SAFETY", "PROHIBITED", "BLOCKLIST", "IMAGE_OTHER", "RECITATION")):
                raise ImageBlockedError()
            raise ImageEmptyError()

        # Safety filters are left at the provider defaults on purpose. Only a
        # brief 503 is retried; quota and blocked responses fail immediately
        # so an editor is never charged for repeated identical requests.
        attempts = 2
        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(asyncio.to_thread(request), timeout=settings.image_timeout_seconds)
            except ImageGenerationError:
                raise
            except (TimeoutError, asyncio.TimeoutError) as error:
                raise ImageTimeoutError() from error
            except Exception as error:  # noqa: BLE001 - mapped to a controlled error below
                message = str(error)
                if any(marker in message for marker in ("429", "RESOURCE_EXHAUSTED")):
                    raise ImageQuotaError() from error
                if any(marker in message for marker in ("503", "UNAVAILABLE")) and attempt < attempts - 1:
                    await asyncio.sleep(2)
                    continue
                logger.error("Gemini image generation failed: %s", error, exc_info=error)
                raise ImageGenerationError() from error
        raise ImageEmptyError()


def get_provider() -> GeminiProvider:
    return VertexGeminiProvider() if settings.llm_provider == "gemini_enterprise" else MockGeminiProvider()
