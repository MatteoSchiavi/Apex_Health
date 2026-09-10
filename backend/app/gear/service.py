"""Gear tracking (MASTER_SPEC §13).

- Auto-link: an ingested activity inherits the user's default gear for its
  discipline (discipline_gear_defaults); Telegram voice can override later.
- Nightly accumulation (§19, right after the feature engine): usage since
  the last gear_service_logs.performed_at is RECOMPUTED from linked
  activities into hours_since_service / km_since_service — a pure recompute,
  so re-running never double-counts (§17).
- Crossing the configured interval fires ONE gear_service_due alert per gear
  (deduped on unacknowledged alerts for the same gear); logging a service
  resets the counters. Alerts are DB rows — the caller commits, then pushes
  (§21 contract in app/connectors/telegram/alerts.py).
"""

import logging
from datetime import datetime

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.alert import Alert
from app.models.gear import (
    ActivityGearLink,
    DisciplineGearDefault,
    Gear,
    GearServiceLog,
)

logger = logging.getLogger("gear.service")


def _alert_prefix(gear_id: int) -> str:
    """Stable machine-ish prefix so dedup can target exactly this gear."""
    return f"Gear #{gear_id} "


async def auto_link_gear(
    session: AsyncSession, *, user_id: int, discipline_id: int, activity_id: int
) -> int:
    """Link the discipline's default gear to a freshly ingested activity.
    Idempotent: existing (activity_id, gear_id) rows are left alone (§17).
    Returns the number of links added."""
    defaults = (
        await session.scalars(
            select(DisciplineGearDefault.gear_id).where(
                DisciplineGearDefault.user_id == user_id,
                DisciplineGearDefault.discipline_id == discipline_id,
            )
        )
    ).all()
    added = 0
    for gear_id in defaults:
        has_link = await session.scalar(
            select(
                exists().where(
                    ActivityGearLink.activity_id == activity_id,
                    ActivityGearLink.gear_id == gear_id,
                )
            )
        )
        if not has_link:
            session.add(ActivityGearLink(activity_id=activity_id, gear_id=gear_id))
            added += 1
    if added:
        logger.debug(
            "auto-linked %d gear item(s) to activity %s", added, activity_id
        )
    return added


async def log_gear_service(
    session: AsyncSession,
    *,
    gear: Gear,
    service_type: str,
    performed_at: datetime,
    notes: str | None = None,
) -> GearServiceLog:
    """Record a service AND reset the usage counters (§13: logging a new
    service resets them). Counters stay 0 on the next accumulation because
    usage is only summed past the last performed_at.

    Any OPEN gear_service_due alert for this gear is acknowledged: the
    service resolved it. Without this, a still-unacknowledged old alert
    would silence the NEXT legitimate crossing (dedup is scoped to open
    alerts by design)."""
    log = GearServiceLog(
        gear_id=gear.id, service_type=service_type, performed_at=performed_at, notes=notes
    )
    session.add(log)
    gear.hours_since_service = 0
    gear.km_since_service = 0

    open_alerts = (
        await session.scalars(
            select(Alert).where(
                Alert.user_id == gear.user_id,
                Alert.type == "gear_service_due",
                Alert.acknowledged.is_(False),
                Alert.message.startswith(_alert_prefix(gear.id)),
            )
        )
    ).all()
    for alert in open_alerts:
        alert.acknowledged = True
    return log


async def _gear_usage_since_last_service(
    session: AsyncSession, gear: Gear
) -> tuple[float, float]:
    """(hours, km) accumulated on this gear since its last service log —
    recompute from activity rows, never an increment (§17)."""
    last_performed = await session.scalar(
        select(func.max(GearServiceLog.performed_at)).where(
            GearServiceLog.gear_id == gear.id
        )
    )
    conditions = [ActivityGearLink.gear_id == gear.id]
    if last_performed is not None:
        conditions.append(Activity.start_time > last_performed)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Activity.duration_s), 0),
                func.coalesce(func.sum(Activity.distance_m), 0),
            )
            .select_from(ActivityGearLink)
            .join(Activity, Activity.id == ActivityGearLink.activity_id)
            .where(and_(*conditions))
        )
    ).one()
    return float(row[0]) / 3600.0, float(row[1]) / 1000.0


async def _has_open_alert(session: AsyncSession, gear: Gear) -> bool:
    """True while an unacknowledged gear_service_due alert for THIS gear is
    open — the dedup that makes nightly re-runs quiet (§17)."""
    prefix = _alert_prefix(gear.id)
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Alert.user_id == gear.user_id,
                    Alert.type == "gear_service_due",
                    Alert.acknowledged.is_(False),
                    Alert.message.startswith(prefix),
                )
            )
        )
    )


async def accumulate_gear_usage(
    session: AsyncSession, gear: Gear
) -> Alert | None:
    """Recompute one gear's usage counters; fire a new gear_service_due
    alert when an interval is crossed and none is open. The alert row is
    added to the session — caller commits, then pushes (§21)."""
    if not gear.active:
        return None
    hours, km = await _gear_usage_since_last_service(session, gear)
    gear.hours_since_service = hours
    gear.km_since_service = km

    if await _has_open_alert(session, gear):
        return None

    crossed = []
    if gear.service_interval_hours is not None and hours >= float(gear.service_interval_hours):
        crossed.append(f"{hours:.1f} h since last service (interval {float(gear.service_interval_hours):g} h)")
    if gear.service_interval_km is not None and km >= float(gear.service_interval_km):
        crossed.append(f"{km:.1f} km since last service (interval {float(gear.service_interval_km):g} km)")
    if not crossed:
        return None

    alert = Alert(
        user_id=gear.user_id,
        type="gear_service_due",
        severity="warning",
        message=f"{_alert_prefix(gear.id)}'{gear.name}' is due for service — " + " and ".join(crossed),
    )
    session.add(alert)
    return alert
