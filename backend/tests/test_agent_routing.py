"""Routing tests (§9.2) — the Phase 5 acceptance criterion: a cheap_only
account NEVER reaches the powerful tier (§23 Phase 5 AC2), plus the full-tier
classification path and fail-closed behavior."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.agent.entrypoint import run_agent_turn
from app.agent.routing import resolve_tier
from app.models.ai import TokenUsage
from app.models.chat import AiChatMessage
from app.models.user import AuthCredential
from tests.helpers.ai import FixtureAgentLLMClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
)

NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def final(content: str):
    from app.core.llm import LLMResponse

    return LLMResponse(content=content, model="fixture-llm", tokens_in=800, tokens_out=120)


def classification(category: str):
    from app.core.llm import LLMResponse

    return LLMResponse(
        content=f'{{"category": "{category}"}}', model="fixture-llm", tokens_in=90, tokens_out=5
    )


async def _owner_id(ctx) -> int:
    async with ctx.sessionmaker() as session:
        return (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()


async def _set_tier(ctx, user_id: int, tier: str) -> None:
    async with ctx.sessionmaker() as session:
        cred = await session.get(AuthCredential, user_id)
        cred.ai_access_tier = tier
        await session.commit()


async def test_cheap_only_never_reaches_powerful():
    """§23 Phase 5 AC2: with ai_access_tier='cheap_only' even an obviously
    strategic message runs cheap — and no classification call ever happens."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        # The fixture would happily serve a powerful-tier turn; it must never
        # be asked for one. One scripted reply = one loop turn.
        llm = FixtureAgentLLMClient([final("Here is a plan.")])
        owner = await _owner_id(ctx)  # owner defaults to cheap_only
        decision = await _set_tier(ctx, owner, "cheap_only")

        result = await run_agent_turn(ctx.sessionmaker, llm, owner, "design me a 4-week block", now=NOW)

        assert result.reply == "Here is a plan."
        assert all(call["tier"] != "powerful" for call in llm.calls)
        assert len(llm.calls) == 1 and llm.calls[0]["tier"] == "cheap"
        async with ctx.sessionmaker() as session:
            message = (
                await session.scalars(
                    select(AiChatMessage).where(AiChatMessage.role == "assistant")
                )
            ).one()
            assert message.model_tier == "cheap"
            # no routing_classification usage row — cheap_only skips the router
            rows = (await session.scalars(select(TokenUsage))).all()
            assert all(u.call_type != "routing_classification" for u in rows)

        # and the routing decision itself, directly:
        async with ctx.sessionmaker() as session:
            decision = await resolve_tier(session, owner, "design me a 4-week block", llm)
        assert decision.tier == "cheap"
        assert decision.classification is None
        assert decision.cap == "cheap_only"


async def test_full_tier_strategic_goes_powerful():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([classification("strategic"), final("Periodization advice…")])
        owner = await _owner_id(ctx)
        await _set_tier(ctx, owner, "full")

        result = await run_agent_turn(ctx.sessionmaker, llm, owner, "rebuild my base for months", now=NOW)

        assert [c["tier"] for c in llm.calls] == ["free", "powerful"]
        assert result.reply == "Periodization advice…"
        async with ctx.sessionmaker() as session:
            message = (
                await session.scalars(
                    select(AiChatMessage).where(AiChatMessage.role == "assistant")
                )
            ).one()
            assert message.model_tier == "powerful"
            routing_rows = (
                await session.scalars(
                    select(TokenUsage).where(TokenUsage.call_type == "routing_classification")
                )
            ).all()
            assert len(routing_rows) == 1
            assert routing_rows[0].tier == "free"


async def test_full_tier_lookup_stays_cheap():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([classification("lookup"), final("Recovery is 42.")])
        owner = await _owner_id(ctx)
        await _set_tier(ctx, owner, "full")

        await run_agent_turn(ctx.sessionmaker, llm, owner, "how is my recovery?", now=NOW)

        assert [c["tier"] for c in llm.calls] == ["free", "cheap"]


async def test_classification_failure_fails_closed_to_cheap():
    """Unparsable classification → lookup (cheap). Surprises cost less."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([final("I am not JSON."), final("Answer.")])
        owner = await _owner_id(ctx)
        await _set_tier(ctx, owner, "full")

        result = await run_agent_turn(ctx.sessionmaker, llm, owner, "strategic things", now=NOW)

        assert [c["tier"] for c in llm.calls] == ["free", "cheap"]
        assert result.reply == "Answer."


async def test_missing_credential_row_caps_at_cheap():
    """The DB CHECK pins ai_access_tier to ('cheap_only','full'), so garbage
    values cannot exist in storage — the app-layer fail-closed branch covers
    a MISSING credential row instead (routing must cap, not crash)."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([final("Answer.")])
        owner = await _owner_id(ctx)

        async with ctx.sessionmaker() as session:
            from app.models.user import User

            session.add(User(name="Ghost", timezone="Europe/Rome"))
            await session.commit()
            ghost_id = (
                await session.scalars(select(User.id).where(User.name == "Ghost"))
            ).first()
        # ghost has no AuthCredential row

        async with ctx.sessionmaker() as session:
            decision = await resolve_tier(session, ghost_id, "anything", llm)
        assert decision.tier == "cheap"
        assert decision.cap == "cheap_only"

        await run_agent_turn(ctx.sessionmaker, llm, ghost_id, "anything", now=NOW)
        assert [c["tier"] for c in llm.calls] == ["cheap"]
