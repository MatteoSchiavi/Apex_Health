"""Whoop client (official Developer API v2).

OAuth2 authorization-code flow per the published OpenAPI spec:
  authorize  https://api.prod.whoop.com/oauth/oauth2/auth
  token      https://api.prod.whoop.com/oauth/oauth2/token
  base       https://api.prod.whoop.com/developer/v2
Collections paginate with a `nextToken` request param (response field
`next_token`), 25 records max per page.

Token lifecycle mirrors the Technogym client: the caller persists
`OAuthTokens.as_credentials()` encrypted; `ensure_fresh()` refreshes a
near-expiry access token single-flight and hands the new tokens back via
`tokens_out` so the sync driver can persist the rotation.

Every endpoint URL is a Settings tunable (§24) and tests run against
injected transports / fixture clients — no test can reach the live API.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.connectors.oauth2 import OAuth2Error, OAuthTokens
from app.core.config import get_settings

logger = logging.getLogger("connectors.whoop.client")

# Refresh when the access token expires within this margin.
_EXPIRY_MARGIN_S = 60


class WhoopAuthError(Exception):
    """Raised when OAuth cannot complete or credentials are unusable."""


class WhoopOAuth:
    """Token exchange/refresh against the configured token endpoint."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def exchange_code(self, code: str) -> OAuthTokens:
        try:
            return await self._call(
                "authorization_code",
                {"code": code, "redirect_uri": get_settings().whoop_redirect_uri},
            )
        except OAuth2Error as exc:
            raise WhoopAuthError(str(exc)) from exc

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        try:
            return await self._call("refresh_token", {"refresh_token": refresh_token})
        except OAuth2Error as exc:
            raise WhoopAuthError(str(exc)) from exc

    async def _call(self, grant_type: str, extra: dict[str, str]) -> OAuthTokens:
        settings = get_settings()
        from app.connectors.oauth2 import _token_request  # local import, test seams

        body = {
            "grant_type": grant_type,
            "client_id": settings.whoop_client_id,
            "client_secret": settings.whoop_client_secret,
            **extra,
        }
        return await _token_request(
            settings.whoop_oauth_token_url, body, transport=self._transport
        )


def build_authorize_url(state: str, *, scope: str | None = None) -> str:
    """Authorization URL the user opens in a browser (manual step)."""
    settings = get_settings()
    if not settings.whoop_client_id or not settings.whoop_client_secret:
        raise WhoopAuthError(
            "WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET are not configured — "
            "register the app at developer.whoop.com first"
        )
    from app.connectors.oauth2 import build_authorize_url as _shared

    return _shared("whoop", state)


class _Http(Protocol):
    async def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...


