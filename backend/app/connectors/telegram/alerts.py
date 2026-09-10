"""Alert push (§10.3, §21): alerts are DB-backed, user-facing records —
pushed to the linked user's chat as they trigger. Alert-creating code paths
(Phase 4 onward) commit the row, then call push_alert; the bot never scans
for alerts on a schedule (§19 has no alert-scan job)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.alert import Alert
from app.models.telegram import TelegramLink

logger = logging.getLogger("connectors.telegram.alerts")

SEVERITY_ICON = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


async def push_alert(sessionmaker: async_sessionmaker, telegram, alert: Alert) -> int:
    """Send one committed alert to every chat linked to its user.
    Returns the number of chats notified (0 if the user has none)."""
    async with sessionmaker() as session:
        links = (
            await session.scalars(
                select(TelegramLink).where(TelegramLink.user_id == alert.user_id)
            )
        ).all()
    text = f"{SEVERITY_ICON.get(alert.severity, '•')} Alert [{alert.type}] — {alert.message}"
    for link in links:
        await telegram.send_message(link.chat_id, text)
    if not links:
        logger.info("alert %s (%s) has no linked chat to receive it", alert.id, alert.type)
    return len(links)


async def notify_user(sessionmaker: async_sessionmaker, telegram, user_id: int, text: str) -> int:
    """Proactive plain message to all linked chats (e.g. forecast nudges)."""
    async with sessionmaker() as session:
        links = (
            await session.scalars(
                select(TelegramLink).where(TelegramLink.user_id == user_id)
            )
        ).all()
    for link in links:
        await telegram.send_message(link.chat_id, text)
    return len(links)
