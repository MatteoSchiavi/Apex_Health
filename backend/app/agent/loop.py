"""Agent loop (MASTER_SPEC §8.4).

One turn = up to 8 LLM/tool iterations. Each LLM call logs to token_usage
(§8.6); each tool execution goes through the §8.3 registry, logs to
agent_tool_calls (session_id nullable for non-chat callers), and returns
tool results as data — tool errors NEVER kill the loop (§8.4). If the loop
doesn't converge inside the budget, the best partial answer is returned.

A-01 audit: ``history`` parameter accepts bounded prose-pair replay so
multi-turn coaching continuity works.

T-02 audit: tool calls execute in parallel with per-call timeouts.

T-03 audit: tool-result bytes are capped; oldest results truncate first.

T-04 audit: budget exhaustion triggers a forced tool-free summarization
close-out so the user never receives "Let me also check…" as the final answer.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.tools import TOOL_REGISTRY, ToolContext, tool_schemas
from app.core.llm import LLMError, LLMClient, LLMResponse, ToolCallRequest, jsonable
from app.models.ai import AgentToolCall
from app.queries.usage import log_llm_usage

logger = logging.getLogger("app.agent.loop")

MAX_ITERATIONS = 8  # §8.4: max 8 iterations, best partial answer on non-convergence

NO_CONVERGENCE_REPLY = (
    "I couldn't finish this request within the tool budget — here's what I have so far. "
    "Try narrowing the question."
)


@dataclass
class AgentLoopResult:
    reply: str
    tier: str
    model: str
    tool_audit: list[dict[str, Any]] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    converged: bool = False


def _assistant_tool_call_message(response: LLMResponse) -> dict[str, Any]:
    """OpenAI assistant message carrying the model's tool requests."""
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": _dumps(call.arguments)},
            }
            for call in (response.tool_calls or [])
        ],
    }


def _tool_result_message(call: ToolCallRequest, payload: dict[str, Any]) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call.id, "content": _dumps(payload)}


def _dumps(payload: Any) -> str:
    # F-28 audit: was `import json` (function-local shadowing the module
    # import). Use the module-level import — same behavior, no shadow.
    return json.dumps(payload, ensure_ascii=False, default=str)


