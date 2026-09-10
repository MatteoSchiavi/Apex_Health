"""Telegram Bot API client abstraction.

§10.1: the bot transport is long polling — outbound-only, no webhook, no
public exposure. §0/§16.7/§20: automated tests NEVER talk to the live
Telegram API — the bot depends only on the `TelegramClient` protocol and
tests inject a fixture-backed implementation. `LiveTelegramClient` speaks
the Bot API over HTTPS and is exercised only by the owner running the bot
process with TELEGRAM_BOT_TOKEN set.
"""

import logging
from typing import Any, Protocol

import httpx

logger = logging.getLogger("connectors.telegram.client")

API_BASE = "https://api.telegram.org"
# §10.1 long polling: the getUpdates call blocks server-side for this long
# before returning an empty result. Keep below the HTTP client timeout.
LONG_POLL_TIMEOUT_S = 25


class TelegramError(Exception):
    """Raised when the Bot API returns a non-ok response or the request fails."""


class TelegramClient(Protocol):
    """The surface the bot needs. All methods are async."""

    async def get_updates(self, offset: int, timeout_s: int) -> list[dict[str, Any]]:
        """Long-poll updates with `offset` (last update_id + 1)."""
        ...

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a text message; optional inline keyboard reply_markup."""
        ...

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        """Acknowledge a callback query (clears the client's loading state)."""
        ...

    async def get_file(self, file_id: str) -> dict[str, Any]:
        """File metadata incl. file_path for download."""
        ...

    async def download_file(self, file_path: str) -> bytes:
        """Download file content by its Bot API file_path."""
        ...


class LiveTelegramClient:
    """Bot API over HTTPS (§10.1). Built only by the bot process entrypoint —
    never by tests."""

    def __init__(self, bot_token: str, client: httpx.AsyncClient | None = None) -> None:
        if not bot_token:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN is not set — the polling loop cannot start"
            )
        self._base = f"{API_BASE}/bot{bot_token}"
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(f"{self._base}/{method}", json=payload)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method} request failed: {exc}") from exc
        if not body.get("ok"):
            raise TelegramError(f"{method} returned error: {body.get('description')}")
        return body["result"]

    async def get_updates(self, offset: int, timeout_s: int) -> list[dict[str, Any]]:
        return await self._post(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout_s,
                # Only what §10 needs; anything else is ignored by handlers.
                "allowed_updates": ["message", "callback_query"],
            },
        )

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", payload)

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        await self._post("answerCallbackQuery", payload)

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self._post("getFile", {"file_id": file_id})

    async def download_file(self, file_path: str) -> bytes:
        try:
            resp = await self._client.get(f"{self._base}/{file_path}")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramError(f"file download failed: {exc}") from exc
        return resp.content
