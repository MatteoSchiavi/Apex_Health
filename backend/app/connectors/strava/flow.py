"""Strava OAuth connection flow — Whoop/Technogym pattern (single-use Redis
state, session-less callback, app-layer-encrypted token storage)."""

import secrets
from datetime import UTC

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.strava.client import (
    StravaAuthError,
    StravaOAuth,
    build_authorize_url,
)
from app.core.config import get_settings
from app.core.encryption import encrypt_json
from app.models.integration import Integration
from app.models.user import User

STATE_TTL_SECONDS = 600
_STATE_KEY = "strava:oauth:state:{state}"


class OAuthFlowError(Exception):
    pass


def flow_settings_ready() -> bool:
    settings = get_settings()
    return bool(settings.strava_client_id and settings.strava_client_secret)


async def create_pending_authorization(
    redis: Redis, user: User
) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    await redis.set(_STATE_KEY.format(state=state), str(user.id), ex=STATE_TTL_SECONDS)
    return state, build_authorize_url(state)


async def complete_authorization(
    session: AsyncSession, redis: Redis, *, code: str, state: str
) -> dict:
    key = _STATE_KEY.format(state=state)
    stored_user_id = await redis.get(key)
    if not stored_user_id:
        raise OAuthFlowError("unknown or expired state — start the authorization again")
    consumed = await redis.delete(key)
    if not consumed:
        raise OAuthFlowError("state already used")

    user_id = int(stored_user_id)
    try:
        tokens = await StravaOAuth().exchange_code(code)
    except StravaAuthError as exc:
        raise OAuthFlowError(f"token exchange failed: {exc}") from exc

    user = await session.get(User, user_id)
    if user is None:  # pragma: no cover
        raise OAuthFlowError("state points at a missing account")

    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == "strava"
        )
    )
    if integration is None:
        integration = Integration(user_id=user_id, provider="strava", status="active")
        session.add(integration)
        await session.flush()
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.credentials_encrypted = encrypt_json(tokens.as_credentials())
    await session.commit()
    return {
        "status": "connected",
        "provider": "strava",
        "user_id": user_id,
        "expires_at": (
            tokens.expires_at.astimezone(UTC).isoformat() if tokens.expires_at else None
        ),
    }
