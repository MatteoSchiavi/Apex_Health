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

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.connectors.coros.flow import (
    OAuthFlowError as CorosFlowError,
    complete_authorization as coros_complete,
    create_pending_authorization as coros_create_pending,
    flow_settings_ready as coros_flow_ready,
)
from app.connectors.oura.flow import (
    OAuthFlowError as OuraFlowError,
    complete_authorization as oura_complete,
    create_pending_authorization as oura_create_pending,
    flow_settings_ready as oura_flow_ready,
)
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
from app.connectors.garmin.client import (
    GarminAuthError,
    LiveGarminClient,
)
from app.core.encryption import encrypt_json
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


# ------------------------------------------------------- Oura (API v2)


@router.post("/settings/integrations/oura/authorize")
async def start_oura_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Mint the single-use state and return the Oura authorization URL."""
    if not oura_flow_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "OURA_CLIENT_ID / OURA_CLIENT_SECRET are not configured — "
                "register a personal app at cloud.ouraring.com first "
                "(INSTALL §7e)"
            ),
        )
    state, authorize_url = await oura_create_pending(redis, user)
    logger.info("oura OAuth: pending authorization minted for user %s", user.id)
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_seconds": 600,
        "note": (
            "Open the URL, log into Oura, and approve — the provider then "
            "redirects to the configured redirect URI."
        ),
    }


@router.get("/integrations/oura/callback")
async def oura_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Oura authorization failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="callback requires both 'code' and 'state' parameters",
        )
    try:
        return await oura_complete(session, redis, code=code, state=state)
    except OuraFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------- COROS (Open API shell)


@router.post("/settings/integrations/coros/authorize")
async def start_coros_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """COROS gates API access behind a manual developer-portal review — this
    endpoint 400s with the explanation until COROS_CLIENT_ID/SECRET exist."""
    if not coros_flow_ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "COROS_CLIENT_ID / COROS_CLIENT_SECRET are not configured — "
                "apply at open.coros.com (manual review); when approved, set "
                "the env pair and this flow works unchanged (INSTALL §7f)"
            ),
        )
    state, authorize_url = await coros_create_pending(redis, user)
    logger.info("coros OAuth: pending authorization minted for user %s", user.id)
    return {
        "authorize_url": authorize_url,
        "state": state,
        "expires_in_seconds": 600,
        "note": "Open the URL, log into COROS, and approve.",
    }


@router.get("/integrations/coros/callback")
async def coros_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"COROS authorization failed: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="callback requires both 'code' and 'state' parameters",
        )
    try:
        return await coros_complete(session, redis, code=code, state=state)
    except CorosFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------- Garmin (credentials flow)
#
# Garmin's consumer API has no user-facing OAuth for self-registered apps —
# the connector logs in with the account credentials once (garminconnect
# 0.3.x native tokens) and stores ONLY the resulting session tokens,
# app-layer-encrypted (§17). The password itself is never persisted, never
# logged, and lives only for the duration of this request.


class GarminConnectIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    # When the account has MFA enabled the first call returns
    # {"mfa_required": true}; the client re-submits the same credentials plus
    # the one-time code from the user's authenticator/email.
    mfa_code: str | None = Field(default=None, max_length=12)


class _MfaRequired(Exception):
    """Internal: raised inside the (synchronous) login thread when the
    account needs a one-time code and none was supplied."""


@router.post("/settings/integrations/garmin/connect")
async def connect_garmin(
    payload: GarminConnectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Link a Garmin account from the UI.

    Runs the garminconnect login exchange in a worker thread (the lib is
    synchronous). Returns `{"mfa_required": true}` when the account has MFA
    and no code was supplied — the client then shows the code field and
    re-posts. On success the session tokens replace any previous credential
    blob, the integration goes active, and the per-user backfill task is
    enqueued (NULL last_synced_at = full walk, §6.3).

    F-11 audit: rate-limited to 3 connects/hour/IP (Redis sliding window) so
    the endpoint cannot be abused as a brute-force proxy against the user's
    real Garmin account. The password is zeroed from local scope immediately
    after the login thread returns. The backfill enqueue is scoped to THIS
    user (``garmin.sync_user.s(user.id)``) — never a global fan-out.
    """

    # F-11: rate limit — 3 connect attempts per hour per USER (the user is
    # already authenticated; keying on user_id is stronger than IP and
    # prevents one user from burning another's quota).
    rl_key = f"garmin_connect:rl:user:{user.id}"
    attempts = await redis.incr(rl_key)
    if attempts == 1:
        await redis.expire(rl_key, 3600)
    if attempts > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many Garmin connect attempts — wait an hour before retrying.",
        )

    def _mfa_prompt() -> str:
        if payload.mfa_code:
            return payload.mfa_code.strip()
        raise _MfaRequired()

    try:
        client = await asyncio.to_thread(
            LiveGarminClient.from_password,
            payload.email.strip(),
            payload.password,
            _mfa_prompt,
        )
    except _MfaRequired:
        return {
            "connected": False,
            "mfa_required": True,
            "note": "Account requires a one-time code — resubmit with mfa_code.",
        }
    except GarminAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Garmin connect failed: {exc}",
        ) from exc
    finally:
        # F-11: zero the password reference from request scope — Python's
        # GC will collect it on the next pass; the local binding is gone
        # immediately so a follow-up exception handler cannot read it.
        payload.password = "x" * len(payload.password)

    tokens = client.dump_tokens()
    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user.id, Integration.provider == "garmin"
        )
    )
    if integration is None:
        integration = Integration(user_id=user.id, provider="garmin", status="active")
        session.add(integration)
    integration.credentials_encrypted = encrypt_json(tokens)
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.last_synced_at = None  # next sync = full history walk
    await session.commit()
    logger.info("garmin connect: integration %s activated for user %s", integration.id, user.id)

    # F-11: enqueue the PER-USER backfill (NOT sync_all_garmin) so one user's
    # connect does not fan out to every other user's account.
    backfill_enqueued = True
    try:
        from app.tasks.garmin_sync import sync_user_garmin

        sync_user_garmin.delay(user.id)
    except Exception:  # noqa: BLE001 — broker down: next beat tick (6h) covers
        backfill_enqueued = False
        logger.warning("garmin connect: per-user backfill enqueue failed — beat will cover")

    return {
        "connected": True,
        "mfa_required": False,
        "provider": "garmin",
        "backfill_enqueued": backfill_enqueued,
    }


@router.post("/settings/integrations/garmin/sync")
async def sync_garmin_now(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """'Sync now' — enqueue the incremental Garmin poll immediately instead
    of waiting for the 6-hourly beat tick.

    F-11 audit: scoped to the connecting user (``garmin.sync_user.s(user.id)``)
    — never a global fan-out that would re-sync every other user's account.
    """
    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user.id, Integration.provider == "garmin"
        )
    )
    if integration is None or integration.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Garmin is not connected — connect it first.",
        )
    enqueued = True
    try:
        from app.tasks.garmin_sync import sync_user_garmin

        sync_user_garmin.delay(user.id)
    except Exception:  # noqa: BLE001
        enqueued = False
        logger.warning("garmin sync-now enqueue failed — beat will cover")
    return {"enqueued": enqueued}
