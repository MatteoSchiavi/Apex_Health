"""Auth service: owner bootstrap, login with lockout bookkeeping, server-side sessions.

Sessions are server-side rows (§2, §22.2): the cookie carries a random token,
only its peppered SHA-256 hash is stored. Expiry slides: once more than half
the TTL has passed, a valid request extends the session to a full TTL from now.
"""

from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rate_limit import LoginRateLimiter
from app.core.config import get_settings
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.models.user import AuthCredential, User, UserSession


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
    """Verify credentials, applying §22.1 lockout. Raises AuthError on failure."""
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
            session.add(cred)
            cred.failed_login_count = cred.failed_login_count + 1
            if failures >= settings.login_max_attempts:
                cred.locked_until = datetime.now(UTC) + timedelta(
                    minutes=settings.login_lockout_minutes
                )
            await session.commit()
        raise AuthError("invalid_credentials")

    # Success: clear both Redis window and DB counters.
    await limiter.reset(email)
    session.add(cred)
    cred.failed_login_count = 0
    cred.locked_until = None
    await session.commit()
    return cred


async def create_session(session: AsyncSession, user_id: int) -> tuple[str, datetime]:
    """Create a server-side session row; returns (raw_token, expires_at)."""
    settings = get_settings()
    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes)
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_session_token(token, settings.session_secret),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return token, expires_at


async def resolve_session(
    session: AsyncSession, token: str
) -> tuple[User, UserSession] | None:
    """Return (user, session_row) for a valid, unexpired token; slides expiry."""
    settings = get_settings()
    row = await session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token, settings.session_secret)
        )
    )
    if row is None or row.expires_at <= datetime.now(UTC):
        return None

    # Sliding expiry: past half the TTL, extend to a full TTL from now (§22.2).
    half_life = row.created_at + timedelta(
        minutes=settings.session_ttl_minutes // 2
    )
    if datetime.now(UTC) > half_life:
        new_expiry = datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes)
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
