"""Fixture-backed LLM and STT clients (§0/§20 — the only AI clients tests
use). The LLM fixture serves recorded replies in order and records every
call so tests can assert on prompts, tier selection and tool payloads.

FixtureAgentLLMClient scripts full LLMResponse objects (tool-call requests
included) for agent-loop tests; FixtureLLMClient stays the plain-completion
fixture for the voice pipeline and simple reply assertions.
"""

from typing import Any

from app.core.llm import LLMResponse


class FixtureLLMClient:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tier: str = "cheap",
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"messages": messages, "system": system, "tier": tier, "tools": tools}
        )
        if not self._replies:
            raise AssertionError("FixtureLLMClient ran out of recorded replies")
        return LLMResponse(content=self._replies.pop(0), model="fixture-llm")


class FixtureAgentLLMClient:
    """Scripts LLMResponses step by step (tool-call requests and finals) and
    records every completion call."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tier: str = "cheap",
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"messages": messages, "system": system, "tier": tier, "tools": tools}
        )
        if not self._responses:
            raise AssertionError("FixtureAgentLLMClient ran out of scripted responses")
        return self._responses.pop(0)


class FixtureSTT:
    """Returns the recorded transcript for any audio bytes."""

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript
        self.calls: list[dict[str, Any]] = []

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        self.calls.append({"bytes": len(audio), "filename": filename})
        return self._transcript


class FixtureEmbeddingClient:
    """Deterministic vectors keyed by text hash-prefix; records calls."""

    def __init__(self, dimension: int = 1536, tokens_per_text: int = 12) -> None:
        self.dimension = dimension
        self._tokens = tokens_per_text
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]):
        from app.core.embeddings import EMBEDDING_MODEL, EmbeddingResult

        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            seed = sum(ord(c) for c in text) % 97
            vector = [0.0] * self.dimension
            vector[seed % self.dimension] = 1.0
            vectors.append(vector)
        return EmbeddingResult(
            vectors=vectors, model=EMBEDDING_MODEL, tokens_in=self._tokens * len(texts)
        )
