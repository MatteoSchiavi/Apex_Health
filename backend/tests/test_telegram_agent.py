"""Agent entrypoint tests (§10.2 free text → agent, §23 Phase 3 AC: free
text gets a real agent response). The LLM is fixture-backed; sessions and
chat logging hit the real database."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.agent.entrypoint import run_agent_turn
from app.connectors.telegram.handlers import handle_update
from app.models.chat import AiChatMessage, AiChatSession
from app.models.features import DailyFeature
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from app.core.llm import LLMResponse
from tests.helpers.ai import FixtureAgentLLMClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
)

CHAT = 42
REPLY = (Path(__file__).resolve().parent / "fixtures" / "telegram" / "chat_reply.txt").read_text().strip()


def classification(category: str) -> LLMResponse:
    return LLMResponse(
        content=f'{{"category": "{category}"}}', model="fixture-llm", tokens_in=90, tokens_out=5
    )


def final_reply(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="fixture-llm", tokens_in=800, tokens_out=120)


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


async def _seed_feature(ctx, owner: int, day, readiness: float = 71.0) -> None:
    async with ctx.sessionmaker() as session:
        session.add(
            DailyFeature(
                user_id=owner,
                date=day,
                recovery_score=78.0,
                strain_score=12.4,
                readiness_score=readiness,
                training_load_acute=812.0,
                training_load_chronic=670.0,
                acwr=1.21,
                data_completeness="full",
            )
        )
        await session.commit()


async def test_free_text_gets_real_agent_reply():
    """§23 Phase 3 AC: free text gets a real agent response — grounded in a
    data snapshot and logged to the chat tables. The owner's credential is
    'full' (§15 bootstrap), so the §9.2 router runs first (free tier) and
    tags this question 'lookup' → the chat turn rides the cheap tier."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [classification("lookup"), final_reply(REPLY)]
        )
        owner = await _link_chat(ctx, CHAT)
        await _seed_feature(ctx, owner, datetime(2025, 3, 9).date())

        await handle_update(ctx, load_update("text_free"))

        assert sent_texts(client) == [REPLY]
        prompt = llm.calls[1]["messages"][0]["content"]
        assert "recovery looking" in prompt  # the user's question
        assert '"readiness": 71.0' in llm.calls[1]["system"]  # grounded via the §8.4 system block
        assert [c["tier"] for c in llm.calls] == ["free", "cheap"]  # §9.2 routing sequence

        async with ctx.sessionmaker() as session:
            messages = (
                await session.scalars(select(AiChatMessage).order_by(AiChatMessage.id))
            ).all()
            assert [m.role for m in messages] == ["user", "assistant"]
            assert messages[1].model_tier == "cheap"
            assert messages[1].referenced_data["latest"]["readiness"] == 71.0
            sessions = (await session.scalars(select(AiChatSession))).all()
            assert len(sessions) == 1


async def test_agent_without_data_says_what_it_can():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([final_reply(REPLY)])
        owner = await _link_chat(ctx, CHAT)
        await run_agent_turn(ctx.sessionmaker, llm, owner, "how is my recovery?", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC), tier="cheap")
        system = llm.calls[0]["system"]
        assert '"latest": null' in system
        # A-02/A-03 audit: trend_14d is now CALENDAR-COMPLETE — always 14
        # entries (one per day), each either a feature row or a gap marker
        # with "status": "no_feature_row". The old empty-list assertion
        # (trend_14d: []) is replaced by a check that the gap marker is
        # present when no feature rows exist.
        assert '"trend_14d":' in system
        assert '"no_feature_row"' in system or '"status": "no_feature_row"' in system


async def test_session_boundary_after_30_minutes():
    """§6.4: a new session row when the user messages after >30 idle minutes."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient([final_reply(REPLY), final_reply(REPLY), final_reply(REPLY)])
        owner = await _link_chat(ctx, CHAT)
        t0 = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)

        r1 = await run_agent_turn(ctx.sessionmaker, llm, owner, "one", now=t0, tier="cheap")
        r2 = await run_agent_turn(ctx.sessionmaker, llm, owner, "two", now=t0 + timedelta(minutes=10), tier="cheap")
        r3 = await run_agent_turn(ctx.sessionmaker, llm, owner, "three", now=t0 + timedelta(minutes=50), tier="cheap")

        assert r1.session_id == r2.session_id  # within 30 min → same session
        assert r3.session_id != r1.session_id  # 50 min idle → new session
        async with ctx.sessionmaker() as session:
            sessions = (await session.scalars(select(AiChatSession))).all()
            assert len(sessions) == 2
            messages = (await session.scalars(select(AiChatMessage))).all()
            assert len(messages) == 6  # 3 user + 3 assistant
