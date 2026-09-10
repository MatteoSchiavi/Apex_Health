"""LLM client abstraction (§8.1).

One interface — `complete(messages, tools, system, tier)` — implemented per
provider; nothing else touches a provider SDK. That is what makes the
tier/provider choice in §9 an env-var change, not a code change.

Phase 5 extends the Phase 3 client with OpenAI-style tool calling (§8.3/8.4):
`tools` carries the tool registry's JSON schemas; a response that requests
tool calls surfaces as `LLMResponse.tool_calls` for the agent loop to
execute. Token accounting (§8.6) is written by call sites from the response's
usage fields (`tokens_in/out`, `cached_tokens`).

Tier → model mapping (§9.1): free and cheap both ride the flash model (free
tier routing hardcodes it per the §8.1 note), powerful comes from settings.

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
class ToolCallRequest:
    """One tool the model wants executed (OpenAI-compatible shape)."""

    id: str
    name: str
    arguments: dict[str, Any]  # parsed from the JSON arguments string


@dataclass
class LLMResponse:
    content: str | None
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    tool_calls: list[ToolCallRequest] | None = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tier: str = "cheap",
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


class LiveGLMClient:
    """GLM family via an OpenAI-compatible chat-completions endpoint (§2).

    Model per tier comes from settings (LLM_PROVIDER_CHEAP /
    LLM_PROVIDER_POWERFUL); the §9.1 free tier rides the flash model, so
    "free" resolves to model_cheap here and free-tier call sites simply pass
    tier="free" for honest token_usage accounting.
    """

    def __init__(self, api_key: str, api_base: str, model_cheap: str, model_powerful: str) -> None:
        if not api_key:
            raise LLMError("GLM_API_KEY is not set — live LLM calls are unavailable")
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        # §9.1: the free tier IS the flash model — free-tier call sites pass
        # tier="free" and ride the same model as cheap.
        self._models = {"free": model_cheap, "cheap": model_cheap, "powerful": model_powerful}
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tier: str = "cheap",
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if tier not in self._models:
            raise LLMError(f"unknown tier {tier!r} (expected one of {sorted(self._models)})")
        payload_messages: list[dict[str, Any]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        payload: dict[str, Any] = {"model": self._models[tier], "messages": payload_messages}
        if tools:
            payload["tools"] = tools
        try:
            resp = await self._client.post(
                f"{self._api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"GLM completion failed: {exc}") from exc
        return parse_completion(body, fallback_model=self._models[tier])


def parse_completion(body: dict[str, Any], fallback_model: str) -> LLMResponse:
    """Shape an OpenAI-compatible chat-completions body into an LLMResponse.

    Pure function so the live client's parsing is unit-testable without HTTP.
    Tool calls parse defensively: unparsable JSON arguments raise LLMError —
    the agent loop converts that into a tool-error result, never a crash."""
    usage = body.get("usage") or {}
    message = body["choices"][0]["message"]
    cached = 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens") or 0)
    tool_calls = None
    raw_calls = message.get("tool_calls") or []
    if raw_calls:
        tool_calls = []
        for call in raw_calls:
            fn = call.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError as exc:
                raise LLMError(f"tool call {fn.get('name')!r}: unparsable arguments: {exc}") from exc
            tool_calls.append(
                ToolCallRequest(id=call.get("id") or "", name=fn.get("name") or "", arguments=arguments)
            )
    return LLMResponse(
        content=message.get("content"),
        model=body.get("model", fallback_model),
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        cached_tokens=cached,
        tool_calls=tool_calls,
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
