"""§8.5 write-tool confirmation flow end-to-end: the agent drafts a plan or
supplement change, the bot attaches the inline keyboard, the callback
confirms/rejects. Plus the §8.3 search_context tool over the embedded
journal/report corpus (§6.2 pinned model, fixture client)."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.agent.entrypoint import run_agent_turn
from app.connectors.telegram.handlers import handle_update
from app.models.ai import Embedding, TokenUsage
from app.models.medical import SupplementProtocol
from app.models.telegram import TelegramLink
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential
from app.queries.plans import confirm_plan_draft, create_supplement_draft
from tests.helpers.ai import FixtureAgentLLMClient, FixtureEmbeddingClient
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
    with_callback_data,
    with_text,
)

CHAT = 42
NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def tool_request(call_id: str, name: str, **kwargs):
    from app.core.llm import LLMResponse, ToolCallRequest

    return LLMResponse(
        content=None,
        model="fixture-llm",
        tool_calls=[ToolCallRequest(id=call_id, name=name, arguments=kwargs)],
    )


def final(content: str):
    from app.core.llm import LLMResponse

    return LLMResponse(content=content, model="fixture-llm")


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


async def _cap_owner_at_cheap(ctx, user_id: int) -> None:
    async with ctx.sessionmaker() as session:
        cred = await session.get(AuthCredential, user_id)
        cred.ai_access_tier = "cheap_only"
        await session.commit()


async def test_proposed_plan_arrives_with_confirm_keyboard_and_confirms():
    """§8.5 end-to-end: propose → keyboard under the bot reply → tap ✅ →
    plan confirmed (never auto-applied by the agent)."""
    client = FixtureTelegramClient()
    async with bot_context(
        client,
        llm_factory=lambda: llm,
        embeddings_factory=lambda: FixtureEmbeddingClient(),
    ) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request(
                    "c1",
                    "propose_training_plan",
                    week_start="2025-03-10",
                    sessions=[{"date": "2025-03-11", "session_type": "endurance", "target_duration_min": 60}],
                ),
                final("Here's a draft week — confirm below."),
            ]
        )
        owner = await _link_chat(ctx, CHAT)
        await _cap_owner_at_cheap(ctx, owner)

        await handle_update(ctx, with_text(load_update("text_free"), "plan my week"))

        # reply carries the §8.5 inline keyboard
        assert client.sent_messages[0]["text"] == "Here's a draft week — confirm below."
        keyboard = client.sent_messages[0]["reply_markup"]
        plan_id = keyboard["inline_keyboard"][0][0]["callback_data"].split(":")[2]
        assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"plan:confirm:{plan_id}"

        async with ctx.sessionmaker() as session:
            plan = await session.get(TrainingPlan, int(plan_id))
            assert plan.status == "draft"  # draft until the human says so

        # tap ✅
        await handle_update(
            ctx, with_callback_data(load_update("callback_confirm"), f"plan:confirm:{plan_id}")
        )
        assert "Confirmed." in client.callback_answers[-1]["text"]
        async with ctx.sessionmaker() as session:
            plan = await session.get(TrainingPlan, int(plan_id))
            assert plan.status == "confirmed"  # §8.5: only the human confirms

        # tap ✅ again → already handled, no change
        await handle_update(
            ctx, with_callback_data(load_update("callback_confirm"), f"plan:confirm:{plan_id}")
        )
        assert client.callback_answers[-1]["text"] == "That draft was already handled."


async def test_plan_reject_deletes_the_draft():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request(
                    "c1",
                    "propose_training_plan",
                    week_start="2025-03-10",
                    sessions=[{"date": "2025-03-12", "session_type": "rest"}],
                ),
                final("Draft ready — or discard it."),
            ]
        )
        owner = await _link_chat(ctx, CHAT)
        await _cap_owner_at_cheap(ctx, owner)

        await handle_update(ctx, with_text(load_update("text_free"), "plan my week"))
        keyboard = client.sent_messages[0]["reply_markup"]
        plan_id = int(keyboard["inline_keyboard"][0][1]["callback_data"].split(":")[2])

        await handle_update(
            ctx, with_callback_data(load_update("callback_confirm"), f"plan:reject:{plan_id}")
        )
        async with ctx.sessionmaker() as session:
            assert await session.get(TrainingPlan, plan_id) is None  # §6.4 has no 'rejected'
            assert (await session.scalars(select(PlannedSession))).all() == []


async def test_supplement_proposal_confirms_and_replaces_old_protocol():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request(
                    "c1",
                    "propose_supplement_change",
                    supplement_name="Iron",
                    dose="40 mg every other day",
                    reason="ferritin 21 ng/mL",
                ),
                final("Proposed an iron protocol change — confirm below."),
            ]
        )
        owner = await _link_chat(ctx, CHAT)
        await _cap_owner_at_cheap(ctx, owner)

        # the protocol being replaced
        async with ctx.sessionmaker() as session:
            old = SupplementProtocol(
                user_id=owner, supplement_name="Iron", dose="25 mg", active=True
            )
            session.add(old)
            await session.commit()

        await handle_update(ctx, with_text(load_update("text_free"), "fix my iron"))
        keyboard = client.sent_messages[0]["reply_markup"]
        protocol_id = int(keyboard["inline_keyboard"][0][0]["callback_data"].split(":")[2])

        await handle_update(
            ctx, with_callback_data(load_update("callback_confirm"), f"supp:confirm:{protocol_id}")
        )
        async with ctx.sessionmaker() as session:
            new = await session.get(SupplementProtocol, protocol_id)
            assert new.active is True
            old = await session.get(SupplementProtocol, old.id)  # re-fetch in this session
            assert old.active is False  # replaced, not duplicated (§8.5)


async def test_journal_save_is_embedded_and_searchable():
    """§6.2 + §8.3 loop: confirmed journal entry → embedding row (+ §8.6
    usage) → search_context returns it for a fuzzy query."""
    client = FixtureTelegramClient()
    embeddings = FixtureEmbeddingClient()
    async with bot_context(
        client,
        llm_factory=lambda: llm,
        embeddings_factory=lambda: embeddings,
    ) as ctx:
        owner = await _link_chat(ctx, CHAT)
        await _cap_owner_at_cheap(ctx, owner)

        # a saved journal entry with an embedding — mirroring confirm_draft's
        # write-time hook (store + §8.6 usage row)
        async with ctx.sessionmaker() as session:
            from app.models.journal import JournalEntry
            from app.queries.search import embed_journal_entry
            from app.queries.usage import log_embedding_usage

            entry = JournalEntry(
                user_id=owner,
                date=NOW.date(),
                free_text_notes="left knee felt sharp on downhills after the long run",
                tags=["knee"],
                source="telegram_voice",
            )
            session.add(entry)
            await session.flush()
            embed_result = await embed_journal_entry(
                session, embeddings, owner, entry.id, entry.free_text_notes
            )
            await log_embedding_usage(
                session, user_id=owner, model=embed_result.model, tokens_in=embed_result.tokens_in
            )
            await session.commit()
            entry_id = entry.id

        # the agent answers a fuzzy question through search_context
        llm = FixtureAgentLLMClient(
            [
                tool_request("c1", "search_context", query="knee pain downhills"),
                final("Fuzzy memory question answered from search_context."),
            ]
        )
        result = await run_agent_turn(
            ctx.sessionmaker, llm, owner, "why did my knee hurt?", now=NOW,
            embedding_client=embeddings,
        )

        assert result.reply.endswith("from search_context.")
        audit = result.loop.tool_audit
        assert len(audit) == 1 and audit[0]["tool"] == "search_context"
        hits = audit[0]["output"]["hits"]
        assert hits and hits[0]["source_table"] == "journal_entries"
        assert hits[0]["source_id"] == entry_id

        async with ctx.sessionmaker() as session:
            rows = (await session.scalars(select(Embedding))).all()
            assert len(rows) == 1 and rows[0].source_table == "journal_entries"
            usage = (
                await session.scalars(
                    select(TokenUsage).where(TokenUsage.call_type == "embedding")
                )
            ).all()
            assert len(usage) == 1 and usage[0].tokens_in == 12


async def test_search_context_without_embedding_client_degrades_cleanly():
    """No OPENAI_API_KEY → the tool returns a readable result; the loop and
    the bot reply survive (§8.4 errors-as-results)."""
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureAgentLLMClient(
            [
                tool_request("c1", "search_context", query="knee"),
                final("I couldn't search this time."),
            ]
        )
        owner = await _link_chat(ctx, CHAT)
        await _cap_owner_at_cheap(ctx, owner)

        result = await run_agent_turn(ctx.sessionmaker, llm, owner, "knee?", now=NOW)

        assert result.reply == "I couldn't search this time."
        assert "unavailable" in result.loop.tool_audit[0]["output"]["error"]
