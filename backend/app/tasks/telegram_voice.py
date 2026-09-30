"""Voice-note Celery task (§10.2: handler acknowledges, hands off to Celery
so the polling loop keeps draining updates while transcription runs)."""

import asyncio
import logging

from app.connectors.telegram.client import LiveTelegramClient
from app.connectors.telegram.voice import VoiceDeps, run_voice_pipeline
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.llm import build_llm_client
from app.core.stt import build_stt_client
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.telegram_voice")


@celery_app.task(name="telegram.process_voice")
def process_voice_task(chat_id: int, message_id: int, voice_file_id: str, message_ts: int) -> None:
    asyncio.run(_run(chat_id, message_id, voice_file_id, message_ts))


async def _run(chat_id: int, message_id: int, voice_file_id: str, message_ts: int) -> None:
    settings = get_settings()
    deps = VoiceDeps(
        telegram=LiveTelegramClient(settings.telegram_bot_token),
        llm=build_llm_client(),
        stt=build_stt_client(),
    )
    try:
        await run_voice_pipeline(
            deps, sessionmaker, chat_id, message_id, voice_file_id, message_ts
        )
    except Exception:
        # §21: a failed draft never kills the worker; the user gets no draft
        # and can simply resend. Error surfaces in structured logs.
        logger.exception("voice pipeline failed for chat %s message %s", chat_id, message_id)
        raise
