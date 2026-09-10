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
from tests.helpers.ai import FixtureLLMClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
)

CHAT = 42
REPLY = (Path(__file__).resolve().parent / "fixtures" / "telegram" / "chat_reply.txt").read_text().strip()


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
    data snapshot and logged to the chat tables."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureLLMClient([REPLY])
        owner = await _link_chat(ctx, CHAT)
        await _seed_feature(ctx, owner, datetime(2025, 3, 9).date())

        await handle_update(ctx, load_update("text_free"))

        assert sent_texts(client) == [REPLY]
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "recovery looking" in prompt  # the user's question
        assert '"readiness": 71.0' in prompt  # grounded in the snapshot
        assert llm.calls[0]["tier"] == "cheap"

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
        llm = FixtureLLMClient([REPLY])
        owner = await _link_chat(ctx, CHAT)
        await run_agent_turn(ctx.sessionmaker, llm, owner, "how is my recovery?", now=datetime(2025, 3, 10, 8, 0, tzinfo=UTC))
        prompt = llm.calls[0]["messages"][0]["content"]
        assert '"latest": null' in prompt
        assert '"trend_7d": []' in prompt


async def test_session_boundary_after_30_minutes():
    """§6.4: a new session row when the user messages after >30 idle minutes."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureLLMClient([REPLY, REPLY, REPLY])
        owner = await _link_chat(ctx, CHAT)
        t0 = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)

        r1 = await run_agent_turn(ctx.sessionmaker, llm, owner, "one", now=t0)
        r2 = await run_agent_turn(ctx.sessionmaker, llm, owner, "two", now=t0 + timedelta(minutes=10))
        r3 = await run_agent_turn(ctx.sessionmaker, llm, owner, "three", now=t0 + timedelta(minutes=50))

        assert r1.session_id == r2.session_id  # within 30 min → same session
        assert r3.session_id != r1.session_id  # 50 min idle → new session
        async with ctx.sessionmaker() as session:
            sessions = (await session.scalars(select(AiChatSession))).all()
            assert len(sessions) == 2
            messages = (await session.scalars(select(AiChatMessage))).all()
            assert len(messages) == 6  # 3 user + 3 assistant
