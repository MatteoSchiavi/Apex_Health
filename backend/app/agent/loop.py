"""Agent loop (MASTER_SPEC §8.4).

One turn = up to 8 LLM/tool iterations. Each LLM call logs to token_usage
(§8.6); each tool execution goes through the §8.3 registry, logs to
agent_tool_calls (session_id nullable for non-chat callers), and returns
tool results as data — tool errors NEVER kill the loop (§8.4). If the loop
doesn't converge inside the budget, the best partial answer is returned.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.tools import TOOL_REGISTRY, ToolContext, tool_schemas
from app.core.llm import LLMError, LLMClient, LLMResponse, ToolCallRequest
from app.models.ai import AgentToolCall
from app.queries.usage import log_llm_usage

logger = logging.getLogger("app.agent.loop")

MAX_ITERATIONS = 8  # §8.4: max 8 iterations, best partial answer on non-convergence

NO_CONVERGENCE_REPLY = (
    "I couldn't finish this request within the tool budget — here's what I have so far. "
    "Try narrowing the question."
)


def _jsonable(value: Any) -> Any:
    """Recursively coerce a tool payload into JSONB-safe types (date/datetime
    → ISO strings, Decimal → float). agent_tool_calls and the tool message
    payloads must never fail on serialization — a handler returning a raw
    date is a logging bug, not a crash."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


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
    import json

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

    result = _jsonable(result)
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
) -> AgentLoopResult:
    """One agent turn (§8.4). Call_type for token_usage is 'chat' — scheduled
    report generation calls this with session_id=None if it ever needs the
    loop; direct one-shot completions log their own usage."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": text}]
    audit: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    best_partial: str | None = None
    last_model = "unknown"

    for iteration in range(1, MAX_ITERATIONS + 1):
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
        for call in response.tool_calls or []:
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

    # Budget exhausted → §8.4 best partial answer.
    return AgentLoopResult(
        reply=best_partial or NO_CONVERGENCE_REPLY,
        tier=tier,
        model=last_model,
        tool_audit=audit,
        drafts=drafts,
        iterations=MAX_ITERATIONS,
        converged=False,
    )
