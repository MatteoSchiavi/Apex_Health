"""Invite flow (§15, §6.4 invites): owner mints codes, friends redeem them.

The invite code is a capability token: possession of a live (unused,
unexpired) code lets exactly one person create exactly one friend account
and start a session in the same request. Redemption claims the row with
SELECT ... FOR UPDATE before the user is created, so two concurrent
redemptions of the same code cannot both succeed (one waits on the lock,
then sees used_by set and fails).
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import AuthCredential, Invite, User

# 128-bit capability: unguessable even against an online guessing loop, and
# short enough to read aloud from a phone screen in two chunks.
CODE_LENGTH_BYTES = 16

# Default validity the owner gets when they don't pick a window.
DEFAULT_EXPIRY_DAYS = 7


class InviteError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind  # "invalid" | "used" | "expired" | "email_taken"


def new_invite_code() -> str:
    return secrets.token_urlsafe(CODE_LENGTH_BYTES)


async def create_invite(
    session: AsyncSession, created_by: int, expires_in_days: int = DEFAULT_EXPIRY_DAYS
) -> Invite:
    invite = Invite(
        code=new_invite_code(),
        created_by=created_by,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def get_invite_by_code(session: AsyncSession, code: str) -> Invite | None:
    return await session.scalar(select(Invite).where(Invite.code == code))


async def claim_invite(session: AsyncSession, code: str) -> Invite:
    """Row-locked claim of a live invite. Raises InviteError otherwise."""
    invite = await session.scalar(select(Invite).where(Invite.code == code).with_for_update())
    if invite is None:
        raise InviteError("invalid")
    if invite.used_by is not None:
        raise InviteError("used")
    if invite.expires_at <= datetime.now(UTC):
        raise InviteError("expired")
    return invite


async def redeem_invite(
    session: AsyncSession, code: str, name: str, email: str, password: str
) -> tuple[User, AuthCredential, Invite]:
    """Create the friend account for a valid invite and mark it used.

    Same-transaction guarantee: the invite claim, the user row, and the
    credential commit together — a crash mid-redemption leaves the invite
    unused rather than half-consumed.
    """
    email = email.strip().lower()

    existing_cred = await session.scalar(
        select(AuthCredential).where(AuthCredential.email == email)
    )
    if existing_cred is not None:
        raise InviteError("email_taken")

    invite = await claim_invite(session, code)

    user = User(name=name.strip())
    session.add(user)
    await session.flush()  # assign user.id

    cred = AuthCredential(
        user_id=user.id,
        email=email,
        password_hash=hash_password(password),
        role="friend",
        ai_access_tier="cheap_only",  # §15: friends start cheap; owner can raise (§18)
        share_segments=False,
    )
    session.add(cred)

    invite.used_by = user.id
    await session.commit()
    await session.refresh(user)
    return user, cred, invite


async def revoke_invite(session: AsyncSession, invite_id: int, owner_id: int) -> bool:
    """Delete an unused invite. Used invites are history, not state — refuse."""
    invite = await session.get(Invite, invite_id)
    if invite is None:
        return False
    if invite.used_by is not None:
        raise InviteError("used")
    await session.delete(invite)
    await session.commit()
    return True


def is_expired(invite: Invite) -> bool:
    return invite.expires_at <= datetime.now(UTC)
