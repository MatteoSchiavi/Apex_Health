"""Oura API v2 HTTP client: token refresh + paged collection fetches.

Endpoints (https://cloud.ouraring.com/v2/docs): usercollection/daily_sleep,
/sleep, /heartrate, /personal_info, /daily_stress (not used yet). Pages
return {"data": [...], "next_token": "..."} — cursor pagination like Whoop.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.connectors.oauth2 import OAuth2Error, OAuthTokens, exchange_code, refresh
from app.core.config import get_settings

logger = logging.getLogger("connectors.oura.client")

SOURCE = "oura"


class OuraAuthError(Exception):
    """Raised when Oura tokens are missing/expired and refresh fails."""


def build_authorize_url(state: str) -> str:
    from app.connectors.oauth2 import build_authorize_url as shared

    return shared("oura", state)


async def exchange(code: str) -> OAuthTokens:
    return await exchange_code("oura", code)


class OuraClient:
    """Bearer-token collection reader. The sync driver owns pacing."""

    def __init__(self, tokens: OAuthTokens) -> None:
        self._tokens = tokens
        settings = get_settings()
        self._base = settings.oura_api_base.rstrip("/")
        self._page_size = settings.oura_page_size
        self.page_delay_s = settings.oura_page_delay_seconds

    @property
    def tokens_out(self) -> OAuthTokens | None:
        """Strictly-newer tokens when the client refreshed mid-run (the sync
        task persists them — same rotation law as Whoop)."""
        return self._tokens

    async def _ensure_token(self) -> str:
        """Refresh when the stored access token is past its lifetime."""
        t = self._tokens
        if t.expires_at and t.expires_at <= datetime.now(UTC) + timedelta(minutes=5):
            if not t.refresh_token:
                raise OuraAuthError("Oura access token expired and no refresh token stored")
            try:
                self._tokens = await refresh("oura", t.refresh_token)
            except OAuth2Error as exc:
                raise OuraAuthError(f"Oura token refresh failed: {exc}") from exc
        return self._tokens.access_token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._ensure_token()
        url = f"{self._base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()

    async def _paged(self, path: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Cursor-paginated window pull; start/end are ISO datetimes."""
        out: list[dict[str, Any]] = []
        params: dict[str, Any] = {
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "page_size": self._page_size,
        }
        while True:
            payload = await self._get(path, params)
            rows = payload.get("data") or []
            out.extend(r for r in rows if isinstance(r, dict))
            next_token = payload.get("next_token")
            if not next_token:
                return out
            params["next_token"] = next_token

    async def fetch_daily_sleep(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self._paged("daily_sleep", start, end)

    async def fetch_sleep_periods(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self._paged("sleep", start, end)

    async def fetch_heartrate(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return await self._paged("heartrate", start, end)

    async def fetch_personal_info(self) -> dict[str, Any]:
        return await self._get("personal_info")
