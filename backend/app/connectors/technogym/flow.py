"""Technogym OAuth connection flow (MASTER_SPEC §11 Stage 11a, §23 Phase 6 AC1).

The real-account connection is the owner's MANUAL step (§0/§16.7): this module
holds the pieces both surfaces share —

- the API endpoints (/settings/integrations/technogym/authorize + the
  provider-redirected /integrations/technogym/callback), and
- the owner CLI (tools/technogym_connect.py), which supports the paste-the-code
  variant for hosts where the redirect URI is not reachable.

CSRF/state model: the authorize step mints a single-use random `state` stored
in Redis under `technogym:oauth:state:{state}` -> user_id with a 10-minute TTL.
The callback must echo it; it is consumed on first use. This protects the
session-less callback (the browser redirect cannot carry app cookies) and is
also what binds a manual code-paste to the right account.
"""

import secrets
from datetime import UTC

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.technogym.client import (
    OAuthTokens,
    TechnogymAuthError,
    TechnogymOAuth,
    build_authorize_url,
)
from app.core.config import get_settings
from app.core.encryption import encrypt_json
from app.models.integration import Integration
from app.models.user import User

STATE_TTL_SECONDS = 600
_STATE_KEY = "technogym:oauth:state:{state}"


class OAuthFlowError(Exception):
    """Raised for user-facing flow failures (bad/expired state, provider
    errors, unconfigured client)."""


async def create_pending_authorization(
    redis: Redis, user: User, *, scope: str | None = None
) -> tuple[str, str]:
    """Mint (state, authorize_url). The owner opens the URL in a browser and
    logs into Technogym themselves — never automated (§0)."""
    state = secrets.token_urlsafe(32)
    await redis.set(
        _STATE_KEY.format(state=state), str(user.id), ex=STATE_TTL_SECONDS
    )
    return state, build_authorize_url(state, scope=scope)


async def complete_authorization(
    session: AsyncSession, redis: Redis, *, code: str, state: str
) -> dict:
    """Validate the single-use state, exchange the code for tokens, store
    them app-layer-encrypted on the owner's technogym integration row.

    Returns a small status dict; raises OAuthFlowError for anything the
    user can fix (bad state, provider refusal, unconfigured client)."""
    key = _STATE_KEY.format(state=state)
    stored_user_id = await redis.get(key)
    if not stored_user_id:
        raise OAuthFlowError(
            "unknown or expired state — start the authorization again"
        )
    consumed = await redis.delete(key)
    if not consumed:  # concurrent double-use of the same state
        raise OAuthFlowError("state already used")

    user_id = int(stored_user_id)
    try:
        tokens: OAuthTokens = await TechnogymOAuth().exchange_code(code)
    except TechnogymAuthError as exc:
        raise OAuthFlowError(f"token exchange failed: {exc}") from exc

    user = await session.get(User, user_id)
    if user is None:  # pragma: no cover - state only mints for real users
        raise OAuthFlowError("state points at a missing account")

    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == "technogym"
        )
    )
    if integration is None:
        integration = Integration(user_id=user_id, provider="technogym", status="active")
        session.add(integration)
        await session.flush()
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.credentials_encrypted = encrypt_json(tokens.as_credentials())
    await session.commit()
    return {
        "status": "connected",
        "provider": "technogym",
        "user_id": user_id,
        "expires_at": (
            tokens.expires_at.astimezone(UTC).isoformat()
            if tokens.expires_at
            else None
        ),
    }


def flow_settings_ready() -> bool:
    """True when TECHNOGYM_CLIENT_ID/SECRET are configured (§5)."""
    settings = get_settings()
    return bool(
        settings.technogym_client_id and settings.technogym_client_secret
    )
