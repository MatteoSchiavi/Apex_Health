"""Nightly gear-accumulation task (§13, §19: "1×/day, right after feature
engine"). Celery beat dispatches hourly at :15 and the task computes only
for users whose local wall clock reads hour 3 — inside the same 03:00-03:59
local window as the feature engine (minute 0), guaranteeing it runs after
that day's feature pass in every timezone. The recompute is idempotent
(§17), so a DST fall-back double-run is harmless.

gear_service_due alerts are DB rows committed here; when TELEGRAM_BOT_TOKEN
is configured they are pushed to the linked chat(s) right after the commit
(§21 contract in app/connectors/telegram/alerts.py).
"""

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import sessionmaker
from app.gear.service import accumulate_gear_usage
from app.models.gear import Gear
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.gear")

NIGHTLY_LOCAL_HOUR = 3


def is_nightly_local_time(now: datetime, tz: ZoneInfo) -> bool:
    """True when `now` falls in the 03:00-03:59 local window for `tz` (§19)."""
    return now.astimezone(tz).hour == NIGHTLY_LOCAL_HOUR


async def _accumulate_all(now_iso: str | None = None) -> dict:
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    results: dict[str, dict] = {}
    telegram = None
    if get_settings().telegram_bot_token:
        from app.connectors.telegram.client import LiveTelegramClient

        telegram = LiveTelegramClient(get_settings().telegram_bot_token)

    async with sessionmaker() as session:
        users = (await session.scalars(select(User).order_by(User.id))).all()
        for user in users:
            tz = ZoneInfo(user.timezone)
            if not is_nightly_local_time(now, tz):
                continue
            fired = 0
            try:
                gears = (
                    await session.scalars(
                        select(Gear).where(Gear.user_id == user.id, Gear.active.is_(True))
                    )
                ).all()
                alerts = []
                for gear in gears:
                    alert = await accumulate_gear_usage(session, gear)
                    if alert is not None:
                        alerts.append(alert)
                await session.commit()
                fired = len(alerts)

                if telegram is not None:
                    from app.connectors.telegram.alerts import push_alert

                    for alert in alerts:
                        await push_alert(sessionmaker, telegram, alert)
                results[str(user.id)] = {
                    "gear_checked": len(gears),
                    "alerts_fired": fired,
                }
            except Exception:
                # §21: one user's failure must not starve the others.
                logger.exception("gear accumulation failed for user %s", user.id)
                results[str(user.id)] = {"status": "failed"}
    return results


@celery_app.task(name="gear.accumulate_all")
def accumulate_all_gear(now_iso: str | None = None) -> dict:
    return asyncio.run(_accumulate_all(now_iso))
