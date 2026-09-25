"""Auth service: owner bootstrap, login with lockout bookkeeping, server-side sessions.

Sessions are server-side rows (§2, §22.2): the cookie carries a random token,
only its peppered SHA-256 hash is stored. Expiry slides: once more than half
the TTL has passed, a valid request extends the session to a full TTL from now.
"""

import logging
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rate_limit import LoginRateLimiter
from app.core.config import get_settings
from app.core.security import (
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)
from app.models.user import AuthCredential, User, UserSession

logger = logging.getLogger("auth.service")


class AuthError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind  # "invalid_credentials" | "locked"


async def ensure_owner(session: AsyncSession) -> None:
    """Bootstrap the owner account from OWNER_EMAIL/OWNER_PASSWORD at startup (§15).

    Idempotent: does nothing when an owner already exists.
    """
    settings = get_settings()
    existing = await session.scalar(
        select(AuthCredential).where(AuthCredential.role == "owner")
    )
    if existing is not None:
        # Bug 11: an earlier deploy could have downgraded the owner's
        # ai_access_tier (admin role misassigned). On every startup, when an
        # owner already exists, restore the tier to 'full' so the owner keeps
        # their AI access regardless of any drift in the DB.
        if existing.ai_access_tier != "full":
            logger.warning(
                "owner account %s had ai_access_tier=%s — restoring to 'full'",
                existing.user_id,
                existing.ai_access_tier,
            )
            existing.ai_access_tier = "full"
            await session.commit()
        return

    user = User(name=settings.owner_email.split("@", 1)[0])
    session.add(user)
    await session.flush()
    session.add(
        AuthCredential(
            user_id=user.id,
            email=settings.owner_email,
            password_hash=hash_password(settings.owner_password),
            role="owner",
            ai_access_tier="full",
        )
    )
    await session.commit()


async def get_auth_credential(session: AsyncSession, email: str) -> AuthCredential | None:
    return await session.scalar(
        select(AuthCredential).where(AuthCredential.email == email.lower())
    )


async def authenticate(
    session: AsyncSession, redis: Redis, email: str, password: str
) -> AuthCredential:
    """Verify credentials, applying §22.1 lockout. Raises AuthError on failure.

    F-05 audit: the failed-login counter is incremented atomically via
    ``UPDATE ... SET count = count + 1`` so concurrent failures no longer
    undercount. The Redis window and DB counter share a single source of
    truth (Redis for the live window, DB for the persistent lockout state).
    F-06 audit: on success, rehash the password when argon2 params have
    drifted upward (gradual parameter upgrade without a forced reset).
    """
    settings = get_settings()
    limiter = LoginRateLimiter(redis, settings)
    cred = await get_auth_credential(session, email)

    def _locked() -> bool:
        return cred is not None and cred.locked_until is not None and cred.locked_until > datetime.now(UTC)

    if await limiter.is_locked(email) or _locked():
        raise AuthError("locked")

    if cred is None or not verify_password(cred.password_hash, password):
        if cred is not None:
            failures = await limiter.record_failure(email)
            # F-05: atomic SQL increment — concurrent failures no longer
            # race on the read-modify-write cycle.
            await session.execute(
                update(AuthCredential)
                .where(AuthCredential.user_id == cred.user_id)
                .values(failed_login_count=AuthCredential.failed_login_count + 1)
            )
            if failures >= settings.login_max_attempts:
                await session.execute(
                    update(AuthCredential)
                    .where(AuthCredential.user_id == cred.user_id)
                    .values(locked_until=datetime.now(UTC) + timedelta(
                        minutes=settings.login_lockout_minutes
                    ))
                )
            await session.commit()
        raise AuthError("invalid_credentials")

    # Success: clear both Redis window and DB counters.
    await limiter.reset(email)
    # F-05: atomic reset (no read-modify-write race on the success path either).
    await session.execute(
        update(AuthCredential)
        .where(AuthCredential.user_id == cred.user_id)
        .values(failed_login_count=0, locked_until=None)
    )
    # F-06: gradual argon2 parameter upgrade — if the stored hash was
    # produced with weaker params than the current defaults, rehash on
    # successful login. The user pays no cost (no reset); the next login
    # uses the stronger hash transparently.
    if needs_rehash(cred.password_hash):
        await session.execute(
            update(AuthCredential)
            .where(AuthCredential.user_id == cred.user_id)
            .values(password_hash=hash_password(password))
        )
    await session.commit()
    # Refresh the in-memory cred so the caller sees the updated counters.
    await session.refresh(cred)
    return cred


async def create_session(session: AsyncSession, user_id: int) -> tuple[str, datetime]:
    """Create a server-side session row; returns (raw_token, expires_at).

    F-21 audit: sets ``absolute_expires_at`` (30-day cap from creation) so
    sliding-expiry refresh cannot keep a stolen session alive forever.
    """
    settings = get_settings()
    token = new_session_token()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.session_ttl_minutes)
    # F-21: 30-day absolute lifetime — sliding refresh cannot extend past this.
    absolute_expires_at = now + timedelta(days=30)
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_session_token(token, settings.session_secret),
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
        )
    )
    await session.commit()
    return token, expires_at


async def resolve_session(
    session: AsyncSession, token: str
) -> tuple[User, UserSession] | None:
    """Return (user, session_row) for a valid, unexpired token; slides expiry.

    F-21 audit: rejects sessions past their ``absolute_expires_at`` regardless
    of sliding-refresh activity. A stolen session is therefore bounded to a
    maximum 30-day lifetime even if used continuously.
    """
    settings = get_settings()
    row = await session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token, settings.session_secret)
        )
    )
    if row is None or row.expires_at <= datetime.now(UTC):
        return None
    # F-21: absolute lifetime cap — checked AFTER the sliding-expiry check
    # so a session that has aged past absolute_expires_at is rejected even
    # if its sliding expiry was just refreshed.
    if row.absolute_expires_at is not None and row.absolute_expires_at <= datetime.now(UTC):
        return None

    # Sliding expiry: past half the TTL, extend to a full TTL from now (§22.2).
    # F-21: the extension is capped by absolute_expires_at — sliding refresh
    # cannot push the session past the absolute lifetime.
    half_life = row.created_at + timedelta(
        minutes=settings.session_ttl_minutes // 2
    )
    if datetime.now(UTC) > half_life:
        new_expiry = min(
            datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes),
            row.absolute_expires_at or datetime.max.replace(tzinfo=UTC),
        )
        await session.execute(
            update(UserSession)
            .where(UserSession.id == row.id)
            .values(expires_at=new_expiry)
        )
        await session.commit()
        row.expires_at = new_expiry

    user = await session.get(User, row.user_id)
    if user is None:
        return None
    return user, row


async def destroy_session(session: AsyncSession, token: str) -> bool:
    settings = get_settings()
    result = await session.execute(
        delete(UserSession).where(
            UserSession.token_hash == hash_session_token(token, settings.session_secret)
        )
    )
    await session.commit()
    return bool(result.rowcount)


def session_cookie_name() -> str:
    return "hcc_session"


def cookie_max_age_seconds() -> int:
    return get_settings().session_ttl_minutes * 60
