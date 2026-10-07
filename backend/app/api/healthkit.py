"""Cookie-free native endpoints and session-protected one-use pairing."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_session
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import hash_session_token, new_session_token
from app.models.healthkit import HealthKitBatch, HealthKitPairing
from app.models.user import AuthCredential, User, UserSession
from app.models.watch import DeviceToken
from app.schemas.healthkit import HealthKitDelta, PairingExchange
from app.services.evidence import scope_lock
from app.services.healthkit_ingest import ingest_healthkit

router = APIRouter(prefix="/healthkit", tags=["healthkit"])


def _cookie_free(request: Request):
    if "hcc_session" in request.cookies:
        raise HTTPException(400, "Native endpoints do not accept browser session cookies")


async def get_healthkit_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, DeviceToken]:
    _cookie_free(request)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    raw = authorization.split(" ", 1)[1].strip()
    if not 32 <= len(raw) <= 128:
        raise HTTPException(401, "Invalid token")
    hashed = hash_session_token(raw, get_settings().session_secret)
    candidate = await session.scalar(select(DeviceToken).where(DeviceToken.token_hash == hashed))
    if candidate is None or candidate.scope != "healthkit_sync":
        raise HTTPException(401, "Invalid or revoked token")
    # Serialize devices for one account, and re-read after taking the lock.
    # Revocation and disabled-account changes cannot interleave with a batch.
    await scope_lock(session, candidate.user_id, "changes")
    token = await session.scalar(select(DeviceToken).where(DeviceToken.id == candidate.id).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(UTC)
    if token is None or token.scope != "healthkit_sync" or token.revoked_at is not None or token.absolute_expires_at is None or token.absolute_expires_at <= now:
        raise HTTPException(401, "Invalid, expired or revoked token")
    credential = await session.scalar(select(AuthCredential).where(AuthCredential.user_id == token.user_id).with_for_update())
    user = await session.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if credential is None or credential.disabled or user is None:
        raise HTTPException(401, "Invalid or disabled account")
    return user, token


@router.post("/pairings", status_code=201)
async def create_pairing(
    session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session),
):
    user, _ = principal
    raw = new_session_token()
    now = datetime.now(UTC)
    # Only the newest unconsumed code survives an accidental repeat click.
    from sqlalchemy import update
    await scope_lock(session, user.id, "changes")
    await session.execute(update(HealthKitPairing).where(HealthKitPairing.user_id == user.id,
        HealthKitPairing.consumed_at.is_(None)).values(consumed_at=now))
    expires = now + timedelta(minutes=10)
    session.add(HealthKitPairing(user_id=user.id,
        code_hash=hash_session_token(raw, get_settings().session_secret), expires_at=expires))
    await session.commit()
    return {"code": raw, "expires_at": expires}


@router.post("/exchange")
async def exchange_pairing(payload: PairingExchange, request: Request,
    session: AsyncSession = Depends(get_session)):
    _cookie_free(request)
    hashed = hash_session_token(payload.code, get_settings().session_secret)
    candidate = await session.scalar(select(HealthKitPairing).where(HealthKitPairing.code_hash == hashed))
    if candidate is None:
        raise HTTPException(401, "Invalid or expired pairing code")
    await scope_lock(session, candidate.user_id, "changes")
    pairing = await session.scalar(select(HealthKitPairing).where(HealthKitPairing.id == candidate.id).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(UTC)
    if pairing is None or pairing.consumed_at is not None or pairing.expires_at <= now:
        raise HTTPException(401, "Invalid or expired pairing code")
    credential = await session.scalar(select(AuthCredential).where(AuthCredential.user_id == pairing.user_id).with_for_update())
    if credential is None or credential.disabled:
        raise HTTPException(401, "Invalid or disabled account")
    raw = new_session_token()
    token = DeviceToken(user_id=pairing.user_id, name=payload.name, scope="healthkit_sync",
        token_hash=hash_session_token(raw, get_settings().session_secret), sync_checkpoint=0,
        absolute_expires_at=now + timedelta(days=365))
    pairing.consumed_at = now
    session.add(token)
    await session.flush()
    result = {"token": raw, "device_id": token.id, "checkpoint": 0}
    await session.commit()
    return result


@router.get("/status")
async def sync_status(session: AsyncSession = Depends(get_session),
    principal: tuple[User, DeviceToken] = Depends(get_healthkit_principal)):
    user, token = principal
    # Feed metadata is bounded and never contains HK anchors or sample data.
    # Token-specific last_success avoids reporting another phone's delivery.
    last_success = await session.scalar(select(HealthKitBatch.created_at).where(
        HealthKitBatch.device_id == token.id).order_by(HealthKitBatch.checkpoint.desc()).limit(1))
    return {"device_id": token.id, "checkpoint": token.sync_checkpoint, "last_success_at": last_success}


@router.get("/devices")
async def list_devices(session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session)):
    user, _ = principal
    successful = select(HealthKitBatch.device_id, func.max(HealthKitBatch.created_at).label("last_success_at")).group_by(HealthKitBatch.device_id).subquery()
    rows = (await session.execute(select(DeviceToken, successful.c.last_success_at).outerjoin(
        successful, successful.c.device_id == DeviceToken.id).where(DeviceToken.user_id == user.id,
        DeviceToken.scope == "healthkit_sync").order_by(DeviceToken.created_at.desc(), DeviceToken.id.desc()))).all()
    return [{"id": token.id, "name": token.name, "created_at": token.created_at,
        "last_used_at": token.last_used_at, "revoked_at": token.revoked_at,
        "absolute_expires_at": token.absolute_expires_at, "checkpoint": token.sync_checkpoint,
        "last_success_at": last_success} for token, last_success in rows]


@router.delete("/devices/{device_id}", status_code=204)
async def revoke_device(device_id: int, session: AsyncSession = Depends(get_session),
    principal: tuple[User, UserSession] = Depends(get_current_session)):
    user, _ = principal
    await scope_lock(session, user.id, "changes")
    token = await session.scalar(select(DeviceToken).where(DeviceToken.id == device_id,
        DeviceToken.user_id == user.id, DeviceToken.scope == "healthkit_sync").with_for_update())
    if token is None:
        raise HTTPException(404, "Device not found")
    token.revoked_at = token.revoked_at or datetime.now(UTC)
    await session.commit()


@router.post("/deltas")
async def upload_deltas(payload: HealthKitDelta, session: AsyncSession = Depends(get_session),
    principal: tuple[User, DeviceToken] = Depends(get_healthkit_principal)):
    user, token = principal
    try:
        receipt = await ingest_healthkit(session, user, token, payload)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return receipt
