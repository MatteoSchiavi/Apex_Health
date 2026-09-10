"""Technogym client abstraction (MASTER_SPEC §11 — Stage 11a).

OAuth2 authorization-code flow per the enduser-to-enduser sample on
developer.technogym.com / apidocs.mywellness.com. §24 open item: what a
self-registered individual client may actually call only resolves when the
owner registers and connects manually, so every endpoint URL is a Settings
tunable (fix them from the developer console without a code change) and all
tests run against recorded fixtures — no test can reach the live API
(§0/§16.7/§20).

Token lifecycle: the caller owns persisting `OAuthTokens.as_credentials()`
app-layer-encrypted in `integrations.credentials_encrypted` (§17, same law as
the Garmin session dump). `LiveTechnogymClient.ensure_fresh()` refreshes a
near-expiry access token single-flight and hands the new tokens back via
`tokens_out`, so the sync driver can persist the rotation.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

logger = logging.getLogger("connectors.technogym.client")

# Refresh when the access token expires within this margin.
_EXPIRY_MARGIN_S = 60


class TechnogymAuthError(Exception):
    """Raised when OAuth cannot complete or credentials are unusable."""


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None  # UTC, per the token response's expires_in
    raw: dict[str, Any] = field(default_factory=dict)  # full response, raw-first storage

    @classmethod
    def from_response(cls, payload: dict[str, Any], now: datetime | None = None) -> "OAuthTokens":
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise TechnogymAuthError(f"token response missing access_token: {payload!r}")
        expires_in = payload.get("expires_in")
        expires_at = (
            (now or datetime.now(UTC)) + timedelta(seconds=float(expires_in))
            if expires_in is not None
            else None
        )
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            expires_at=expires_at,
            raw=payload,
        )

    def as_credentials(self) -> dict[str, Any]:
        """JSON-serializable payload for integrations.credentials_encrypted."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "raw": self.raw,
        }

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> "OAuthTokens":
        if not isinstance(credentials, dict) or not credentials.get("access_token"):
            raise TechnogymAuthError(
                "stored Technogym credentials are missing access_token — connect first"
            )
        expires_at = None
        if credentials.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(credentials["expires_at"])
            except ValueError as exc:
                raise TechnogymAuthError(f"stored expires_at unparsable: {exc}") from exc
        return cls(
            access_token=credentials["access_token"],
            refresh_token=credentials.get("refresh_token"),
            expires_at=expires_at,
            raw=credentials.get("raw") or {},
        )


def build_authorize_url(state: str, *, scope: str | None = None) -> str:
    """Authorization URL the owner opens in a browser (manual step, §11).

    `state` is a single-use random value the caller stores server-side (Redis,
    TTL-bound); the callback must echo it before any token exchange.
    """
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.technogym_client_id,
        "redirect_uri": settings.technogym_redirect_uri,
        "state": state,
    }
    chosen_scope = scope if scope is not None else settings.technogym_scope
    if chosen_scope:
        params["scope"] = chosen_scope
    return f"{settings.technogym_oauth_authorize_url}?{urlencode(params)}"


def _token_request_body(*, grant_type: str, **extra: str) -> dict[str, str]:
    settings = get_settings()
    body = {
        "grant_type": grant_type,
        "client_id": settings.technogym_client_id,
        "client_secret": settings.technogym_client_secret,
    }
    body.update(extra)
    return body


