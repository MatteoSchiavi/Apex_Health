"""Bot process entrypoint (§10.1): Telegram long polling.

Outbound-only — the bot asks Telegram for updates, no webhook, no public
port. Run as its own process (compose `bot` service):
    python -m app.connectors.telegram.polling

Requires TELEGRAM_BOT_TOKEN (§5). Voice notes are handed off to Celery
(.delay is a blocking Redis op, so it runs off the event loop).
"""

import asyncio
import logging

from app.connectors.telegram.client import (
    LONG_POLL_TIMEOUT_S,
    LiveTelegramClient,
    TelegramError,
)
from app.connectors.telegram.context import BotContext
from app.connectors.telegram.handlers import handle_update
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.embeddings import EmbeddingError, build_embedding_client
from app.core.llm import build_llm_client
from app.core.redis import get_redis
from app.tasks.telegram_voice import process_voice_task

logger = logging.getLogger("connectors.telegram.polling")


def _embeddings_factory():
    """Embedding client when OPENAI_API_KEY is configured (§6.2 pinned
    model), else None — search_context degrades to a readable result."""
    if not get_settings().openai_api_key:
        return None
    try:
        return build_embedding_client()
    except EmbeddingError:
        return None


async def _celery_voice_dispatch(**kwargs) -> None:
    await asyncio.to_thread(process_voice_task.delay, **kwargs)


async def run_polling(ctx: BotContext) -> None:
    """Poll forever: offset tracking + exponential backoff on Telegram
    errors; one bad update never stops the loop."""
    offset = 0
    backoff_s = 5.0
    while True:
        try:
            updates = await ctx.telegram.get_updates(offset, LONG_POLL_TIMEOUT_S)
            backoff_s = 5.0
        except TelegramError as exc:
            logger.warning("getUpdates failed: %s — retrying in %.0fs", exc, backoff_s)
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 60.0)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                await handle_update(ctx, update)
            except Exception:
                logger.exception(
                    "update %s crashed its handler — loop continues", update.get("update_id")
                )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    ctx = BotContext(
        telegram=LiveTelegramClient(settings.telegram_bot_token),
        sessionmaker=sessionmaker,
        redis=get_redis(),
        dispatch_voice=_celery_voice_dispatch,
        llm_factory=build_llm_client,
        embeddings_factory=_embeddings_factory,
    )
    logger.info("bot polling started (long poll %ss)", LONG_POLL_TIMEOUT_S)
    try:
        asyncio.run(run_polling(ctx))
    except KeyboardInterrupt:
        logger.info("bot stopped")


if __name__ == "__main__":
    main()
