"""Voice-note pipeline tests (§10.2, §23 Phase 3 AC: a linked chat's voice
note produces a confirmable draft). Telegram/LLM/STT traffic is entirely
fixture-backed; only the database is real."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from app.connectors.telegram.handlers import LINK_INSTRUCTIONS, handle_update
from app.connectors.telegram.voice import VoiceDeps, run_voice_pipeline
from app.models.activity import Activity, Discipline
from app.models.journal import JournalEntry
from app.models.telegram import TelegramLink, TelegramMessage
from app.models.user import AuthCredential
from tests.helpers.ai import FixtureLLMClient, FixtureSTT
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
    with_callback_data,
)

CHAT = 42
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "telegram"
TRANSCRIPT = (FIXTURES / "transcript.txt").read_text().strip()
EXTRACTION = json.loads((FIXTURES / "extraction.json").read_text())
EXTRACTION_EDITED = json.loads((FIXTURES / "extraction_edited.json").read_text())


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


def _make_dispatcher(ctx, telegram, llm):
    stt = FixtureSTT(TRANSCRIPT)

    async def dispatch(**kwargs):
        await run_voice_pipeline(
            VoiceDeps(telegram=telegram, llm=llm, stt=stt), ctx.sessionmaker, **kwargs
        )

    return dispatch


async def _produce_draft(client: FixtureTelegramClient, ctx) -> TelegramMessage:
    await handle_update(ctx, load_update("voice_note"))
    async with ctx.sessionmaker() as session:
        return (await session.scalars(select(TelegramMessage))).one()


async def test_voice_note_produces_confirmable_draft():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        llm = FixtureLLMClient([json.dumps(EXTRACTION)])
        ctx.dispatch_voice = _make_dispatcher(ctx, client, llm)

        await handle_update(ctx, load_update("voice_note"))

        # ack first, then the draft (§10.2)
        texts = sent_texts(client)
        assert "structuring" in texts[0].lower()
        draft = client.sent_messages[1]
        assert EXTRACTION["summary"] in draft["text"]

        async with ctx.sessionmaker() as session:
            row = (await session.scalars(select(TelegramMessage))).one()
            assert row.status == "pending"
            assert row.raw_transcript == TRANSCRIPT
            assert row.extracted_json["extraction"]["discipline"] == "road_cycling"
            assert row.extracted_json["message_ts"] == 1741530000
        buttons = draft["reply_markup"]["inline_keyboard"][0]
        assert buttons[0] == {"text": "✅ Save", "callback_data": f"voice:confirm:{row.id}"}
        assert buttons[1] == {"text": "✏️ Edit", "callback_data": f"voice:edit:{row.id}"}
        # extraction prompt went to the model with the transcript
        assert TRANSCRIPT in llm.calls[0]["messages"][0]["content"]


async def test_confirm_writes_journal_entry_idempotently():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        llm = FixtureLLMClient([json.dumps(EXTRACTION)])
        ctx.dispatch_voice = _make_dispatcher(ctx, client, llm)
        row = await _produce_draft(client, ctx)

        callback = with_callback_data(load_update("callback_confirm"), f"voice:confirm:{row.id}")
        await handle_update(ctx, callback)

        async with ctx.sessionmaker() as session:
            row = await session.get(TelegramMessage, row.id)
            assert row.status == "confirmed"
            entry = await session.get(JournalEntry, row.linked_journal_entry_id)
            assert entry.source == "telegram_voice"
            assert entry.date == date(2025, 3, 9)  # §17: local date of the note
            assert int(entry.mood_score) == 7
            assert float(entry.soreness_score) == 3.0
            assert entry.tags == EXTRACTION["tags"]
            assert entry.raw_transcript == TRANSCRIPT
        assert "saved" in sent_texts(client)[-1].lower()
        assert client.callback_answers[-1]["text"].startswith("Saved as journal entry #")

        # second confirm: no-op, nothing duplicated
        await handle_update(ctx, callback)
        async with ctx.sessionmaker() as session:
            assert len((await session.scalars(select(JournalEntry))).all()) == 1
            assert (await session.get(TelegramMessage, row.id)).status == "confirmed"
        assert client.callback_answers[-1]["text"] == "Already saved."


async def test_edit_flow_replaces_draft():
    client = FixtureTelegramClient()
    async with bot_context(client, llm_factory=lambda: llm) as ctx:
        llm = FixtureLLMClient([json.dumps(EXTRACTION), json.dumps(EXTRACTION_EDITED)])
        await _link_chat(ctx, CHAT)
        ctx.dispatch_voice = _make_dispatcher(ctx, client, llm)
        row = await _produce_draft(client, ctx)

        await handle_update(ctx, with_callback_data(load_update("callback_edit"), f"voice:edit:{row.id}"))
        assert "corrections" in sent_texts(client)[-1].lower()
        assert await ctx.redis.get(f"tg:edit:{CHAT}") == str(row.id)

        await handle_update(ctx, load_update("text_edit_correction"))

        # corrections reached the extraction call, new draft reflects them
        assert "commuting" in llm.calls[1]["messages"][0]["content"]
        texts = sent_texts(client)
        assert "commuting" in texts[-1]
        async with ctx.sessionmaker() as session:
            rows = (
                await session.scalars(select(TelegramMessage).order_by(TelegramMessage.id))
            ).all()
            assert [r.status for r in rows] == ["rejected", "pending"]
            assert rows[1].extracted_json["extraction"]["soreness_score"] == 7
        # edit state consumed
        assert await ctx.redis.get(f"tg:edit:{CHAT}") is None


async def test_voice_from_unlinked_chat_gets_link_instructions():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:  # dispatcher would raise if used
        await handle_update(ctx, load_update("voice_note"))
    assert sent_texts(client) == [LINK_INSTRUCTIONS]


async def test_draft_references_activity_in_window():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        async with ctx.sessionmaker() as session:
            discipline = (
                await session.scalars(
                    select(Discipline).where(Discipline.name == "road_cycling")
                )
            ).one()
            # session 11:30Z -> 14:30Z; note lands 14:20Z — inside the window
            session.add(
                Activity(
                    user_id=owner,
                    discipline_id=discipline.id,
                    start_time=datetime(2025, 3, 9, 11, 30, tzinfo=UTC),
                    start_tz_offset_minutes=60,
                    local_date=date(2025, 3, 9),
                    duration_s=10800,
                )
            )
            await session.commit()

        llm = FixtureLLMClient([json.dumps(EXTRACTION)])
        ctx.dispatch_voice = _make_dispatcher(ctx, client, llm)
        await handle_update(ctx, load_update("voice_note"))

        draft_text = sent_texts(client)[-1]
        assert "Context: road_cycling session" in draft_text


async def test_voice_redelivery_creates_single_draft():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        llm = FixtureLLMClient([json.dumps(EXTRACTION)])
        ctx.dispatch_voice = _make_dispatcher(ctx, client, llm)
        update = load_update("voice_note")

        await handle_update(ctx, update)
        await handle_update(ctx, update)  # Telegram redelivery

        async with ctx.sessionmaker() as session:
            rows = (await session.scalars(select(TelegramMessage))).all()
        assert len(rows) == 1
        assert sum(1 for t in sent_texts(client) if "Journal draft" in t) == 1
