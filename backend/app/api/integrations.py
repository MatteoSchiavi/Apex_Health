"""Integration settings + Technogym OAuth endpoints (MASTER_SPEC §18
`/settings/integrations`, §11 Stage 11a, §23 Phase 6 AC1).

The connection itself is the owner's MANUAL step (§0/§16.7):

1. POST /settings/integrations/technogym/authorize   (session + CSRF)
   -> {authorize_url} — the owner opens it in a browser and logs into
   Technogym themselves.
2. GET  /integrations/technogym/callback             (no session — this is
   the provider's browser redirect; the single-use OAuth `state` in Redis is
   what authenticates and binds it to the right account)
   -> exchanges the code, stores tokens app-layer-encrypted (§17).

GET /settings/integrations lists the account's connector rows.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.connectors.strava.flow import (
    OAuthFlowError as StravaFlowError,
    complete_authorization as strava_complete,
    create_pending_authorization as strava_create_pending,
    flow_settings_ready as strava_flow_ready,
)
from app.connectors.technogym.flow import (
    OAuthFlowError,
    complete_authorization,
    create_pending_authorization,
    flow_settings_ready,
)
from app.connectors.whoop.flow import (
    OAuthFlowError as WhoopFlowError,
    complete_authorization as whoop_complete,
    create_pending_authorization as whoop_create_pending,
    flow_settings_ready as whoop_flow_ready,
)
from app.core.db import get_session
from app.core.redis import get_redis
from app.models.integration import Integration
from app.models.user import User

logger = logging.getLogger("api.integrations")

router = APIRouter(tags=["integrations"])


def _to_dict(integration: Integration) -> dict:
    return {
        "id": integration.id,
        "provider": integration.provider,
        "status": integration.status,
        "credentials_stored": integration.credentials_encrypted is not None,
        "last_synced_at": integration.last_synced_at,
        "consecutive_failures": integration.consecutive_failures,
    }


@router.get("/settings/integrations")
async def list_integrations(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Integration).where(Integration.user_id == user.id)
        )
    ).all()
    return [_to_dict(r) for r in rows]


@router.post("/settings/integrations/technogym/authorize")
async def start_technogym_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Mint the single-use state and return the URL the owner must open
    manually. State-changing (Redis write) -> CSRF header required (§22.3)."""
    if not flow_settings_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "TECHNOGYM_CLIENT_ID / TECHNOGYM_CLIENT_SECRET are not "
                "configured — register at developer.technogym.com first (§24)"
            ),
        )
    state, authorize_url = await create_pending_authorization(redis, user)
    logger.info("technogym OAuth: pending authorization minted for user %s", user.id)
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_seconds": 600,
        "note": (
            "Open the URL, log into Technogym, and approve — the provider "
            "then redirects to the configured redirect URI. Manual step (§0)."
        ),
    }


@router.get("/integrations/technogym/callback")
async def technogym_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Provider browser redirect target. No app session exists here — the
    single-use `state` is the authentication and account binding."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Technogym authorization failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="callback requires both 'code' and 'state' parameters",
        )
    try:
        return await complete_authorization(session, redis, code=code, state=state)
    except OAuthFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------------------- Whoop (v2)


@router.post("/settings/integrations/whoop/authorize")
async def start_whoop_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Mint the single-use state and return the Whoop authorization URL.
    State-changing (Redis write) -> CSRF header required (§22.3)."""
    if not whoop_flow_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET are not configured — "
                "register the app at developer.whoop.com first (INSTALL §7b)"
            ),
        )
    state, authorize_url = await whoop_create_pending(redis, user)
    logger.info("whoop OAuth: pending authorization minted for user %s", user.id)
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_seconds": 600,
        "note": (
            "Open the URL, log into Whoop, and approve — the provider then "
            "redirects to the configured redirect URI."
        ),
    }


@router.get("/integrations/whoop/callback")
async def whoop_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Whoop's browser redirect target (session-less; single-use state is
    the authentication and account binding)."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Whoop authorization failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="callback requires both 'code' and 'state' parameters",
        )
    try:
        return await whoop_complete(session, redis, code=code, state=state)
    except WhoopFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------------------- Strava (v3)


@router.post("/settings/integrations/strava/authorize")
async def start_strava_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    if not strava_flow_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET are not configured — "
                "register the app at strava.com/settings/api first (INSTALL §7c)"
            ),
        )
    state, authorize_url = await strava_create_pending(redis, user)
    logger.info("strava OAuth: pending authorization minted for user %s", user.id)
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_seconds": 600,
        "note": (
            "Open the URL, log into Strava, and approve — the provider then "
            "redirects to the configured redirect URI."
        ),
    }


@router.get("/integrations/strava/callback")
async def strava_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strava authorization failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="callback requires both 'code' and 'state' parameters",
        )
    try:
        return await strava_complete(session, redis, code=code, state=state)
    except StravaFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
