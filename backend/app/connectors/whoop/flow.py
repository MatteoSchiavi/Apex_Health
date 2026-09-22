"""Whoop OAuth connection flow — cloned from the Technogym pattern.

CSRF/state model: the authorize step mints a single-use random `state`
stored in Redis under `whoop:oauth:state:{state}` -> user_id with a
10-minute TTL. The provider's browser redirect must echo it; it is consumed
on first use (the session-less callback cannot carry app cookies).
"""

import secrets

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.whoop.client import (
    WhoopAuthError,
    WhoopOAuth,
    build_authorize_url,
)
from app.core.config import get_settings
from app.core.encryption import encrypt_json
from app.models.integration import Integration
from app.models.user import User

STATE_TTL_SECONDS = 600
_STATE_KEY = "whoop:oauth:state:{state}"


class OAuthFlowError(Exception):
    """Raised for user-facing flow failures (bad/expired state, provider
    errors, unconfigured client)."""


def flow_settings_ready() -> bool:
    settings = get_settings()
    return bool(settings.whoop_client_id and settings.whoop_client_secret)


async def create_pending_authorization(
    redis: Redis, user: User
) -> tuple[str, str]:
    """Mint (state, authorize_url). The user opens the URL and logs into
    Whoop themselves — never automated."""
    state = secrets.token_urlsafe(32)
    await redis.set(_STATE_KEY.format(state=state), str(user.id), ex=STATE_TTL_SECONDS)
    return state, build_authorize_url(state)


async def complete_authorization(
    session: AsyncSession, redis: Redis, *, code: str, state: str
) -> dict:
    """Validate the single-use state, exchange the code for tokens, store
    them app-layer-encrypted on the user's whoop integration row."""
    key = _STATE_KEY.format(state=state)
    stored_user_id = await redis.get(key)
    if not stored_user_id:
        raise OAuthFlowError("unknown or expired state — start the authorization again")
    consumed = await redis.delete(key)
    if not consumed:  # concurrent double-use of the same state
        raise OAuthFlowError("state already used")

    user_id = int(stored_user_id)
    try:
        tokens = await WhoopOAuth().exchange_code(code)
    except WhoopAuthError as exc:
        raise OAuthFlowError(f"token exchange failed: {exc}") from exc

    user = await session.get(User, user_id)
    if user is None:  # pragma: no cover - state only mints for real users
        raise OAuthFlowError("state points at a missing account")

    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == "whoop"
        )
    )
    if integration is None:
        integration = Integration(user_id=user_id, provider="whoop", status="active")
        session.add(integration)
        await session.flush()
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.credentials_encrypted = encrypt_json(tokens.as_credentials())
    await session.commit()
    from datetime import UTC

    return {
        "status": "connected",
        "provider": "whoop",
        "user_id": user_id,
        "expires_at": (
            tokens.expires_at.astimezone(UTC).isoformat() if tokens.expires_at else None
        ),
    }
