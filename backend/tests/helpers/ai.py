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

    async def aclose(self):
        self.closed = True

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


async def authorize_ai(session, user_id=1):
    """Explicit consent fixture for tests that intentionally exercise a provider."""
    from datetime import UTC, datetime
    from app.models.athlete import AiConsent
    from app.services.ai_access import POLICY_VERSION, PURPOSE, provider_identity
    from app.models.user import AuthCredential
    credential = await session.get(AuthCredential, user_id)
    if credential is None:
        session.add(AuthCredential(user_id=user_id, email=f"ai-fixture-{user_id}@example.test", password_hash="unused", ai_access_tier="full", disabled=False))
    row = await session.get(AiConsent, user_id)
    if row is None:
        row = AiConsent(user_id=user_id)
        session.add(row)
    row.active, row.policy_version, row.purpose = True, POLICY_VERSION, PURPOSE
    row.provider_identity, row.accepted_at, row.withdrawn_at = provider_identity(), datetime.now(UTC), None
    await session.commit()


import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def authorized_ai_account(db_session):
    from sqlalchemy import text
    await db_session.execute(text("TRUNCATE ai_consents, ai_budget_reservations, athlete_profiles RESTART IDENTITY CASCADE"))
    await db_session.execute(text("UPDATE auth_credentials SET ai_access_tier='full', disabled=false WHERE user_id=1"))
    await authorize_ai(db_session)
    yield
