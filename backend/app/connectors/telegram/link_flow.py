"""Link flow (§10.3): bot-initiated one-time codes, confirmed by the owner.

With no web Settings page this round, linking is intentionally minimal: an
unlinked chat sends /link, the bot replies with (and logs) a one-time code,
and the owner completes the bind with /confirm <code> from the same chat.
Only the owner account exists as a user until friend onboarding resumes
(§15), so a confirmed chat is always linked to the owner account.
Codes live in Redis with a 15-minute TTL and are single-use.
"""

import logging
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram import TelegramLink
from app.models.user import AuthCredential

logger = logging.getLogger("connectors.telegram.link_flow")

LINK_CODE_TTL_S = 900  # 15 minutes
_LINK_CODE_KEY = "tg:link_code:{code}"


async def get_linked_user_id(session: AsyncSession, chat_id: int) -> int | None:
    """Resolve chat_id -> linked user id, or None if the chat is unlinked."""
    row = await session.scalars(
        select(TelegramLink.user_id).where(TelegramLink.chat_id == chat_id)
    )
    return row.first()


async def get_owner_user_id(session: AsyncSession) -> int | None:
    """The owner account every link binds to until friends exist (§15)."""
    row = await session.scalars(
        select(AuthCredential.user_id).where(AuthCredential.role == "owner")
    )
    return row.first()


async def is_chat_linked(session: AsyncSession, chat_id: int) -> bool:
    return (await get_linked_user_id(session, chat_id)) is not None


async def issue_link_code(session: AsyncSession, redis, chat_id: int) -> str | None:
    """Create a one-time code bound to this chat. None if no owner exists."""
    owner_id = await get_owner_user_id(session)
    if owner_id is None:
        return None
    code = secrets.token_hex(4).upper()  # 8 chars, unambiguous hex
    await redis.set(_LINK_CODE_KEY.format(code=code), chat_id, ex=LINK_CODE_TTL_S)
    # §10.3: the code is also printed to the server log so the owner can
    # verify it independently of the Telegram message.
    logger.info("link code %s issued for chat %s (expires in %ss)", code, chat_id, LINK_CODE_TTL_S)
    return code


async def confirm_link_code(
    session: AsyncSession, redis, chat_id: int, code: str
) -> tuple[bool, str]:
    """Bind chat_id -> owner user. Returns (ok, message_key)."""
    key = _LINK_CODE_KEY.format(code=code.strip().upper())
    stored_chat_raw = await redis.get(key)
    if stored_chat_raw is None:
        return False, "unknown_or_expired"
    if int(stored_chat_raw) != chat_id:
        # A code is only valid in the chat that requested it.
        return False, "wrong_chat"
    owner_id = await get_owner_user_id(session)
    if owner_id is None:
        return False, "no_owner"
    existing = await get_linked_user_id(session, chat_id)
    if existing is not None:
        await redis.delete(key)
        return True, "already_linked"
    session.add(TelegramLink(user_id=owner_id, chat_id=chat_id))
    await session.commit()
    await redis.delete(key)  # single-use
    logger.info("chat %s linked to user %s", chat_id, owner_id)
    return True, "linked"


def new_correlation_id() -> str:
    """Short id for log correlation across a handler + task hand-off."""
    return uuid.uuid4().hex[:8]
