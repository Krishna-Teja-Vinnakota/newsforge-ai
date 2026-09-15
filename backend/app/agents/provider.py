import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.settings import settings

Schema = TypeVar("Schema", bound=BaseModel)
logger = logging.getLogger("uvicorn.error")


class GeminiProvider(ABC):
    name: str

    @abstractmethod
    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema: ...


class MockGeminiProvider(GeminiProvider):
    name = "mock-gemini"

    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema:
        return schema.model_validate(fallback)


class VertexGeminiProvider(GeminiProvider):
    name = "gemini-enterprise"

    async def generate_json(self, *, model: str, prompt: str, schema: type[Schema], fallback: dict[str, Any]) -> Schema:
        if not settings.google_cloud_project or not model:
            raise RuntimeError("Gemini Enterprise requires GOOGLE_CLOUD_PROJECT and an enabled model ID")

        def request() -> Schema:
            from google import genai
            from google.genai import types

            # The Google Gen AI SDK supports two mutually exclusive modes:
            # Gemini Developer API with an API key, or Vertex AI with a
            # project/location and Application Default Credentials. Do not pass
            # project/location alongside an API key.
            if settings.gemini_api_key:
                client_options: dict[str, Any] = {"api_key": settings.gemini_api_key}
            else:
                client_options = {
                    "vertexai": True,
                    "project": settings.google_cloud_project,
                    "location": settings.google_cloud_location,
                }
            client = genai.Client(**client_options)
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
                is_retryable = "503" in str(error) or "UNAVAILABLE" in str(error)
                if not is_retryable or attempt == attempts - 1:
                    break
                await asyncio.sleep(2 * (attempt + 1))
        # A newsroom workflow must not strand an approved lead because a
        # remote model is temporarily unavailable or returns malformed
        # structured output. The agent-specific fallback remains editable
        # and the error stays visible in container logs for follow-up.
        logger.error("Gemini generation failed; using the structured agent fallback: %s", last_error, exc_info=last_error)
        return schema.model_validate(fallback)


def get_provider() -> GeminiProvider:
    return VertexGeminiProvider() if settings.llm_provider == "gemini_enterprise" else MockGeminiProvider()
