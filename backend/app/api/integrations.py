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
import hashlib
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_credential, get_current_user, require_owner
from app.connectors.garmin.metadata import garmin_auth_method
from app.connectors.garmin.personal import GarminPersonalClient, GarminPersonalError
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
from app.core.encryption import decrypt_json, encrypt_json
from app.core.db import get_session
from app.core.redis import get_redis_dependency
from app.models.integration import Integration
from app.models.user import AuthCredential, User
from app.services.alpha_events import record_event

logger = logging.getLogger("api.integrations")

router = APIRouter(tags=["integrations"])

_OAUTH_STATE_PROVIDERS = {"technogym", "whoop", "strava", "oura", "coros"}
_DISCONNECTABLE_PROVIDERS = _OAUTH_STATE_PROVIDERS | {"garmin"}


async def _discard_pending_oauth_states(
    redis: Redis, provider: str, user_id: int
) -> None:
    """Remove unconsumed authorization states for this account/provider."""
    if provider not in _OAUTH_STATE_PROVIDERS:
        return
    keys = []
    async for key in redis.scan_iter(match=f"{provider}:oauth:state:*"):
        owner = await redis.get(key)
        if owner is not None and str(
            owner.decode() if isinstance(owner, bytes) else owner
        ) == str(user_id):
            keys.append(key)
    if keys:
        await redis.delete(*keys)


async def _revoke_strava_access_token(credentials: dict) -> bool:
    """Call Strava's documented deauthorization endpoint when possible."""
    access_token = credentials.get("access_token")
    if not access_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://www.strava.com/oauth/deauthorize",
                data={"access_token": access_token},
            )
        return response.is_success
    except httpx.HTTPError:
        logger.warning("strava provider deauthorization was not confirmed")
        return False


def _to_dict(integration: Integration, *, is_owner: bool = False) -> dict:
    from app.connectors.support import support_for
    return {
        "id": integration.id,
        "provider": integration.provider,
        "support": support_for(integration.provider),
        "status": integration.status,
        "credentials_stored": integration.credentials_encrypted is not None,
        "last_synced_at": integration.last_synced_at,
        "consecutive_failures": integration.consecutive_failures,
        "auth_method": garmin_auth_method(integration, is_owner=is_owner),
    }


def _connection_result(request: Request, result: dict) -> dict | Response:
    """Return athletes to their device settings after browser OAuth consent."""
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/app/settings?tab=devices", status_code=303)
    return result


async def _record_oauth_connection(session: AsyncSession, result: dict, provider: str):
    # OAuth state determines account ownership inside the flow. The callback
    # does not infer the account from a browser cookie or provider payload.
    try:
        if result.get("provider") != provider:
            return
        if provider == "oura":
            ident = result.get("integration_id")
            if not isinstance(ident, int) or isinstance(ident, bool) or ident <= 0:
                return
            integration = await session.get(Integration, ident)
        else:
            # Technogym, WHOOP and Strava return the user bound to consumed
            # OAuth state; Oura returns the committed integration's ID.
            user_id = result.get("user_id")
            if (result.get("status") != "connected" or not isinstance(user_id, int)
                    or isinstance(user_id, bool) or user_id <= 0):
                return
            integration = await session.scalar(select(Integration).where(
                Integration.user_id == user_id, Integration.provider == provider,
                Integration.status == "active",
            ))
        if (integration is not None and integration.provider == provider
                and integration.status == "active"):
            record_event(session, integration.user_id, "integration_connected", {"provider": provider})
            await session.commit()
    except Exception:
        # The flow already committed credentials. An event-storage outage
        # must not tell the athlete that the completed connection failed.
        await session.rollback()
        logger.warning("connection outcome event unavailable")


@router.get("/settings/integrations")
async def list_integrations(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    credential: AuthCredential = Depends(get_current_credential),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Integration).where(Integration.user_id == user.id)
        )
    ).all()
    return [_to_dict(r, is_owner=credential.role == "owner") for r in rows]