class TechnogymOAuth:
    """Token-exchange half of the flow. The httpx client is injectable so
    tests pin a MockTransport; production builds one per call site."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http

    async def _post_token(self, body: dict[str, str]) -> OAuthTokens:
        settings = get_settings()
        if not settings.technogym_client_id or not settings.technogym_client_secret:
            raise TechnogymAuthError(
                "TECHNOGYM_CLIENT_ID/TECHNOGYM_CLIENT_SECRET not configured (§5)"
            )
        http = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            resp = await http.post(settings.technogym_oauth_token_url, data=body)
        finally:
            if self._http is None:
                await http.aclose()
        if resp.status_code != 200:
            raise TechnogymAuthError(
                f"token endpoint returned {resp.status_code}: {resp.text[:200]}"
            )
        return OAuthTokens.from_response(resp.json())

    async def exchange_code(self, code: str) -> OAuthTokens:
        if not code:
            raise TechnogymAuthError("authorization code is empty")
        return await self._post_token(
            _token_request_body(
                grant_type="authorization_code",
                code=code,
                redirect_uri=get_settings().technogym_redirect_uri,
            )
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        if not refresh_token:
            raise TechnogymAuthError("no refresh token available")
        return await self._post_token(
            _token_request_body(grant_type="refresh_token", refresh_token=refresh_token)
        )


class TechnogymClient(Protocol):
    """The surface the sync pipeline needs. Fixture implementations in tests
    mirror exactly these methods (§0: no live API in the test suite)."""

    async def get_workouts(self, start: int, limit: int) -> list[dict[str, Any]]:
        """Completed sessions, newest first, paginated (§6.3 backfill)."""
        ...

    async def get_workout_detail(self, workout_id: str) -> dict[str, Any]:
        """Full-fidelity record for one session (machine data), or {}."""
        ...


class LiveTechnogymClient:
    """Authenticated workout-pull client (Stage 11a pull path).

    `upload_fit` implements the optional FIT/TCX upload of §11a — available
    once the owner's real access tier confirms (§24); it is deliberately NOT
    wired into any automated flow.
    """

    def __init__(
        self,
        tokens: OAuthTokens,
        http: httpx.AsyncClient | None = None,
        oauth: TechnogymOAuth | None = None,
    ) -> None:
        self.tokens = tokens
        self.tokens_out: OAuthTokens | None = None  # rotated tokens for the caller to persist
        self._http = http
        # Share the injected transport with the OAuth half so a test-pinned
        # MockTransport also serves token refreshes (and production reuses
        # one connection pool).
        self._oauth = oauth or TechnogymOAuth(http=http)
        self._refresh_lock = asyncio.Lock()

    # ---------------------------------------------------------------- auth

    async def ensure_fresh(self) -> None:
        """Single-flight refresh when the access token is at/near expiry."""
        if self.tokens.expires_at is None:
            return  # server did not advertise expiry; use until it refuses
        margin = self.tokens.expires_at - timedelta(seconds=_EXPIRY_MARGIN_S)
        if datetime.now(UTC) < margin:
            return
        async with self._refresh_lock:
            # Re-check under the lock — a concurrent caller may have refreshed.
            margin = (self.tokens.expires_at or datetime.now(UTC)) - timedelta(
                seconds=_EXPIRY_MARGIN_S
            )
            if datetime.now(UTC) < margin:
                return
            if not self.tokens.refresh_token:
                raise TechnogymAuthError("access token expired and no refresh token stored")
            logger.info("technogym: refreshing access token")
            refreshed = await self._oauth.refresh(self.tokens.refresh_token)
            self.tokens = refreshed
            self.tokens_out = refreshed

    def _bearer(self) -> str:
        return f"Bearer {self.tokens.access_token}"

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self.ensure_fresh()
        settings = get_settings()
        http = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            resp = await http.get(
                f"{settings.technogym_api_base}{path}",
                params=params,
                headers={"Authorization": self._bearer()},
            )
        finally:
            if self._http is None:
                await http.aclose()
        if resp.status_code == 401:
            raise TechnogymAuthError(f"unauthorized calling {path} — re-authenticate")
        if resp.status_code != 200:
            raise TechnogymAuthError(f"GET {path} returned {resp.status_code}")
        return resp.json()

    # -------------------------------------------------------------- pulls

    async def get_workouts(self, start: int, limit: int) -> list[dict[str, Any]]:
        payload = await self._get_json(
            "/exercises", params={"offset": start, "limit": limit}
        )
        items = payload.get("items") if isinstance(payload, dict) else payload
        return items or []

    async def get_workout_detail(self, workout_id: str) -> dict[str, Any]:
        payload = await self._get_json(f"/exercises/{workout_id}")
        return payload or {}

    # ------------------------------------------------------------- uploads

    async def upload_fit(self, filename: str, content: bytes) -> dict[str, Any]:
        """Optional §11a FIT/TCX upload. Contingent on the real access tier
        (§24); not wired into any automated flow."""
        await self.ensure_fresh()
        settings = get_settings()
        http = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            resp = await http.post(
                f"{settings.technogym_api_base}/exercises/upload",
                files={"file": (filename, content)},
                headers={"Authorization": self._bearer()},
            )
        finally:
            if self._http is None:
                await http.aclose()
        if resp.status_code not in (200, 201, 202):
            raise TechnogymAuthError(
                f"FIT upload returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json() if resp.content else {}


def build_live_client(credentials: dict[str, Any] | None) -> LiveTechnogymClient:
    """Build the live client from stored (decrypted) credentials."""
    if not credentials:
        raise TechnogymAuthError(
            "Technogym credentials missing: connect via "
            "tools/technogym_connect.py or /settings/integrations first"
        )
    return LiveTechnogymClient(OAuthTokens.from_credentials(credentials))


def credentials_expired(credentials: dict[str, Any] | None) -> bool:
    """True when stored credentials are within the refresh margin (or unparsable)."""
    if not credentials:
        return True
    try:
        tokens = OAuthTokens.from_credentials(credentials)
    except TechnogymAuthError:
        return True
    if tokens.expires_at is None:
        return False
    return datetime.now(UTC) >= tokens.expires_at - timedelta(seconds=_EXPIRY_MARGIN_S)
