"""Agent loop tests (§8.4) — the Phase 5 acceptance criterion: a ≥2-tool-call
query answers correctly and logs to agent_tool_calls (§23 Phase 5 AC1). Tool
errors surface as results (§8.4); non-convergence returns the best partial."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.agent.entrypoint import run_agent_turn
from app.connectors.telegram.handlers import handle_update
from app.models.ai import AgentToolCall, TokenUsage
from app.models.chat import AiChatMessage
from app.models.features import DailyFeature
from app.models.medical import LabPanel, LabMetric
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from app.queries.usage import day_spend
from tests.helpers.ai import FixtureAgentLLMClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
)

CHAT = 42
TODAY = datetime(2025, 3, 10).date()


def tool_request(call_id: str, name: str, **kwargs):
    from app.core.llm import LLMResponse, ToolCallRequest

    return LLMResponse(
        content=None,
        model="fixture-llm",
        tokens_in=500,
        tokens_out=40,
        tool_calls=[ToolCallRequest(id=call_id, name=name, arguments=kwargs)],
    )


def final(content: str):
    from app.core.llm import LLMResponse

    return LLMResponse(content=content, model="fixture-llm", tokens_in=800, tokens_out=120)


async def _seed_data(ctx, owner: int) -> None:
    async with ctx.sessionmaker() as session:
        panel = LabPanel(
            user_id=owner,
            date=datetime(2025, 3, 1).date(),
            panel_type="blood",
        )
        session.add(panel)
        await session.flush()
        session.add_all(
            [
                DailyFeature(
                    user_id=owner,
                    date=TODAY,
                    recovery_score=42.0,
                    readiness_score=51.0,
                    strain_score=18.2,
                    training_load_acute=910.0,
                    training_load_chronic=650.0,
                    acwr=1.40,
                    data_completeness="full",
                ),
                LabMetric(
                    lab_panel_id=panel.id,
                    metric_name="ferritin",
                    value=21.0,
                    unit="ng/mL",
                    ref_low=30.0,
                ),
            ]
        )
        await session.commit()


async def _link_chat(ctx, chat_id: int) -> int:
    async with ctx.sessionmaker() as session:
        owner = (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()
        session.add(TelegramLink(user_id=owner, chat_id=chat_id))
        await session.commit()
    return owner


async def _owner_id(ctx) -> int:
    async with ctx.sessionmaker() as session:
        return (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()


async def test_two_tool_query_answers_and_logs_to_agent_tool_calls():
    """§23 Phase 5 AC1: a ≥2-tool-call query answers correctly and logs to
    agent_tool_calls."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request("c1", "get_metric_trend", metric="recovery",
                             start_date="2025-03-01", end_date="2025-03-10"),
                tool_request("c2", "get_lab_trend", marker="ferritin"),
                final("Recovery is low (42) and ferritin is 21 µg/L — both point at iron."),
            ]
        )
        owner = await _link_chat(ctx, CHAT)
        await _seed_data(ctx, owner)

        await handle_update(ctx, load_update("text_free"))

        # correct final answer, grounded in both tool results
        assert sent_texts(client) == [
            "Recovery is low (42) and ferritin is 21 µg/L — both point at iron."
        ]
        # both tool calls logged with session linkage, inputs, outputs, latency
        async with ctx.sessionmaker() as session:
            rows = (
                await session.scalars(select(AgentToolCall).order_by(AgentToolCall.id))
            ).all()
            assert [r.tool_name for r in rows] == ["get_metric_trend", "get_lab_trend"]
            assert all(r.session_id is not None for r in rows)
            assert rows[0].input_json["metric"] == "recovery"
            assert rows[0].output_json["rows"][0]["value"] == 42.0
            assert rows[1].output_json["rows"][0]["value"] == 21.0
            assert all(r.error is None and r.latency_ms is not None for r in rows)

            # final chat message carries the audit trail + tier
            messages = (
                await session.scalars(
                    select(AiChatMessage).order_by(AiChatMessage.id)
                )
            ).all()
            assert messages[-1].model_tier == "cheap"
            audit = messages[-1].referenced_data["tool_calls"]
            assert [a["tool"] for a in audit] == ["get_metric_trend", "get_lab_trend"]

            # every LLM call logged to token_usage (§8.6)
            usage = (await session.scalars(select(TokenUsage))).all()
            assert len(usage) == 3  # 2 tool iterations + final
            assert all(u.call_type == "chat" and u.tier == "cheap" for u in usage)
        # the model saw the tool schemas (§8.4 request build)
        assert len(llm.calls[0]["tools"]) == 11


async def test_tool_error_returns_as_result_and_loop_continues():
    """§8.4: tool errors are results, not exceptions that kill the loop —
    the model corrects course and still produces a final answer."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request("c1", "get_metric_trend", metric="nope",
                             start_date="2025-03-01", end_date="2025-03-10"),
                tool_request("c2", "get_metric_trend", metric="recovery",
                             start_date="2025-03-01", end_date="2025-03-10"),
                final("That metric doesn't exist; recovery is 42."),
            ]
        )
        owner = await _owner_id(ctx)
        await _seed_data(ctx, owner)

        result = await run_agent_turn(
            ctx.sessionmaker, llm, owner, "how is recovery?", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
        )

        assert result.reply == "That metric doesn't exist; recovery is 42."
        async with ctx.sessionmaker() as session:
            rows = (
                await session.scalars(select(AgentToolCall).order_by(AgentToolCall.id))
            ).all()
            assert rows[0].error is not None
            assert "unknown metric" in rows[0].error  # error rides the error column
            assert rows[0].output_json is None
            assert rows[1].error is None
            assert rows[1].output_json["rows"][0]["value"] == 42.0


async def test_loop_gives_best_partial_after_eight_iterations():
    """§8.4: max 8 iterations → best partial answer, no crash, audit intact."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [tool_request(f"c{i}", "get_donation_status") for i in range(8)]
            + [final("never reached")]
        )
        owner = await _owner_id(ctx)

        result = await run_agent_turn(
            ctx.sessionmaker, llm, owner, "loop forever", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
        )

        assert result.loop.converged is False
        assert result.loop.iterations == 8
        assert len(llm.calls) == 8  # the 9th scripted response is never consumed
        assert len(result.loop.tool_audit) == 8
        async with ctx.sessionmaker() as session:
            usage = (await session.scalars(select(TokenUsage))).all()
            assert len(usage) == 8
            spend = await day_spend(session, datetime.now(UTC))
            assert spend > 0


async def test_unknown_tool_name_is_a_readable_error():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request("c1", "delete_everything"),
                final("I don't actually have that tool."),
            ]
        )
        owner = await _owner_id(ctx)

        result = await run_agent_turn(
            ctx.sessionmaker, llm, owner, "do it", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
        )

        assert result.reply == "I don't actually have that tool."
        async with ctx.sessionmaker() as session:
            row = (await session.scalars(select(AgentToolCall))).one()
            assert "unknown tool" in row.error


async def test_plain_completion_still_works_without_tools():
    """A simple question that needs no tools: one iteration, chat logged."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([final("Sleep more.")])
        owner = await _owner_id(ctx)

        result = await run_agent_turn(
            ctx.sessionmaker, llm, owner, "any advice?", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
        )

        assert result.reply == "Sleep more."
        assert result.loop.iterations == 1
        assert result.loop.tool_audit == []
