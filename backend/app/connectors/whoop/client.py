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


class WhoopAPIError(Exception):
    """An unavailable or malformed upstream API response, distinct from auth."""


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
        try:
            return await _token_request(
                settings.whoop_oauth_token_url, body, transport=self._transport
            )
        except OAuth2Error as exc:
            # OAuth errors may include token endpoint bodies: never expose those.
            raise WhoopAuthError("WHOOP token exchange failed; verify app settings or reconnect") from None


def build_authorize_url(state: str, *, scope: str | None = None) -> str:
    """Authorization URL the user opens in a browser (manual step)."""
    settings = get_settings()
    if not settings.whoop_client_id or not settings.whoop_client_secret:
        raise WhoopAuthError(
            "WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET are not configured — "
            "register the app at developer.whoop.com first"
        )
    from urllib.parse import urlencode

    return settings.whoop_oauth_authorize_url + "?" + urlencode({
        "response_type": "code", "client_id": settings.whoop_client_id,
        "redirect_uri": settings.whoop_redirect_uri, "state": state,
        "scope": scope if scope is not None else settings.whoop_scope,
    })


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
                base_url=get_settings().whoop_api_base.rstrip("/") + "/",
                headers={"Authorization": f"Bearer {self.tokens.access_token}"},
                timeout=30.0,
            )
        return self._http

    async def ensure_fresh(self, *, force: bool = False) -> None:
        """Refresh single-flight when the access token is near/past expiry."""
        observed_access_token = self.tokens.access_token
        expires_at = self.tokens.expires_at
        if not force and expires_at is not None and expires_at > datetime.now(UTC) + timedelta(
            seconds=_EXPIRY_MARGIN_S
        ):
            return
        if not self.tokens.refresh_token:
            raise WhoopAuthError(
                "access token expired and no refresh token stored — reconnect Whoop"
            )
        async with self._refresh_lock:
            # Double-check under the lock: another coroutine may have won.
            if force and self.tokens.access_token != observed_access_token:
                return
            expires_at = self.tokens.expires_at
            if not force and expires_at is not None and expires_at > datetime.now(UTC) + timedelta(
                seconds=_EXPIRY_MARGIN_S
            ):
                return
            fresh = await self._oauth.refresh(self.tokens.refresh_token)
            # Some providers omit an unchanged refresh token on rotation.
            fresh.refresh_token = fresh.refresh_token or self.tokens.refresh_token
            self.tokens = fresh
            self.tokens_out = fresh
            if self._http is not None:
                try:
                    self._http.headers["Authorization"] = f"Bearer {fresh.access_token}"
                except AttributeError:  # fixture double without headers
                    pass
            logger.info("whoop: access token refreshed")

    async def aclose(self) -> None:
        if self._http is not None and hasattr(self._http, "aclose"):
            await self._http.aclose()

    # -------------------------------------------------------- collections

    async def _get_paginated(
        self, path: str, extra: dict[str, Any] | None = None, *, page_limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Walk a v2 collection with bounded page and HTTP retry handling."""
        settings = get_settings()
        limit = page_limit if page_limit is not None else settings.whoop_page_size
        limit = min(max(int(limit), 1), 25)
        records: list[dict[str, Any]] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit, **(extra or {})}
            if next_token:
                params["nextToken"] = next_token
            payload = await self._get_json(path, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise WhoopAPIError(f"whoop collection {path} malformed (records must be a list)")
            if any(not isinstance(record, dict) for record in payload["records"]):
                raise WhoopAPIError(f"whoop collection {path} contains invalid records")
            records.extend(payload["records"])
            next_token = payload.get("next_token")
            if not next_token:
                break
            if not isinstance(next_token, str) or next_token in seen_tokens:
                raise WhoopAPIError(f"whoop collection {path} repeated or invalid page token")
            seen_tokens.add(next_token)
            if self.page_delay_s:
                await asyncio.sleep(self.page_delay_s)
        return records

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Bounded retries shared by collections and single-object endpoints."""
        http = await self._ensure_http()
        auth_retried = False
        transient_retries = 0
        while True:
            await self.ensure_fresh()
            try:
                resp = await http.get(path, params=params)
            except httpx.HTTPError as exc:
                raise WhoopAPIError("WHOOP API request failed") from exc
            status = getattr(resp, "status_code", 200)
            if status == 401:
                if auth_retried:
                    raise WhoopAuthError("WHOOP rejected credentials after refresh; reconnect WHOOP")
                await self.ensure_fresh(force=True)
                auth_retried = True
                continue
            if status == 403:
                raise WhoopAuthError("WHOOP access denied; reconnect with the required scopes")
            if status == 429 or status >= 500:
                if transient_retries >= 3:
                    raise WhoopAPIError(f"WHOOP API returned HTTP {status}")
                delay = 2.0 ** transient_retries
                retry_after = getattr(resp, "headers", {}).get("retry-after")
                if retry_after:
                    try:
                        delay = max(0.0, float(retry_after))
                    except (ValueError, TypeError):
                        pass
                await asyncio.sleep(min(delay, 60.0))
                transient_retries += 1
                continue
            if status != 200:
                raise WhoopAPIError(f"WHOOP API returned HTTP {status}")
            try:
                return resp.json() if hasattr(resp, "json") else resp
            except ValueError as exc:
                raise WhoopAPIError("WHOOP API returned invalid JSON") from exc

    async def fetch_sleeps(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("activity/sleep", _time_params(start, end))

    async def fetch_recoveries(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("recovery", _time_params(start, end))

    async def fetch_cycles(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("cycle", _time_params(start, end))

    async def fetch_workouts(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        return await self._get_paginated("activity/workout", _time_params(start, end))

    async def fetch_body_measurement(self) -> dict[str, Any] | None:
        payload = await self._get_json("user/measurement/body")
        if not isinstance(payload, dict):
            raise WhoopAPIError("WHOOP body measurement response must be an object")
        return payload

    async def fetch_profile(self) -> dict[str, Any] | None:
        payload = await self._get_json("user/profile/basic")
        if not isinstance(payload, dict):
            raise WhoopAPIError("WHOOP profile response must be an object")
        return payload

    async def fetch_cycle(self, cycle_id: str | int) -> dict[str, Any]:
        # Cycle IDs remain numeric in v2; sleep and workout IDs are UUIDs.
        if not str(cycle_id).isdigit():
            raise WhoopAPIError("WHOOP recovery has an invalid cycle_id")
        payload = await self._get_json(f"cycle/{cycle_id}")
        if not isinstance(payload, dict):
            raise WhoopAPIError("WHOOP cycle response must be an object")
        return payload


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
