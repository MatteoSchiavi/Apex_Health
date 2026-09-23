"""Oura OAuth connection flow — same state/single-use model as Whoop.

The authorize step mints a single-use random `state` stored in Redis under
`oura:oauth:state:{state}` -> user_id with a 10-minute TTL; the provider's
redirect echoes it and it is consumed on first use.
"""

import secrets

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.oura.client import build_authorize_url, exchange
from app.core.config import get_settings
from app.core.encryption import encrypt_json
from app.models.integration import Integration
from app.models.user import User

STATE_TTL_SECONDS = 600
_STATE_KEY = "oura:oauth:state:{state}"


class OAuthFlowError(Exception):
    """User-facing flow failure (bad/expired state, provider error, no config)."""


def flow_settings_ready() -> bool:
    settings = get_settings()
    return bool(settings.oura_client_id and settings.oura_client_secret)


async def create_pending_authorization(redis: Redis, user: User) -> tuple[str, str]:
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

    tokens = await exchange(code)
    user_id = int(stored_user_id)
    integration = (
        await session.scalars(
            select(Integration).where(
                Integration.user_id == user_id, Integration.provider == "oura"
            )
        )
    ).first()
    if integration is None:
        integration = Integration(user_id=user_id, provider="oura")
        session.add(integration)
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.credentials_encrypted = encrypt_json(tokens.as_credentials())
    await session.commit()
    return {"integration_id": integration.id, "provider": "oura"}