@router.delete("/settings/integrations/{provider}")
async def disconnect_integration(
    provider: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    """Remove this account's saved provider credentials and stop future syncs.

    Historical imported records remain untouched. The sync advisory lock makes
    a disconnect wait-free and prevents a running import from racing it.
    """
    if provider not in _DISCONNECTABLE_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not found")

    lock_id = int.from_bytes(
        hashlib.sha256(f"sync:{provider}:{user.id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    if not await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A sync is running for this provider; disconnect again when it finishes.",
        )

    integration = await session.scalar(
        select(Integration).where(
            Integration.user_id == user.id, Integration.provider == provider
        )
    )
    if integration is None:
        await _discard_pending_oauth_states(redis, provider, user.id)
        return {
            "provider": provider,
            "disconnected": False,
            "provider_revocation": "unsupported",
        }

    credentials = None
    if provider == "strava" and integration.credentials_encrypted:
        try:
            credentials = decrypt_json(integration.credentials_encrypted)
        except Exception:  # noqa: BLE001 — local disconnect must still succeed
            logger.warning("stored Strava credentials could not be read for revocation")

    await _discard_pending_oauth_states(redis, provider, user.id)
    integration.status = "revoked"
    integration.credentials_encrypted = None
    integration.consecutive_failures = 0
    if user.main_integration_id == integration.id:
        user.main_integration_id = None
    await session.commit()

    provider_revocation = "unsupported"
    if provider == "strava":
        provider_revocation = (
            "confirmed"
            if credentials and await _revoke_strava_access_token(credentials)
            else "not_confirmed"
        )
    logger.info("%s integration disconnected for user %s", provider, user.id)
    return {
        "provider": provider,
        "disconnected": True,
        "provider_revocation": provider_revocation,
    }


@router.post("/settings/integrations/technogym/authorize")
async def start_technogym_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
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


@router.get("/integrations/technogym/callback", response_model=None)
async def technogym_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict | Response:
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
        result = await complete_authorization(session, redis, code=code, state=state)
        await _record_oauth_connection(session, result, "technogym")
        return _connection_result(request, result)
    except OAuthFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------------------- Whoop (v2)


@router.post("/settings/integrations/whoop/authorize")
async def start_whoop_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
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


@router.get("/integrations/whoop/callback", response_model=None)
async def whoop_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict | Response:
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
        result = await whoop_complete(session, redis, code=code, state=state)
        await _record_oauth_connection(session, result, "whoop")
        return _connection_result(request, result)
    except WhoopFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------------------- Strava (v3)


@router.post("/settings/integrations/strava/authorize")
async def start_strava_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
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


@router.get("/integrations/strava/callback", response_model=None)
async def strava_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict | Response:
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
        result = await strava_complete(session, redis, code=code, state=state)
        await _record_oauth_connection(session, result, "strava")
        return _connection_result(request, result)
    except StravaFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------------- Oura (API v2)


@router.post("/settings/integrations/oura/authorize")
async def start_oura_authorization(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
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


@router.get("/integrations/oura/callback", response_model=None)
async def oura_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict | Response:
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
        result = await oura_complete(session, redis, code=code, state=state)
        await _record_oauth_connection(session, result, "oura")
        return _connection_result(request, result)
    except OuraFlowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


# ------------------------------------------------- COROS (MCP)


class CorosMcpConnectIn(BaseModel):
    access_token: str = Field(min_length=1, max_length=4096, repr=False)


@router.get("/settings/integrations/coros/mcp/status")
async def coros_mcp_status(user: User = Depends(get_current_user)) -> dict:
    from app.core.config import get_settings
    settings = get_settings()
    return {"configured": bool(settings.coros_mcp_url and settings.coros_mcp_activity_tool)}


@router.post("/settings/integrations/coros/mcp/connect")
async def connect_coros_mcp(
    payload: CorosMcpConnectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    from app.connectors.coros.client import CorosAuthError, build_live_client
    from app.connectors.coros.mcp import MCPError
    from app.connectors.coros.sync import _activities_from_result
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.coros_mcp_url or not settings.coros_mcp_activity_tool:
        raise HTTPException(409, "Configure COROS_MCP_URL and the server's COROS_MCP_ACTIVITY_TOOL first")
    lock_id = int.from_bytes(hashlib.sha256(f"sync:coros:{user.id}".encode()).digest()[:8], "big", signed=True)
    if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}):
        raise HTTPException(409, "A COROS sync is running; try connecting again when it finishes")
    credentials = {"mcp_access_token": payload.access_token}
    try:
        client = build_live_client(credentials)
        result = await client.fetch_activities()
        if _activities_from_result(result) is None:
            raise HTTPException(422, "COROS MCP tool result does not match the configured activity contract")
    except (CorosAuthError, MCPError):
        raise HTTPException(422, "COROS MCP connection could not be verified; check the server, tool and account token") from None
    finally:
        payload.access_token = ""
    integration = await session.scalar(select(Integration).where(
        Integration.user_id == user.id, Integration.provider == "coros",
    ))
    if integration is None:
        integration = Integration(user_id=user.id, provider="coros")
        session.add(integration)
    integration.credentials_encrypted = encrypt_json(credentials)
    integration.status = "active"
    integration.consecutive_failures = 0
    integration.last_synced_at = None
    await _discard_pending_oauth_states(redis, "coros", user.id)
    record_event(session, user.id, "integration_connected", {"provider": "coros"})
    await session.commit()
    return {"connected": True, "provider": "coros"}


@router.post("/settings/integrations/coros/authorize")
async def start_coros_authorization(user: User = Depends(get_current_user)) -> dict:
    raise HTTPException(410, "COROS now connects through your configured MCP server in Settings")


@router.get("/integrations/coros/callback")
async def coros_oauth_callback() -> dict:
    raise HTTPException(410, "COROS OAuth has been retired; connect through the configured MCP server")


# ------------------------------------------------- Garmin (credentials flow)
#
# Garmin's consumer API has no user-facing OAuth for self-registered apps —
# the connector logs in with the account credentials once (garminconnect
# 0.3.x native tokens) and stores ONLY the resulting session tokens,
# app-layer-encrypted (§17). The password itself is never persisted, never
# logged, and lives only for the duration of this request.


async def _limit_garmin_connect(redis: Redis, user_id: int) -> None:
    # Shared by both Garmin connection methods. INCR + EXPIRE must be atomic:
    # interruption between them must not leave a permanent rate-limit key.
    attempts = await redis.eval("""
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], 3600) end
        return count
    """, 1, f"garmin_connect:rl:user:{user_id}")
    if int(attempts) > 3:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many Garmin connect attempts; wait an hour before retrying.",
            headers={"Retry-After": "3600"},
        )


async def _lock_garmin_connection(session: AsyncSession, user_id: int) -> None:
    # Same transaction lock as disconnect and the sync worker. Hold it through
    # authentication + commit, so an in-flight sync cannot restore old tokens.
    lock_id = int.from_bytes(
        hashlib.sha256(f"sync:garmin:{user_id}".encode()).digest()[:8],
        "big", signed=True,
    )
    if not await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}
    ):
        raise HTTPException(409, "A Garmin sync or connection is running; try again when it finishes.")


class GarminPersonalConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("api_key")
    @classmethod
    def nonempty_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A Garmin Personal API key is required")
        return value


@router.post("/settings/integrations/garmin/personal/connect", dependencies=[Depends(require_owner)])
async def connect_garmin_personal(
    payload: GarminPersonalConnectIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    """Verify and save the owner's official Garmin Personal API key.

    This is a personal-use pilot. Friend accounts need a separately approved
    Garmin Business API integration; they cannot use this endpoint.
    """
    from starlette.concurrency import run_in_threadpool

    await _limit_garmin_connect(redis, user.id)
    await _lock_garmin_connection(session, user.id)
    client = None
    try:
        client = GarminPersonalClient({
            "auth_type": "personal_api_key",
            "api_key": payload.api_key.get_secret_value(),
        })
        # Do not touch an existing working integration until the official
        # Garmin exchange has accepted the new key.
        await client.authenticate()
        encrypted_credentials = encrypt_json(client.dump_tokens())
    except GarminAuthError:
        raise HTTPException(400, "Garmin Personal API key could not be verified; check or replace the key.") from None
    except GarminPersonalError as exc:
        if exc.status_code == 429:
            raise HTTPException(429, "Garmin is limiting connection attempts; try again later.") from None
        if exc.error_class == "permission":
            raise HTTPException(400, "Garmin Personal API access is not permitted; review the key's access.") from None
        raise HTTPException(503, "Garmin Personal API is temporarily unavailable; try again shortly.") from None
    finally:
        payload.api_key = SecretStr("")
        if client is not None:
            await client.aclose()

    integration = await session.scalar(select(Integration).where(
        Integration.user_id == user.id, Integration.provider == "garmin",
    ))
    if integration is None:
        integration = Integration(user_id=user.id, provider="garmin")
        session.add(integration)
    integration.credentials_encrypted = encrypted_credentials
    integration.status = "active"
    integration.consecutive_failures = 0
    # Keep the row, main device preference, imported history and sync watermark.
    # Personal API coverage is bounded by the transport, not by resetting history.
    record_event(session, user.id, "integration_connected", {"provider": "garmin"})
    await session.commit()

    backfill_enqueued = True
    try:
        from app.tasks.garmin_sync import sync_user_garmin
        await run_in_threadpool(sync_user_garmin.delay, user.id)
    except Exception:
        backfill_enqueued = False
        logger.warning("garmin personal connect: per-user sync enqueue unavailable")
    return {
        "connected": True,
        "provider": "garmin",
        "auth_method": "personal_api_key",
        "backfill_enqueued": backfill_enqueued,
    }


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
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    """Link a Garmin account from the UI.

    Runs the garminconnect login exchange in a worker thread (the lib is
    synchronous). Returns `{"mfa_required": true}` when the account has MFA
    and no code was supplied — the client then shows the code field and
    re-posts. On success the session tokens replace any previous credential
    blob, the integration goes active, and the per-user backfill task is
    enqueued. Existing history and the sync watermark are preserved; a new
    integration starts with NULL last_synced_at (§6.3).

    F-11 audit: rate-limited to 3 connects/hour/user (Redis fixed window) so
    the endpoint cannot be abused as a brute-force proxy against the user's
    real Garmin account. The password is zeroed from local scope immediately
    after the login thread returns. The backfill enqueue is scoped to THIS
    user (``garmin.sync_user.s(user.id)``) — never a global fan-out.
    """

    # F-11: rate limit — 3 connect attempts per hour per USER (the user is
    # already authenticated; keying on user_id is stronger than IP and
    # prevents one user from burning another's quota).
    await _limit_garmin_connect(redis, user.id)
    await _lock_garmin_connection(session, user.id)

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
    except GarminAuthError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Garmin connect failed; check your credentials and try again.",
        ) from None
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
    from app.connectors.garmin.sync import clear_personal_api_coverage
    await clear_personal_api_coverage(session, user.id)
    record_event(session, user.id, "integration_connected", {"provider": "garmin"})
    await session.commit()
    logger.info("garmin connect: integration %s activated for user %s", integration.id, user.id)

    # F-11: enqueue the PER-USER backfill (NOT sync_all_garmin) so one user's
    # connect does not fan out to every other user's account.
    backfill_enqueued = True
    try:
        from app.tasks.garmin_sync import sync_user_garmin
        sync_user_garmin.delay(user.id)
    except Exception:
        backfill_enqueued = False
        logger.warning("garmin connect: per-user backfill enqueue failed — beat will cover")

    return {
        "connected": True,
        "mfa_required": False,
        "provider": "garmin",
        "backfill_enqueued": backfill_enqueued,
    }


