"""Embedding adapter (MASTER_SPEC §2, §6.2).

The embedding model is PINNED to OpenAI text-embedding-3-small (1536-dim) —
unlike the LLM layer this is NOT provider-swappable (§6.2: switching means an
explicit vector(N) migration + full re-embed). Live client rides the
OpenAI-compatible /embeddings endpoint; tests inject fixtures and never hit
the network (§0/§20).

Every embedding call writes a token_usage row (§8.6): embed() returns the
token count alongside the vectors so call sites can log it in one step.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-small"  # pinned — §6.2
EMBEDDING_DIM = 1536


class EmbeddingError(Exception):
    pass


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str = EMBEDDING_MODEL
    tokens_in: int = 0


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


class LiveOpenAIEmbeddingClient:
    def __init__(self, api_key: str, api_base: str, model: str = EMBEDDING_MODEL) -> None:
        if not api_key:
            raise EmbeddingError("OPENAI_API_KEY is not set — embeddings are unavailable")
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=60.0)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model)
        try:
            resp = await self._client.post(
                f"{self._api_base}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding call failed: {exc}") from exc
        usage = body.get("usage") or {}
        data = sorted(body["data"], key=lambda item: item["index"])
        return EmbeddingResult(
            vectors=[item["embedding"] for item in data],
            model=body.get("model", self._model),
            tokens_in=int(usage.get("prompt_tokens", 0)),
        )


def build_embedding_client() -> EmbeddingClient:
    """Production client from settings; tests inject fixtures instead."""
    settings = get_settings()
    return LiveOpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        api_base=settings.openai_api_base,
    )
