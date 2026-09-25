from typing import Any

import pytest

from app.agents import editing_agent
from app.agents.provider import GeminiProvider
from app.models.agents import ChatMessage, ChatResult


@pytest.mark.asyncio
async def test_run_chat_returns_the_safe_mock_fallback(db):
    result = await editing_agent.run_chat(
        "A valid draft headline", "", "<p>Draft text.</p>", [], "Make this punchier"
    )

    assert result.reply == "I couldn't process that — try rephrasing your request."
    assert result.title is None
    assert result.dek is None
    assert result.content_html is None


@pytest.mark.asyncio
async def test_run_chat_sanitizes_an_html_proposal(db, monkeypatch):
    class UnsafeProvider(GeminiProvider):
        name = "unsafe-test"

        async def generate_json(self, *, model: str, prompt: str, schema: type[ChatResult], fallback: dict[str, Any]) -> ChatResult:
            return schema.model_validate(
                {"reply": "I made the edit.", "content_html": "<p>Safe</p><script>alert(1)</script>"}
            )

    monkeypatch.setattr(editing_agent, "get_provider", lambda: UnsafeProvider())

    result = await editing_agent.run_chat(
        "A valid draft headline", "", "<p>Draft text.</p>", [], "Make this punchier"
    )

    assert result.content_html == "<p>Safe</p>"


@pytest.mark.asyncio
async def test_run_chat_drops_oldest_history_to_stay_within_budget(db, monkeypatch):
    captured: dict[str, Any] = {}

    class CapturingProvider(GeminiProvider):
        name = "capturing-test"

        async def generate_json(self, *, model: str, prompt: str, schema: type[ChatResult], fallback: dict[str, Any]) -> ChatResult:
            captured["prompt"] = prompt
            return schema.model_validate(fallback)

    monkeypatch.setattr(editing_agent, "get_provider", lambda: CapturingProvider())
    history = [ChatMessage(role="user", content=f"{index}:" + "x" * 3990) for index in range(8)]
    draft = "<p>" + "d" * 45_000 + "</p>"

    await editing_agent.run_chat("A valid draft headline", "", draft, history, "Please revise this")

    # The payload representation adds a small amount of syntax, so test the
    # bounded inputs directly as well as confirming early turns were removed.
    bounded = editing_agent.chat_history_within_budget(
        "A valid draft headline", "", draft, history, "Please revise this"
    )
    assert len(bounded) < len(history)
    assert bounded == history[-len(bounded):]
    assert "0:" not in captured["prompt"]
    assert "7:" in captured["prompt"]
