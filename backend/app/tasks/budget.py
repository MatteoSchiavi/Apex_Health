"""Daily budget check (MASTER_SPEC §8.6, §19 "Daily budget check 1×/day").

Sums each account's estimated token_usage cost for the UTC day and — when a
user crosses DAILY_TOKEN_BUDGET_USD — fires a `budget_warning` alert
(severity info: informational, NOT a hard stop) and pushes it to that user's
linked chat(s). One warning per user per UTC day (§17-style idempotency: the
re-run inside the same day finds the existing row and stays quiet).

Scheduling: beat fires once a day at 23:45 UTC — near the close of the UTC
accounting day the sums use. Judgment call documented in the README: §19
fixes the cadence (1×/day) but not the wall clock, and the sums are defined
on UTC days, so the check runs as late in that day as practical.
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import sessionmaker
from app.models.alert import Alert
from app.models.user import User
from app.queries.usage import day_spend_by_user
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.budget")


async def _daily_check(now_iso: str | None = None) -> dict:
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    budget = get_settings().daily_token_budget_usd
    if budget <= 0:
        return {"status": "disabled"}

    telegram = None
    if get_settings().telegram_bot_token:
        from app.connectors.telegram.client import LiveTelegramClient

        telegram = LiveTelegramClient(get_settings().telegram_bot_token)

    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    fired: list[dict] = []
    created_alerts: list[Alert] = []

    async with sessionmaker() as session:
        spends = await day_spend_by_user(session, now)
        for user_id, spend in sorted(spends.items()):
            if spend <= Decimal(str(budget)):
                continue
            # one budget_warning per user per UTC day
            existing = await session.scalar(
                select(Alert).where(
                    Alert.user_id == user_id,
                    Alert.type == "budget_warning",
                    Alert.triggered_at >= day_start,
                )
            )
            if existing is not None:
                continue
            user = await session.get(User, user_id)
            name = getattr(user, "name", None) or f"user {user_id}"
            alert = Alert(
                user_id=user_id,
                type="budget_warning",
                severity="info",
                message=(
                    f"Estimated AI spend today: ${spend:.2f} — daily budget ${budget:.2f} "
                    f"(informational; nothing was stopped)."
                ),
            )
            session.add(alert)
            created_alerts.append(alert)
            fired.append({"user": name, "spend": f"${spend:.2f}"})
        await session.commit()

    if telegram is not None and created_alerts:
        from app.connectors.telegram.alerts import push_alert

        for alert in created_alerts:
            await push_alert(sessionmaker, telegram, alert)

    return {"checked_users": len(spends), "warnings_fired": fired}


@celery_app.task(name="budget.daily_check")
def daily_budget_check(now_iso: str | None = None) -> dict:
    """§19: 1×/day — 23:45 UTC, near the close of the accounting day."""
    return asyncio.run(_daily_check(now_iso))
