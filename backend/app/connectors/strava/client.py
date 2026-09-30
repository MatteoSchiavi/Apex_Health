"""Strava client (official REST API v3, OAuth2 authorization-code).

  authorize  https://www.strava.com/oauth/authorize
  token      https://www.strava.com/oauth/token
  base       https://www.strava.com/api/v3
Token responses carry BOTH `expires_at` (epoch) and `expires_in` (seconds);
the shared OAuthTokens reader uses `expires_in`. Access tokens last 6h.

Strava rate limits (200 req/15min read, 2000/day read on the standard tier;
historically 100/15min + 1000/day) are honored by the sync driver's page
pacing — this client itself just fetches pages.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.connectors.oauth2 import OAuth2Error, OAuthTokens
from app.core.config import get_settings

logger = logging.getLogger("connectors.strava.client")

_EXPIRY_MARGIN_S = 60


class StravaAuthError(Exception):
    """Raised when OAuth cannot complete or credentials are unusable."""


class StravaOAuth:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def exchange_code(self, code: str) -> OAuthTokens:
        try:
            return await self._call(
                "authorization_code",
                {"code": code, "redirect_uri": get_settings().strava_redirect_uri},
            )
        except OAuth2Error as exc:
            raise StravaAuthError(str(exc)) from exc

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        try:
            return await self._call("refresh_token", {"refresh_token": refresh_token})
        except OAuth2Error as exc:
            raise StravaAuthError(str(exc)) from exc

    async def _call(self, grant_type: str, extra: dict[str, str]) -> OAuthTokens:
        settings = get_settings()
        from app.connectors.oauth2 import _token_request

        body = {
            "grant_type": grant_type,
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            **extra,
        }
        return await _token_request(
            settings.strava_oauth_token_url, body, transport=self._transport
        )


def build_authorize_url(state: str, *, scope: str | None = None) -> str:
    settings = get_settings()
    if not settings.strava_client_id or not settings.strava_client_secret:
        raise StravaAuthError(
            "STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET are not configured — "
            "register the app at strava.com/settings/api first"
        )
    from app.connectors.oauth2 import build_authorize_url as _shared

    return _shared("strava", state)


class _Http(Protocol):
    async def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...


class LiveStravaClient:
    """Activities list + token refresh single-flight."""

    def __init__(
        self,
        tokens: OAuthTokens,
        *,
        http: _Http | None = None,
        oauth: StravaOAuth | None = None,
        page_delay_s: float | None = None,
    ):
        self.tokens = tokens
        self._http = http
        self._oauth = oauth or StravaOAuth()
        self._refresh_lock = asyncio.Lock()
        self.tokens_out: OAuthTokens | None = None
        self.page_delay_s = (
            page_delay_s
            if page_delay_s is not None
            else get_settings().strava_page_delay_seconds
        )

    @classmethod
    def from_credentials(
        cls, credentials: dict[str, Any], **kwargs: Any
    ) -> "LiveStravaClient":
        try:
            tokens = OAuthTokens.from_credentials(credentials)
        except OAuth2Error as exc:
            raise StravaAuthError(str(exc)) from exc
        return cls(tokens, **kwargs)

    async def _ensure_http(self) -> _Http:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=get_settings().strava_api_base,
                headers={"Authorization": f"Bearer {self.tokens.access_token}"},
                timeout=30.0,
            )
        return self._http

    async def ensure_fresh(self) -> None:
        expires_at = self.tokens.expires_at
        if expires_at is not None and expires_at > datetime.now(UTC) + timedelta(
            seconds=_EXPIRY_MARGIN_S
        ):
            return
        if not self.tokens.refresh_token:
            raise StravaAuthError(
                "access token expired and no refresh token stored — reconnect Strava"
            )
        async with self._refresh_lock:
            expires_at = self.tokens.expires_at
            if expires_at is not None and expires_at > datetime.now(UTC) + timedelta(
                seconds=_EXPIRY_MARGIN_S
            ):
                return
            fresh = await self._oauth.refresh(self.tokens.refresh_token)
            self.tokens = fresh
            self.tokens_out = fresh
            if self._http is not None:
                try:
                    self._http.headers["Authorization"] = f"Bearer {fresh.access_token}"
                except AttributeError:
                    pass
            logger.info("strava: access token refreshed")

    async def fetch_activities(
        self,
        *,
        after_epoch: int | None = None,
        before_epoch: int | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        """All summary activities, page by page (Strava caps at 100/page)."""
        settings = get_settings()
        per_page = page_size or settings.strava_activity_page_size
        page = 1
        activities: list[dict[str, Any]] = []
        http = await self._ensure_http()
        while True:
            await self.ensure_fresh()
            params: dict[str, Any] = {"per_page": per_page, "page": page}
            if after_epoch is not None:
                params["after"] = after_epoch
            if before_epoch is not None:
                params["before"] = before_epoch
            resp = await http.get("/athlete/activities", params=params)
            payload = resp.json() if hasattr(resp, "json") else resp
            if not isinstance(payload, list):
                raise StravaAuthError(f"strava activities malformed: {payload!r:.200}")
            if not payload:
                break
            activities.extend(a for a in payload if isinstance(a, dict))
            if len(payload) < per_page:
                break
            page += 1
            if self.page_delay_s:
                await asyncio.sleep(self.page_delay_s)
        return activities


def build_live_client(
    credentials: dict[str, Any] | None, **kwargs: Any
) -> LiveStravaClient:
    if not credentials:
        raise StravaAuthError(
            "no stored Strava credentials — connect the account first "
            "(POST /settings/integrations/strava/authorize)"
        )
    return LiveStravaClient.from_credentials(credentials, **kwargs)
