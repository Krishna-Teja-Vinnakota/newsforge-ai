import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.settings import settings

Schema = TypeVar("Schema", bound=BaseModel)


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

            client_options: dict[str, Any] = {
                "vertexai": True,
                "project": settings.google_cloud_project,
                "location": settings.google_cloud_location,
            }
            # Prefer an explicitly supplied Vertex/Gemini API key. When it is
            # absent, the SDK uses Application Default Credentials as before.
            if settings.gemini_api_key:
                client_options["api_key"] = settings.gemini_api_key
            client = genai.Client(**client_options)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.2),
            )
            return schema.model_validate(json.loads(response.text))

        return await asyncio.wait_for(asyncio.to_thread(request), timeout=settings.agent_timeout_seconds)


def get_provider() -> GeminiProvider:
    return VertexGeminiProvider() if settings.llm_provider == "gemini_enterprise" else MockGeminiProvider()