@router.post("/settings/integrations/garmin/sync", status_code=status.HTTP_202_ACCEPTED)
@router.post("/settings/integrations/{provider}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_garmin_now(
    provider: str = "garmin",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    """Queue one account's sync; a status resource exposes progress safely."""
    from uuid import uuid4
    from starlette.concurrency import run_in_threadpool
    from importlib import import_module
    if provider not in _DISCONNECTABLE_PROVIDERS:
        raise HTTPException(404, "Unknown integration")
    task = import_module(f"app.tasks.{provider}_sync").__dict__[f"sync_user_{provider}"]

    integration = await session.scalar(select(Integration).where(
        Integration.user_id == user.id, Integration.provider == provider,
        Integration.status == "active",
    ))
    if integration is None:
        raise HTTPException(400, "Provider is not connected — connect it first.")
    job_id = str(uuid4())
    try:
        # Ownership precedes publishing so even a fast worker result is scoped.
        await redis.set(f"sync:job:{job_id}", str(user.id), ex=7 * 24 * 3600)
        await run_in_threadpool(task.apply_async, args=[user.id], task_id=job_id)
    except Exception:
        logger.warning("Could not enqueue %s sync for user %s", provider, user.id)
        raise HTTPException(503, "Sync queue unavailable; try again shortly.") from None
    return {"enqueued": True, "completed": False, "job_id": job_id,
            "status_url": f"/settings/integrations/{provider}/sync/{job_id}"}


@router.get("/settings/integrations/garmin/sync/{job_id}")
@router.get("/settings/integrations/{provider}/sync/{job_id}")
async def garmin_sync_status(
    job_id: str,
    provider: str = "garmin",
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
) -> dict:
    from starlette.concurrency import run_in_threadpool
    from app.tasks.celery_app import celery_app

    try:
        owner = await redis.get(f"sync:job:{job_id}")
    except Exception:
        raise HTTPException(503, "Sync status unavailable; try again shortly.") from None
    if owner is None or str(owner.decode() if isinstance(owner, bytes) else owner) != str(user.id):
        raise HTTPException(404, "Sync job not found")

    def read_status():
        result = celery_app.AsyncResult(job_id)
        state = result.state
        payload = {"job_id": job_id, "state": state,
                   "completed": state in {"SUCCESS", "FAILURE", "REVOKED"}}
        if state == "SUCCESS" and isinstance(result.result, dict):
            payload["result"] = {k: v for k, v in result.result.items()
                                 if k in {"status", "mode", "raw_stored", "unprocessed", "streams_failed"}}
            if result.result.get("status") == "skipped" and result.result.get("reason") == "already_running":
                payload["result"]["reason"] = "already_running"
        elif state == "FAILURE":
            from app.connectors.escalation import sync_error_class
            payload["error_class"] = sync_error_class(result.result)
            payload["error"] = ("Provider authentication or permission is required; reconnect or review provider access."
                                if payload["error_class"] in {"authentication", "permission"}
                                else "The synchronization attempt failed after retries; imported data remains available. Retry or review provider access.")
        return payload
    try:
        return await run_in_threadpool(read_status)
    except Exception:
        raise HTTPException(503, "Sync status unavailable; try again shortly.") from None
