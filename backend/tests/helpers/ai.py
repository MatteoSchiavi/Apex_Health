"""Fixture-backed LLM and STT clients (§0/§20 — the only AI clients tests
use). The LLM fixture serves recorded replies in order and records every
call so tests can assert on prompts and tier selection."""

from typing import Any

from app.core.llm import LLMResponse


class FixtureLLMClient:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        tier: str = "cheap",
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system, "tier": tier})
        if not self._replies:
            raise AssertionError("FixtureLLMClient ran out of recorded replies")
        return LLMResponse(content=self._replies.pop(0), model="fixture-llm")


class FixtureSTT:
    """Returns the recorded transcript for any audio bytes."""

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript
        self.calls: list[dict[str, Any]] = []

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        self.calls.append({"bytes": len(audio), "filename": filename})
        return self._transcript
