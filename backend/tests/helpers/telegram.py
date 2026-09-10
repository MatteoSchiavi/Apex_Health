"""Fixture-backed Telegram Bot API client + bot test context (§0/§20).

These are the ONLY Telegram clients automated tests use. The fixture client
serves recorded updates and records every outgoing call so tests assert on
exactly what the bot would have sent over the wire.
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "telegram"
UPDATES_PATH = FIXTURES_DIR / "updates.json"


def load_update(name: str) -> dict[str, Any]:
    """One recorded Bot API update payload, keyed by name in updates.json."""
    updates = json.loads(UPDATES_PATH.read_text())
    if name not in updates:
        raise KeyError(f"recorded update {name!r} not in {UPDATES_PATH}")
    return updates[name]


def with_text(update: dict[str, Any], text: str) -> dict[str, Any]:
    """Same recorded update shape, with the message text replaced — for
    flows whose payload is dynamic (e.g. a freshly issued link code)."""
    assert "message" in update
    return {**update, "message": {**update["message"], "text": text}}


class FixtureTelegramClient:
    """Serves recorded updates; records every outgoing Bot API call."""

    def __init__(
        self,
        updates: list[dict[str, Any]] | None = None,
        file_bytes: bytes = b"OGGDUMMYBYTES",
        file_map: dict[str, str] | None = None,
    ) -> None:
        self._updates = updates or []
        self._file_bytes = file_bytes
        self._file_map = file_map or {}
        # outgoing call records
        self.sent_messages: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []
        self.file_requests: list[str] = []
        self.downloads: list[str] = []

    async def get_updates(self, offset: int, timeout_s: int) -> list[dict[str, Any]]:
        return [u for u in self._updates if u["update_id"] >= offset]

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        record = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        self.sent_messages.append(record)
        return {"message_id": 9000 + len(self.sent_messages), **record}

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        self.callback_answers.append({"callback_query_id": callback_query_id, "text": text})

    async def get_file(self, file_id: str) -> dict[str, Any]:
        self.file_requests.append(file_id)
        return {
            "file_id": file_id,
            "file_path": self._file_map.get(file_id, f"voice/{file_id}.ogg"),
        }

    async def download_file(self, file_path: str) -> bytes:
        self.downloads.append(file_path)
        return self._file_bytes


def sent_texts(client: FixtureTelegramClient) -> list[str]:
    """Outgoing message texts in order — the common assertion target."""
    return [m["text"] for m in client.sent_messages]


def sent_keyboards(client: FixtureTelegramClient) -> list[dict[str, Any] | None]:
    return [m["reply_markup"] for m in client.sent_messages]


@pytest_asyncio.fixture(autouse=True)
async def clean_bot_tables(db_session):
    """Bot-domain tables are shared across tests in one schema build —
    truncate between tests (same convention as the sync-suite fixture)."""
    await db_session.execute(
        text(
            "TRUNCATE telegram_links, telegram_messages, journal_entries, "
            "ai_chat_sessions, ai_chat_messages RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


@asynccontextmanager
async def bot_context(telegram: FixtureTelegramClient, dispatch_voice=None):
    """A BotContext wired to the app sessionmaker + a fresh Redis client.

    dispatch_voice defaults to an inline no-op recorder; voice tests pass a
    dispatcher that runs the real pipeline against fixture clients.
    """
    from app.connectors.telegram.context import BotContext
    from app.core.db import sessionmaker

    async def _noop_dispatch(**kwargs: Any) -> None:
        return None

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        yield BotContext(
            telegram=telegram,
            sessionmaker=sessionmaker,
            redis=redis,
            dispatch_voice=dispatch_voice or _noop_dispatch,
        )
    finally:
        await redis.aclose()
