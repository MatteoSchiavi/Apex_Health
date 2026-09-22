"""Shared OAuth2 helpers for official-API connectors (Whoop, Strava).

The Technogym connector predates this module and keeps its own copy — new
official-API connectors share this one instead. Token payloads are stored
app-layer-encrypted in `integrations.credentials_encrypted` (§17) exactly
like every other connector: `OAuthTokens.as_credentials()` /
`from_credentials()` are the storage format.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings


class OAuth2Error(Exception):
    """Raised when OAuth cannot complete or credentials are unusable."""


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None  # UTC, from the token response's expires_in
    raw: dict[str, Any] = field(default_factory=dict)  # full response, raw-first

    @classmethod
    def from_response(
        cls, payload: dict[str, Any], now: datetime | None = None
    ) -> "OAuthTokens":
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise OAuth2Error(f"token response missing access_token: {payload!r}")
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
            raise OAuth2Error("stored credentials are missing access_token — connect first")
        expires_at = None
        if credentials.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(credentials["expires_at"])
            except ValueError as exc:
                raise OAuth2Error(f"stored expires_at unparsable: {exc}") from exc
        return cls(
            access_token=credentials["access_token"],
            refresh_token=credentials.get("refresh_token"),
            expires_at=expires_at,
            raw=credentials.get("raw") or {},
        )


def _client_pair(provider: str) -> tuple[str, str]:
    settings = get_settings()
    client_id = getattr(settings, f"{provider}_client_id", "")
    client_secret = getattr(settings, f"{provider}_client_secret", "")
    if not client_id or not client_secret:
        raise OAuth2Error(
            f"{provider.upper()}_CLIENT_ID / {provider.upper()}_CLIENT_SECRET "
            "are not configured — register the app on the provider's developer "
            "portal first"
        )
    return client_id, client_secret


def build_authorize_url(provider: str, state: str) -> str:
    """Authorization URL the user opens in a browser (manual step)."""
    settings = get_settings()
    client_id, _ = _client_pair(provider)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": getattr(settings, f"{provider}_redirect_uri"),
        "state": state,
        "scope": getattr(settings, f"{provider}_scope", "") or "",
        "approval_prompt": "auto",
    }
    base = getattr(settings, f"{provider}_oauth_authorize_url")
    return f"{base}?{urlencode({k: v for k, v in params.items() if v})}"


async def exchange_code(
    provider: str, code: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> OAuthTokens:
    """Authorization-code -> tokens (standard form POST)."""
    settings = get_settings()
    client_id, client_secret = _client_pair(provider)
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": getattr(settings, f"{provider}_redirect_uri"),
    }
    return await _token_request(
        getattr(settings, f"{provider}_oauth_token_url"), body, transport=transport
    )


async def refresh(
    provider: str, refresh_token: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> OAuthTokens:
    settings = get_settings()
    client_id, client_secret = _client_pair(provider)
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return await _token_request(
        getattr(settings, f"{provider}_oauth_token_url"), body, transport=transport
    )


async def _token_request(
    url: str,
    body: dict[str, str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthTokens:
    try:
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            resp = await client.post(url, data=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        raise OAuth2Error(
            f"token endpoint returned {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OAuth2Error(f"token endpoint unreachable: {exc}") from exc
    except ValueError as exc:
        raise OAuth2Error(f"token endpoint returned non-JSON: {exc}") from exc
    return OAuthTokens.from_response(payload)
