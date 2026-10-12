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
    """Compatibility entry point for a confirmed persistent connector failure."""
    await connector_outcome_notification(provider, user_id, "failed", failure_count=3)


async def connector_outcome_notification(provider: str, user_id: int, state: str,
                                         *, error_class: str | None = None, failure_count: int = 0) -> None:
    """One notification per actionable episode, with recovery only after an alert.

    Account feed details contain only bounded operational bookkeeping. The
    transaction lock serializes retries and overlapping scheduled jobs.
    """
    import hashlib
    import re
    from sqlalchemy import text
    from app.core.db import sessionmaker
    from app.models.lab import FeedState
    from app.models.integration import Integration
    provider = provider if re.fullmatch(r'[a-z]{1,20}', provider) else 'connector'
    if state not in {"successful", "partial", "failed"}:
        return
    if state == "failed" and error_class not in {"authentication", "permission"} and failure_count < 3:
        return
    alert_state = ("auth_required" if error_class in {"authentication", "permission"} else "failed") if state == "failed" else state
    lock_id = int.from_bytes(hashlib.sha256(f"sync-alert:{provider}:{int(user_id)}".encode()).digest()[:8], 'big', signed=True)
    async with sessionmaker() as session:
        await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {"key": lock_id})
        feed = await session.scalar(select(FeedState).where(
            FeedState.user_id == user_id, FeedState.provider == provider, FeedState.feed == "account_sync"))
        if feed is None:
            exists = await session.scalar(select(Integration.id).where(
                Integration.user_id == user_id, Integration.provider == provider))
            if exists is None:
                return
            feed = FeedState(user_id=user_id, provider=provider, feed="account_sync",
                             availability="fetch_failed" if state == "failed" else "partial" if state == "partial" else "available",
                             details={}, cursor={})
            session.add(feed)
        details = dict(feed.details or {})
        previous = details.get("alert_state")
        if alert_state == "successful":
            if previous not in {"failed", "auth_required", "partial"}:
                return
            kind = "connector_recovery"
            message = f'Apex Health connector recovered: {provider} · user #{int(user_id)}. Synchronization completed successfully.'
            details.pop("alert_state", None)
        else:
            if previous == alert_state:
                return
            if alert_state == "partial":
                kind = "connector_warning"
                message = f'Apex Health partial synchronization: {provider} · user #{int(user_id)}. Imported data is available; some streams or records need another attempt.'
            elif alert_state == "auth_required":
                kind = "connector_error"
                message = f'Apex Health connector authentication or permission required: {provider} · user #{int(user_id)}. Reconnect or review provider access.'
            else:
                kind = "connector_error"
                message = f'Apex Health persistent connector failure: {provider} · user #{int(user_id)}. Review owner operational logs.'
            details["alert_state"] = alert_state
        feed.details = details
        enqueue(session, kind, message)
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