class LiveWhoopClient:
    """Paginated v2 collections + token refresh single-flight.

    Tests inject an `httpx.AsyncClient` backed by `httpx.MockTransport`
    (token/flow tests) or replace the client entirely with a fixture double
    (sync tests) — the sync pipeline depends only on the collection methods.
    """

    def __init__(
        self,
        tokens: OAuthTokens,
        *,
        http: _Http | None = None,
        oauth: WhoopOAuth | None = None,
        page_delay_s: float | None = None,
    ):
        self.tokens = tokens
        self._http = http
        self._oauth = oauth or WhoopOAuth()
        self._refresh_lock = asyncio.Lock()
        # Strictly-newer tokens when a refresh happened mid-run (rotation law).
        self.tokens_out: OAuthTokens | None = None
        self.page_delay_s = (
            page_delay_s
            if page_delay_s is not None
            else get_settings().whoop_page_delay_seconds
        )

    @classmethod
    def from_credentials(
        cls, credentials: dict[str, Any], **kwargs: Any
    ) -> "LiveWhoopClient":
        try:
            tokens = OAuthTokens.from_credentials(credentials)
        except OAuth2Error as exc:
            raise WhoopAuthError(str(exc)) from exc
        return cls(tokens, **kwargs)

    # ---------------------------------------------------------- lifecycle

    async def _ensure_http(self) -> _Http:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=get_settings().whoop_api_base,
                headers={"Authorization": f"Bearer {self.tokens.access_token}"},
                timeout=30.0,
            )
        return self._http

    async def ensure_fresh(self) -> None:
        """Refresh single-flight when the access token is near/past expiry."""
        expires_at = self.tokens.expires_at
        if expires_at is not None and expires_at > datetime.now(UTC) + timedelta(
            seconds=_EXPIRY_MARGIN_S
        ):
            return
        if not self.tokens.refresh_token:
            raise WhoopAuthError(
                "access token expired and no refresh token stored — reconnect Whoop"
            )
        async with self._refresh_lock:
            # Double-check under the lock: another coroutine may have won.
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
                except AttributeError:  # fixture double without headers
                    pass
            logger.info("whoop: access token refreshed")

    # -------------------------------------------------------- collections

    async def _get_paginated(
        self, path: str, extra: dict[str, Any] | None = None, *, page_limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Walk a v2 collection (nextToken) to exhaustion, paced per §19.

        F-10 audit: HTTP status is now checked BEFORE ``.json()`` — a 429/500
        error page no longer surfaces as ``WhoopAuthError("malformed")``
        (wrong exception class masking data bugs as auth failures). 429
        honors ``Retry-After`` with a bounded retry; 401 triggers the
        standard token-refresh path; everything else raises a generic
        ``ConnectorTransientError`` that Celery's autoretry handles.
        """
        settings = get_settings()
        limit = page_limit if page_limit is not None else settings.whoop_page_size
        records: list[dict[str, Any]] = []
        next_token: str | None = None
        http = await self._ensure_http()
        max_retries = 3
        retry_attempt = 0
        while True:
            await self.ensure_fresh()
            params: dict[str, Any] = {"limit": limit}
            if extra:
                params.update(extra)
            if next_token:
                params["nextToken"] = next_token
            resp = await http.get(path, params=params)
            # F-10: check HTTP status BEFORE parsing the body.
            status = getattr(resp, "status_code", None)
            if status is not None and status != 200:
                # 401 → token refresh path (the next loop iteration's
                # ensure_fresh will rotate the token; if that already
                # happened, the credentials are bad and we surface auth).
                if status == 401:
                    await self.ensure_fresh()
                    continue
                # 429 → honor Retry-After with a bounded retry.
                if status == 429 and retry_attempt < max_retries:
                    retry_after = resp.headers.get("retry-after") if hasattr(resp, "headers") else None
                    delay = float(retry_after) if retry_after else 2.0 ** retry_attempt
                    await asyncio.sleep(min(delay, 60.0))
                    retry_attempt += 1
                    continue
                # Everything else (5xx, 4xx-config) → raise; Celery autoretry
                # handles transient errors, sync-failure-escalation logs the
                # rest.
                raise WhoopAuthError(
                    f"whoop collection {path} returned HTTP {status}"
                )
            payload = resp.json() if hasattr(resp, "json") else resp
            if not isinstance(payload, dict) or "records" not in payload:
                raise WhoopAuthError(f"whoop collection {path} malformed (no records key)")
            records.extend(payload.get("records") or [])
            next_token = payload.get("next_token")
            retry_attempt = 0  # reset on success
            if not next_token:
                break
            if self.page_delay_s:
                await asyncio.sleep(self.page_delay_s)
        return records

    async def fetch_sleeps(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("/v2/activity/sleep", _time_params(start, end))

    async def fetch_recoveries(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("/v2/recovery", _time_params(start, end))

    async def fetch_cycles(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("/v2/cycle", _time_params(start, end))

    async def fetch_workouts(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("/v2/activity/workout", _time_params(start, end))

    async def fetch_body_measurement(self) -> dict[str, Any] | None:
        http = await self._ensure_http()
        await self.ensure_fresh()
        resp = await http.get("/v2/user/measurement/body")
        payload = resp.json() if hasattr(resp, "json") else resp
        return payload if isinstance(payload, dict) else None

    async def fetch_profile(self) -> dict[str, Any] | None:
        http = await self._ensure_http()
        await self.ensure_fresh()
        resp = await http.get("/v2/user/profile/basic")
        payload = resp.json() if hasattr(resp, "json") else resp
        return payload if isinstance(payload, dict) else None


def _time_params(start: datetime | None, end: datetime | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if start is not None:
        params["start"] = start.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if end is not None:
        params["end"] = end.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return params


def build_live_client(
    credentials: dict[str, Any] | None, **kwargs: Any
) -> LiveWhoopClient:
    """Build a client from stored (decrypted) credentials. Whoop has no
    password fallback — an account connects via OAuth or not at all."""
    if not credentials:
        raise WhoopAuthError(
            "no stored Whoop credentials — connect the account first "
            "(POST /settings/integrations/whoop/authorize)"
        )
    return LiveWhoopClient.from_credentials(credentials, **kwargs)
