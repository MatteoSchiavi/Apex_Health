"""One-way owner Bot API sender. No chat handlers, commands, or SDK."""
from datetime import UTC, datetime, timedelta
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.admin import OwnerNotification

def configured() -> bool:
    s = get_settings()
    return bool(s.owner_telegram_bot_token and s.owner_telegram_chat_id)

def enqueue(session: AsyncSession, kind: str, message: str, feedback_id: int | None = None) -> OwnerNotification:
    row = OwnerNotification(kind=kind, message=message[:3500], feedback_id=feedback_id)
    session.add(row)
    return row

async def dispatch(session: AsyncSession, limit: int = 20, notification_id: int | None = None) -> int:
    if not configured():
        return 0
    s = get_settings()
    query = select(OwnerNotification).where(OwnerNotification.delivered_at.is_(None), OwnerNotification.next_attempt_at <= datetime.now(UTC))
    if notification_id is not None:
        query = query.where(OwnerNotification.id == notification_id)
    rows = (await session.scalars(query.order_by(OwnerNotification.id).limit(limit).with_for_update(skip_locked=True))).all()
    delivered = 0
    # Never log URL, response, exceptions, token, or feedback content.
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0), follow_redirects=False) as client:
        for row in rows:
            row.attempts += 1
            try:
                response = await client.post(f"https://api.telegram.org/bot{s.owner_telegram_bot_token}/sendMessage", json={"chat_id": s.owner_telegram_chat_id, "text": row.message, "disable_web_page_preview": True})
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or body.get("ok") is not True:
                    raise ValueError("delivery rejected")
                row.delivered_at = datetime.now(UTC)
                delivered += 1
            except (httpx.HTTPError, ValueError):
                row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=min(86400, 60 * 2 ** min(max(row.attempts - 1, 0), 11)))
    await session.commit()
    return delivered

async def critical_connector_error(provider: str, user_id: int) -> None:
    """Deduplicate one operational alert per provider/account/hour; no error body."""
    import re
    from sqlalchemy import text
    from app.core.db import sessionmaker
    provider = provider if re.fullmatch(r'[a-z]{1,20}', provider) else 'connector'
    message = f'Apex Health critical connector failure: {provider} · user #{int(user_id)}. Review owner operational logs.'
    async with sessionmaker() as session:
        await session.execute(text('SELECT pg_advisory_xact_lock(73150422)'))
        exists = await session.scalar(select(OwnerNotification.id).where(OwnerNotification.kind=='connector_error',OwnerNotification.message==message,OwnerNotification.created_at > datetime.now(UTC)-timedelta(hours=1)).limit(1))
        if not exists:
            enqueue(session,'connector_error',message)
            await session.commit()


async def best_effort_dispatch(session: AsyncSession, notification_id: int) -> bool:
    """After a durable commit, notification outages must not fail the user action."""
    try:
        return bool(await dispatch(session, limit=1, notification_id=notification_id))
    except Exception:
        import logging
        logging.getLogger('owner.notifications').warning('Notification delivery deferred')
        try:
            await session.rollback()
        except Exception:
            pass
        return False