async def _execute_tool(
    ctx: ToolContext, session_id: int | None, call: ToolCallRequest
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one tool call inside ctx.session: result payload + agent_tool_calls
    audit row. Returns (result, audit_entry); errors come back AS RESULTS."""
    started = time.monotonic()
    result: dict[str, Any]
    error: str | None = None
    spec = TOOL_REGISTRY.get(call.name)
    if spec is None:
        result = {
            "error": f"unknown tool {call.name!r} (available: {sorted(TOOL_REGISTRY)})"
        }
        error = result["error"]
    else:
        try:
            result = await spec.handler(ctx, **call.arguments)
        except LLMError as exc:  # unparsable tool arguments etc.
            result = {"error": str(exc)}
            error = str(exc)
        except TypeError as exc:  # wrong argument names/shapes from the model
            result = {"error": f"invalid arguments for {call.name}: {exc}"}
            error = result["error"]
        except Exception as exc:  # §8.4: tool errors are results, never crashes
            result = {"error": f"{type(exc).__name__}: {exc}"}
            error = result["error"]
    latency_ms = int((time.monotonic() - started) * 1000)

    result = jsonable(result)
    ctx.session.add(
        AgentToolCall(
            session_id=session_id,
            tool_name=call.name,
            input_json=call.arguments,
            output_json=None if error else result,
            error=error,
            latency_ms=latency_ms,
        )
    )
    audit = {
        "tool": call.name,
        "input": call.arguments,
        "output": result,
        "error": error,
        "latency_ms": latency_ms,
    }
    return result, audit


async def run_agent_loop(
    sessionmaker: async_sessionmaker,
    llm: LLMClient,
    *,
    user_id: int,
    session_id: int | None,
    text: str,
    system: str,
    tier: str,
    today: date,
    embedding_client: Any | None = None,
    history: list[dict[str, Any]] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    tool_budget_chars: int = 12_000,
) -> AgentLoopResult:
    """One agent turn (§8.4). Call_type for token_usage is 'chat' — scheduled
    report generation calls this with session_id=None if it ever needs the
    loop; direct one-shot completions log their own usage.

    A-01 audit: ``history`` carries the bounded prose-pair replay from the
    caller (the entrypoint loads the last N user+assistant messages from
    the same chat session). When provided, it is prepended to the messages
    list so multi-turn coaching continuity works.

    T-03 audit: ``tool_budget_chars`` caps the total bytes of tool-result
    messages in the running list — when exceeded, the oldest tool results
    are truncated to a ``{truncated: true}`` envelope so the loop cannot
    blow the provider context window with big tool payloads.
    """
    # A-01: prepend history (oldest-first prose pairs).
    base_messages: list[dict[str, Any]] = list(history or [])
    base_messages.append({"role": "user", "content": text})
    messages: list[dict[str, Any]] = list(base_messages)
    audit: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    best_partial: str | None = None
    last_model = "unknown"

    for iteration in range(1, max_iterations + 1):
        async with sessionmaker() as session:
            response = await llm.complete(
                messages=messages,
                system=system,
                tier=tier,
                tools=tool_schemas(),
            )
            last_model = response.model
            await log_llm_usage(
                session,
                user_id=user_id,
                call_type="chat",
                tier=tier,
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cached_tokens=response.cached_tokens,
            )
            if not response.wants_tools:
                await session.commit()
                return AgentLoopResult(
                    reply=response.content or "",
                    tier=tier,
                    model=response.model,
                    tool_audit=audit,
                    drafts=drafts,
                    iterations=iteration,
                    converged=True,
                )
            await session.commit()

        if response.content:  # remember the best prose seen so far
            best_partial = response.content

        messages.append(_assistant_tool_call_message(response))
        # T-02 audit: execute tool calls in parallel with per-call timeouts.
        tool_calls = response.tool_calls or []
        if len(tool_calls) > 1:
            tool_results = await asyncio.gather(
                *(
                    _execute_tool_bounded(sessionmaker, user_id, today, session_id, call, embedding_client)
                    for call in tool_calls
                ),
                return_exceptions=True,
            )
            for call, outcome in zip(tool_calls, tool_results):
                if isinstance(outcome, BaseException):
                    result = {"error": f"{type(outcome).__name__}: {outcome}"}
                    entry = {
                        "tool": call.name,
                        "input": call.arguments,
                        "output": result,
                        "error": result["error"],
                        "latency_ms": 0,
                    }
                    audit.append(entry)
                    messages.append(_tool_result_message(call, result))
                    continue
                result, entry = outcome
                audit.append(entry)
                if "plan_id" in result:
                    drafts.append({"type": "training_plan", "id": result["plan_id"]})
                elif "protocol_id" in result:
                    drafts.append({"type": "supplement", "id": result["protocol_id"]})
                messages.append(_tool_result_message(call, result))
        else:
            for call in tool_calls:
                async with sessionmaker() as session:
                    ctx = ToolContext(
                        session=session,
                        user_id=user_id,
                        today=today,
                        embedding_client=embedding_client,
                    )
                    result, entry = await _execute_tool(ctx, session_id, call)
                    await session.commit()
                audit.append(entry)
                if "plan_id" in result:
                    drafts.append({"type": "training_plan", "id": result["plan_id"]})
                elif "protocol_id" in result:
                    drafts.append({"type": "supplement", "id": result["protocol_id"]})
                messages.append(_tool_result_message(call, result))

        # T-03 audit: cap total tool-result bytes — truncate oldest first.
        messages = _enforce_tool_budget(messages, tool_budget_chars)

    # T-04 audit: budget exhausted → ALWAYS attempt a forced tool-free
    # summarization close-out so the user never receives "Let me also check…"
    # as the final answer. The previous conservative check (only when
    # best_partial trailed off) still left mid-sentence partials as the
    # final reply. Now we always try; on LLMError we fall back to the
    # best partial.
    try:
        async with sessionmaker() as session:
            final = await llm.complete(
                messages=messages
                + [
                    {
                        "role": "user",
                        "content": (
                            "Tool budget exhausted. Summarize the findings so far "
                            "in a complete, self-contained answer — no tool calls. "
                            "If you have enough to answer, answer now; if not, say "
                            "what you'd need next."
                        ),
                    }
                ],
                system=system,
                tier=tier,
                tools=None,
            )
            await log_llm_usage(
                session,
                user_id=user_id,
                call_type="chat",
                tier=tier,
                model=final.model,
                tokens_in=final.tokens_in,
                tokens_out=final.tokens_out,
                cached_tokens=final.cached_tokens,
            )
            await session.commit()
        if final.content and final.content.strip():
            return AgentLoopResult(
                reply=final.content,
                tier=tier,
                model=final.model,
                tool_audit=audit,
                drafts=drafts,
                iterations=max_iterations,
                converged=False,
            )
    except LLMError:
        pass  # fall through to best_partial

    # Budget exhausted → §8.4 best partial answer.
    return AgentLoopResult(
        reply=best_partial or NO_CONVERGENCE_REPLY,
        tier=tier,
        model=last_model,
        tool_audit=audit,
        drafts=drafts,
        iterations=max_iterations,
        converged=False,
    )


async def _execute_tool_bounded(
    sessionmaker: async_sessionmaker,
    user_id: int,
    today: date,
    session_id: int | None,
    call: ToolCallRequest,
    embedding_client: Any | None,
    timeout_s: float = 15.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """T-02 audit: execute one tool call with a per-call timeout.

    On timeout the tool result is an error envelope (the loop converts it
    to a tool-result message) — the loop itself never crashes.
    """
    try:
        async with asyncio.timeout(timeout_s):
            async with sessionmaker() as session:
                ctx = ToolContext(
                    session=session,
                    user_id=user_id,
                    today=today,
                    embedding_client=embedding_client,
                )
                result, entry = await _execute_tool(ctx, session_id, call)
                await session.commit()
            return result, entry
    except (asyncio.TimeoutError, Exception) as exc:
        result = {"error": f"tool {call.name} timed out or crashed: {type(exc).__name__}: {exc}"}
        entry = {
            "tool": call.name,
            "input": call.arguments,
            "output": result,
            "error": result["error"],
            "latency_ms": int(timeout_s * 1000),
        }
        return result, entry


def _enforce_tool_budget(
    messages: list[dict[str, Any]], budget_chars: int
) -> list[dict[str, Any]]:
    """T-03 audit: cap total tool-result bytes — truncate oldest first.

    Tool result messages (role='tool') are the only unbounded payload source.
    When their cumulative size exceeds ``budget_chars``, the oldest tool
    results are replaced with a ``{truncated: true, original_chars: N}``
    envelope so the loop cannot blow the provider context window.
    """
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if not tool_indices:
        return messages
    total = sum(len(m.get("content", "")) for i, m in enumerate(messages) if i in tool_indices)
    if total <= budget_chars:
        return messages
    # Truncate oldest tool results until under budget.
    for i in tool_indices:
        if total <= budget_chars:
            break
        content = messages[i].get("content", "")
        if len(content) <= 100:
            continue
        original_chars = len(content)
        messages[i] = {
            **messages[i],
            "content": json.dumps(
                {"truncated": True, "original_chars": original_chars, "note": "payload capped to fit context budget"},
                ensure_ascii=False,
            ),
        }
        total -= original_chars - len(messages[i]["content"])
    return messages
