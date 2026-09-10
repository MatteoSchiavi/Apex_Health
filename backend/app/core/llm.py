"""LLM client abstraction (§8.1).

One interface — `complete(messages, system, tier)` — implemented per
provider; nothing else touches a provider SDK. That is what makes the
tier/provider choice in §9 an env-var change, not a code change.

Phase 3 scope: the voice pipeline's structured extraction (free tier) and
the bot's free-text entrypoint (cheap tier) call this with plain
completions. The full tool-using agent loop, routing and token accounting
are Phase 5 (§8.3–8.6, §23) and will extend this client with `tools` —
the call sites already go through this module, so nothing else moves.

§0/§20: tests never hit a live provider — they inject a fixture client.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("core.llm")

TIERS = ("free", "cheap", "powerful")


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        tier: str = "cheap",
    ) -> LLMResponse: ...


class LiveGLMClient:
    """GLM family via an OpenAI-compatible chat-completions endpoint (§2).

    Model per tier comes from settings (LLM_PROVIDER_CHEAP /
    LLM_PROVIDER_POWERFUL); the free tier in §9 is the cheap/flash model —
    free-tier routing hardcodes it at the call site, not here.
    """

    def __init__(self, api_key: str, api_base: str, model_cheap: str, model_powerful: str) -> None:
        if not api_key:
            raise LLMError("GLM_API_KEY is not set — live LLM calls are unavailable")
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._models = {"cheap": model_cheap, "powerful": model_powerful}
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        tier: str = "cheap",
    ) -> LLMResponse:
        if tier not in self._models:
            raise LLMError(f"unknown tier {tier!r} (expected one of {sorted(self._models)})")
        payload_messages: list[dict[str, str]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        try:
            resp = await self._client.post(
                f"{self._api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._models[tier], "messages": payload_messages},
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"GLM completion failed: {exc}") from exc
        usage = body.get("usage") or {}
        return LLMResponse(
            content=body["choices"][0]["message"]["content"],
            model=body.get("model", self._models[tier]),
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )


def extract_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object out of a model reply, tolerating code fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"no JSON object in model reply: {content[:200]!r}")
    return json.loads(text[start : end + 1])


def build_llm_client() -> LLMClient:
    """Production client from settings; call sites (tasks, bot process) own
    the lifecycle. Tests never call this — they inject fixture clients."""
    settings = get_settings()
    return LiveGLMClient(
        api_key=settings.glm_api_key,
        api_base=settings.glm_api_base,
        model_cheap=settings.llm_provider_cheap,
        model_powerful=settings.llm_provider_powerful,
    )
