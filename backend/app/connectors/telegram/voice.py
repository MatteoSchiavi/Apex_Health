"""Voice-note pipeline (§10.2).

Flow: voice message -> handler acknowledges -> Celery hand-off -> download
.ogg -> Whisper STT -> structured extraction (GLM flash — the §9.1 free-tier
model; per-account routing doesn't apply here because §9.2 hardcodes
transcript structuring to the free tier) -> a PENDING draft in
telegram_messages with ✅ Save / ✏️ Edit inline buttons.

Every extraction completion logs a token_usage row (§8.6) with tier='free'.

Never auto-commits: journal_entries is written only on the explicit Save
callback (§10.2, §17 write discipline). ✏️ Edit rejects the draft and a new
pending draft is created from the user's corrections (text message).

Activity linkage (§10.2 "linked to an existing activity if the timestamp
falls in its window"): §6.4 gives journal_entries no activity FK, so the
matched activity is surfaced as extraction CONTEXT — the draft references
it; the schema has no row linkage to write.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.llm import LLMClient, LLMResponse, extract_json_object
from app.models.activity import Activity, Discipline
from app.models.journal import JournalEntry
from app.models.telegram import TelegramMessage
from app.models.user import User

logger = logging.getLogger("connectors.telegram.voice")

EDIT_KEY = "tg:edit:{chat_id}"
EDIT_TTL_S = 900  # corrections window
# Voice notes land while stretching/showering: a note counts as "after the
# session" for up to this long past the activity end (context only, no row
# linkage — see module docstring).
ACTIVITY_CONTEXT_GRACE = timedelta(minutes=30)

EXTRACTION_SYSTEM_PROMPT = (
    "You structure voice notes for a personal training diary. Reply with ONLY "
    "a JSON object, no prose:\n"
    '{"discipline": <slug like road_cycling/running/strength or null>, '
    '"mood_score": <1-10 or null>, "energy_score": <1-10 or null>, '
    '"motivation_score": <1-10 or null>, "soreness_score": <1-10 or null>, '
    '"stress_subjective": <1-10 or null>, "sleep_quality_subjective": <1-10 or null>, '
    '"summary": <one plain sentence>, "tags": [<short lowercase tags>]}\n'
    "Include a score only when the speaker states it. Never invent numbers."
)

SCORE_FIELDS = (
    ("mood_score", "Mood"),
    ("energy_score", "Energy"),
    ("motivation_score", "Motivation"),
    ("soreness_score", "Soreness"),
    ("stress_subjective", "Stress"),
    ("sleep_quality_subjective", "Sleep quality"),
)


@dataclass
class VoiceDeps:
    """Injected clients: live in production (bot process), fixtures in tests
    (§0/§20 — no live Telegram/LLM/STT call ever happens in CI)."""

    telegram: object  # TelegramClient protocol
    llm: LLMClient
    stt: object  # STTClient protocol


def draft_keyboard(row_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Save", "callback_data": f"voice:confirm:{row_id}"},
                {"text": "✏️ Edit", "callback_data": f"voice:edit:{row_id}"},
            ]
        ]
    }


def render_draft(tz: ZoneInfo, extraction: dict, message_ts: int, activity_ctx: dict | None) -> str:
    when = datetime.fromtimestamp(message_ts, tz).strftime("%Y-%m-%d %H:%M")
    lines = [f"Journal draft — {when} ({tz.key})"]
    if activity_ctx:
        lines.append(f"Context: {activity_ctx['discipline']} session, started {activity_ctx['started_local']}")
    scores = " · ".join(
        f"{label} {extraction[key]}"
        for key, label in SCORE_FIELDS
        if extraction.get(key) is not None
    )
    if scores:
        lines.append(scores)
    if extraction.get("summary"):
        lines.append(f'"{extraction["summary"]}"')
    if extraction.get("discipline") and not activity_ctx:
        lines.append(f"Discipline: {extraction['discipline']}")
    tags = extraction.get("tags") or []
    if tags:
        lines.append("Tags: " + ", ".join(tags))
    return "\n".join(lines)


def _extraction_user_message(transcript: str, activity_ctx: dict | None, corrections: str | None) -> str:
    parts = [f"Transcript:\n{transcript}"]
    if activity_ctx:
        parts.append(
            f"Context: recorded around a {activity_ctx['discipline']} session "
            f"(started {activity_ctx['started_local']}, {activity_ctx['duration_min']} min)."
        )
    if corrections:
        parts.append(f"The speaker corrected an earlier draft. Apply these corrections:\n{corrections}")
    return "\n\n".join(parts)


async def _extract(
    llm: LLMClient, transcript: str, activity_ctx: dict | None, corrections: str | None
) -> tuple[dict, LLMResponse]:
    response = await llm.complete(
        messages=[{"role": "user", "content": _extraction_user_message(transcript, activity_ctx, corrections)}],
        system=EXTRACTION_SYSTEM_PROMPT,
        # §9.1: transcript structuring is the free tier — hardcoded, not
        # routed (§9.2); the free tier rides the flash model.
        tier="free",
    )
    return extract_json_object(response.content), response


async def _log_extraction_usage(
    sessionmaker: async_sessionmaker, user_id: int, response: LLMResponse
) -> None:
    """§8.6: every LLM call writes a token_usage row."""
    from app.queries.usage import log_llm_usage

    async with sessionmaker() as session:
        await log_llm_usage(
            session,
            user_id=user_id,
            call_type="voice_extraction",
            tier="free",
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cached_tokens=response.cached_tokens,
        )
        await session.commit()


async def _activity_context(session, user_id: int, message_ts: int) -> dict | None:
    """Most recent activity whose [start, end(+grace)] window contains the
    note timestamp (§10.2). Python-side window check: tiny candidate set,
    avoids interval arithmetic in SQL."""
    ts = datetime.fromtimestamp(message_ts, tz=UTC)
    rows = (
        await session.execute(
            select(Activity, Discipline.name)
            .join(Discipline, Activity.discipline_id == Discipline.id)
            .where(
                Activity.user_id == user_id,
                Activity.start_time <= ts,
                Activity.start_time >= ts - timedelta(hours=24),
            )
            .order_by(Activity.start_time.desc())
        )
    ).all()
    for activity, discipline_name in rows:
        end = activity.start_time + timedelta(seconds=activity.duration_s) + ACTIVITY_CONTEXT_GRACE
        if activity.start_time <= ts <= end:
            return {
                "activity_id": activity.id,
                "discipline": discipline_name,
                "started_local": activity.start_time.isoformat(),
                "duration_min": round(activity.duration_s / 60),
            }
    return None


async def run_voice_pipeline(
    deps: VoiceDeps,
    sessionmaker: async_sessionmaker,
    chat_id: int,
    message_id: int,
    voice_file_id: str,
    message_ts: int,
) -> None:
    """Full pipeline for one voice message. Crashes are logged by the caller
    (Celery / dispatcher), never propagated into the polling loop."""
    file_meta = await deps.telegram.get_file(voice_file_id)
    audio = await deps.telegram.download_file(file_meta["file_path"])
    transcript = await deps.stt.transcribe(audio)

    async with sessionmaker() as session:
        user_id = await _linked_user_id(session, chat_id)
        if user_id is None:
            logger.warning("voice note from unlinked chat %s dropped", chat_id)
            return
        user = await session.get(User, user_id)
        existing = (
            await session.scalars(
                select(TelegramMessage).where(
                    TelegramMessage.chat_id == chat_id,
                    TelegramMessage.message_id == message_id,
                    TelegramMessage.status == "pending",
                )
            )
        ).first()
        activity_ctx = await _activity_context(session, user_id, message_ts)

    if existing is not None:
        # Telegram redelivery (offset rewind) — one draft per voice message.
        logger.info("chat %s: draft for message %s already pending — skipped", chat_id, message_id)
        return

    extraction, response = await _extract(deps.llm, transcript, activity_ctx, corrections=None)
    await _log_extraction_usage(sessionmaker, user_id, response)

    async with sessionmaker() as session:
        draft = TelegramMessage(
            chat_id=chat_id,
            message_id=message_id,
            voice_file_id=voice_file_id,
            raw_transcript=transcript,
            extracted_json={
                "message_ts": message_ts,
                "extraction": extraction,
                "activity_context": activity_ctx,
            },
        )
        session.add(draft)
        await session.commit()
        row_id = draft.id

    tz = ZoneInfo(user.timezone)
    await deps.telegram.send_message(
        chat_id,
        render_draft(tz, extraction, message_ts, activity_ctx),
        reply_markup=draft_keyboard(row_id),
    )


async def confirm_draft(
    sessionmaker: async_sessionmaker, chat_id: int, row_id: int
) -> tuple[str, str | None]:
    """✅ Save: write journal_entries, mark confirmed. Idempotent — a second
    confirm answers 'already saved' and changes nothing.

    Returns (callback_answer, follow_up_message | None)."""
    async with sessionmaker() as session:
        row = await session.get(TelegramMessage, row_id)
        if row is None or row.chat_id != chat_id:
            return "Draft not found.", None
        if row.status == "confirmed":
            return "Already saved.", None
        if row.status == "rejected":
            return "That draft was replaced — confirm the latest one.", None
        user_id = await _linked_user_id(session, chat_id)
        assert user_id is not None  # guard guarantees a linked chat
        user = await session.get(User, user_id)
        payload = row.extracted_json or {}
        extraction = payload.get("extraction", {})
        tz = ZoneInfo(user.timezone)
        message_ts = payload.get("message_ts") or int(row.created_at.timestamp())
        local_date = datetime.fromtimestamp(message_ts, tz).date()
        entry = JournalEntry(
            user_id=user_id,
            date=local_date,
            mood_score=extraction.get("mood_score"),
            energy_score=extraction.get("energy_score"),
            motivation_score=extraction.get("motivation_score"),
            soreness_score=extraction.get("soreness_score"),
            stress_subjective=extraction.get("stress_subjective"),
            sleep_quality_subjective=extraction.get("sleep_quality_subjective"),
            free_text_notes=extraction.get("summary"),
            tags=extraction.get("tags") or [],
            source="telegram_voice",
            raw_transcript=row.raw_transcript,
        )
        session.add(entry)
        await session.flush()
        row.status = "confirmed"
        row.linked_journal_entry_id = entry.id
        await session.commit()
        journal_id = entry.id
    logger.info("chat %s: draft %s confirmed as journal entry %s", chat_id, row_id, journal_id)
    return f"Saved as journal entry #{journal_id}.", f"Journal entry #{journal_id} saved."


async def request_edit(redis, chat_id: int, row_id: int) -> str:
    """✏️ Edit: remember which draft awaits corrections (Redis TTL window)."""
    await redis.set(EDIT_KEY.format(chat_id=chat_id), row_id, ex=EDIT_TTL_S)
    return "Send your corrections as a text message — they'll replace this draft."


async def apply_edit_corrections(
    sessionmaker: async_sessionmaker,
    redis,
    telegram: object,
    llm_factory,  # Callable[[], LLMClient] — built only when an edit is open
    chat_id: int,
    corrections: str,
) -> bool:
    """Text message while an edit is open: re-extract with corrections,
    reject the old draft, send a fresh one. False = no edit was open (the
    caller falls through to the agent path)."""
    key = EDIT_KEY.format(chat_id=chat_id)
    raw = await redis.get(key)
    if raw is None:
        return False
    row_id = int(raw)
    await redis.delete(key)

    async with sessionmaker() as session:
        row = await session.get(TelegramMessage, row_id)
        if row is None or row.chat_id != chat_id or row.status != "pending":
            await telegram.send_message(chat_id, "That draft is gone — send a new voice note.")
            return True
        payload = row.extracted_json or {}
        activity_ctx = payload.get("activity_context")
        message_ts = payload.get("message_ts")
        transcript = row.raw_transcript or ""

    extraction, response = await _extract(llm_factory(), transcript, activity_ctx, corrections=corrections)

    async with sessionmaker() as session:
        user_id = await _linked_user_id(session, chat_id)
        if user_id is not None:
            await _log_extraction_usage(sessionmaker, user_id, response)
        row = await session.get(TelegramMessage, row_id)
        row.status = "rejected"
        replacement = TelegramMessage(
            chat_id=chat_id,
            message_id=row.message_id,
            voice_file_id=row.voice_file_id,
            raw_transcript=transcript,
            extracted_json={
                "message_ts": message_ts,
                "extraction": extraction,
                "activity_context": activity_ctx,
            },
        )
        session.add(replacement)
        await session.commit()
        new_row_id = replacement.id

    async with sessionmaker() as session:
        user_id = await _linked_user_id(session, chat_id)
        user = await session.get(User, user_id)
    tz = ZoneInfo(user.timezone)
    await telegram.send_message(
        chat_id,
        render_draft(tz, extraction, message_ts, activity_ctx),
        reply_markup=draft_keyboard(new_row_id),
    )
    logger.info("chat %s: draft %s replaced by %s after corrections", chat_id, row_id, new_row_id)
    return True


async def _linked_user_id(session, chat_id: int) -> int | None:
    from app.connectors.telegram.link_flow import get_linked_user_id

    return await get_linked_user_id(session, chat_id)
