"""Serialize OAuth completion with account-scoped sync and disconnect."""
import hashlib

from sqlalchemy import text


class PendingAuthorizationError(Exception):
    pass


async def consume_pending_state(session, redis, *, provider: str, state: str) -> int:
    key = f"{provider}:oauth:state:{state}"
    owner = await redis.get(key)
    if not owner:
        raise PendingAuthorizationError("unknown or expired state — start the authorization again")
    user_id = int(owner)
    lock_id = int.from_bytes(
        hashlib.sha256(f"sync:{provider}:{user_id}".encode()).digest()[:8],
        "big", signed=True,
    )
    if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}):
        raise PendingAuthorizationError("integration is busy; retry authorization when the sync finishes")
    # Recheck after taking the lock. A disconnect may have invalidated the
    # state between the initial lookup and lock acquisition.
    consumed = await redis.getdel(key)
    if consumed != owner:
        raise PendingAuthorizationError("state already used or cancelled")
    return user_id
