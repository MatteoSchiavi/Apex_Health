"""COROS Open API client shell (see package docstring: awaiting owner's
developer-portal approval). Endpoints follow the published Open API doc;
they are intentionally thin because live verification is impossible before
approval — shapes land in raw_ingest and any mismatch fails per-row, not
per-sync."""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.connectors.oauth2 import OAuth2Error, OAuthTokens, exchange_code, refresh
from app.core.config import get_settings

logger = logging.getLogger("connectors.coros.client")

SOURCE = "coros"


class CorosAuthError(Exception):
    """Raised when COROS tokens are missing/unusable."""


def build_authorize_url(state: str) -> str:
    from app.connectors.oauth2 import build_authorize_url as shared

    return shared("coros", state)


async def exchange(code: str) -> OAuthTokens:
    return await exchange_code("coros", code)


class CorosClient:
    """Bearer-token reader with the same surface as the other connectors."""

    def __init__(self, tokens: OAuthTokens) -> None:
        self._tokens = tokens
        self._base = get_settings().coros_api_base.rstrip("/")

    async def _ensure_token(self) -> str:
        if not self._tokens.access_token:
            raise CorosAuthError("COROS access token missing")
        if self._tokens.refresh_token:
            try:
                self._tokens = await refresh("coros", self._tokens.refresh_token)
            except OAuth2Error as exc:
                raise CorosAuthError(f"COROS token refresh failed: {exc}") from exc
        return self._tokens.access_token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._ensure_token()
        url = f"{self._base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers={"ACCESS-TOKEN": token})
            resp.raise_for_status()
            return resp.json()

    async def fetch_sports_list(self, page: int = 1, size: int = 50) -> dict[str, Any]:
        """Paged activity summaries (Open API /sports/sportsList)."""
        return await self._get("sports/sportsList", {"page": page, "size": size})

    async def fetch_sports_detail(self, sport_id: str) -> dict[str, Any]:
        return await self._get("sports/sportDetail", {"sportId": sport_id})
