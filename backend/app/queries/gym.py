"""Gym schedule reads/writes (Phase 10 v2 — the rethought watch app).

One query layer shared by every surface (§8.2 discipline): the REST
/schedule CRUD, the bot /gym commands, and the watch endpoints
GET /watch/day + /watch/week all call into this module.

Resolution rule (documented judgment call):
  for any date, a CONFIRMED/ACTIVE plan's planned_sessions for that date
  OVERRIDE the recurring weekly template — the AI plan and the standing
  routine compose instead of duplicating. Days with no planned session fall
  back to gym_schedule_slots for that weekday (0=Mon .. 6=Sun).
"""

from datetime import date, time, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.gym import GymScheduleSlot
from app.models.journal import JournalEntry
from app.models.medical import SupplementProtocol
from app.models.training import PlannedSession, TrainingPlan

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ------------------------------------------------------------- recurring CRUD


async def list_slots(session: AsyncSession, user_id: int) -> list[GymScheduleSlot]:
    rows = await session.scalars(
        select(GymScheduleSlot)
        .where(GymScheduleSlot.user_id == user_id)
        .order_by(GymScheduleSlot.weekday, GymScheduleSlot.start_time, GymScheduleSlot.id)
    )
    return list(rows)


async def create_slot(
    session: AsyncSession,
    user_id: int,
    weekday: int,
    start_time: time,
    title: str,
    description: str | None = None,
) -> GymScheduleSlot:
    slot = GymScheduleSlot(
        user_id=user_id,
        weekday=weekday,
        start_time=start_time,
        title=title,
        description=description,
        active=True,
    )
    session.add(slot)
    await session.flush()
    return slot


async def update_slot(
    session: AsyncSession,
    user_id: int,
    slot_id: int,
    **fields,
) -> GymScheduleSlot | None:
    """Patch allowed fields (weekday/start_time/title/description/active);
    a foreign slot id is just 'not found' (404 convention across the API)."""
    slot = await session.get(GymScheduleSlot, slot_id)
    if slot is None or slot.user_id != user_id:
        return None
    allowed = {"weekday", "start_time", "title", "description", "active"}
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(slot, key, value)
    slot.updated_at = slot.updated_at  # ORM touch; DB default owns it on insert
    await session.flush()
    return slot


async def delete_slot(session: AsyncSession, user_id: int, slot_id: int) -> bool:
    """Hard delete — a removed routine slot is gone. Pausing is PATCH
    active=false (kept distinct on purpose)."""
    result = await session.execute(
        delete(GymScheduleSlot).where(
            GymScheduleSlot.id == slot_id, GymScheduleSlot.user_id == user_id
        )
    )
    return result.rowcount > 0


# ----------------------------------------------------------------- resolution


def _slot_dict(slot: GymScheduleSlot, day: date | None) -> dict:
    return {
        "source": "schedule",
        "date": day.isoformat() if day is not None else None,
        "weekday": slot.weekday,
        "session_id": slot.id,
        "title": slot.title,
        "start_time": slot.start_time.strftime("%H:%M"),
        "description": slot.description,
        "session_type": None,
        "target_duration_min": None,
        "plan_id": None,
    }


def _planned_dict(plan: TrainingPlan, ps: PlannedSession) -> dict:
    return {
        "source": "plan",
        "date": ps.date.isoformat(),
        "weekday": ps.date.weekday(),
        "session_id": ps.id,
        "title": ps.session_type or "Planned session",
        "start_time": None,
        "description": ps.description,
        "session_type": ps.session_type,
        "target_duration_min": ps.target_duration_min,
        "plan_id": plan.id,
    }


async def resolve_range(
    session: AsyncSession,
    user_id: int,
    start_day: date,
    days: int = 1,
) -> list[dict]:
    """Day entries for [start_day, start_day + days): date-specific planned
    sessions win; otherwise the recurring template for that weekday. One
    query per source (not per day) — the watch week view stays cheap."""
    end_day = start_day + timedelta(days=days - 1)

    planned_rows = (
        await session.execute(
            select(TrainingPlan, PlannedSession)
            .join(PlannedSession, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(
                TrainingPlan.user_id == user_id,
                TrainingPlan.status.in_(("confirmed", "active")),
                PlannedSession.date >= start_day,
                PlannedSession.date <= end_day,
            )
            .order_by(PlannedSession.date, PlannedSession.id)
        )
    ).all()

    planned_by_date: dict[date, list[dict]] = {}
    for plan, ps in planned_rows:
        planned_by_date.setdefault(ps.date, []).append(_planned_dict(plan, ps))

    slots = await list_slots(session, user_id)
    slots_by_weekday: dict[int, list[dict]] = {}
    for slot in slots:
        if slot.active:
            slots_by_weekday.setdefault(slot.weekday, []).append(_slot_dict(slot, None))

    result = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        if day in planned_by_date:
            sessions = planned_by_date[day]
        else:
            sessions = []
            for entry in slots_by_weekday.get(day.weekday(), []):
                entry["date"] = day.isoformat()
                sessions.append(entry)
        result.append({"date": day.isoformat(), "weekday": day.weekday(), "sessions": sessions})
    return result


async def resolve_day(session: AsyncSession, user_id: int, day: date) -> list[dict]:
    return (await resolve_range(session, user_id, day, days=1))[0]["sessions"]


# ------------------------------------------------------- watch companion data


async def active_supplements(session: AsyncSession, user_id: int, day: date) -> list[dict]:
    """Protocols live on `day` (started on/before, not ended): name, dose and
    the raw schedule text — the watch lists them, it does not own reminders."""
    rows = (
        await session.scalars(
            select(SupplementProtocol)
            .where(
                SupplementProtocol.user_id == user_id,
                SupplementProtocol.active.is_(True),
            )
            .order_by(SupplementProtocol.supplement_name)
        )
    ).all()
    items = []
    for row in rows:
        started = row.start_date is None or row.start_date <= day
        not_ended = row.end_date is None or row.end_date >= day
        if started and not_ended:
            items.append(
                {
                    "name": row.supplement_name,
                    "dose": row.dose,
                    "schedule": row.schedule_cron,
                }
            )
    return items


async def open_alert_summaries(
    session: AsyncSession, user_id: int, limit: int = 3
) -> dict:
    """Unacknowledged alerts — count plus the newest few for the wrist (the
    watch is a glance surface, not the alert inbox; acking stays in
    Telegram/web)."""
    total = len(
        (
            await session.scalars(
                select(Alert).where(
                    Alert.user_id == user_id, Alert.acknowledged.is_(False)
                )
            )
        ).all()
    )
    rows = (
        await session.scalars(
            select(Alert)
            .where(Alert.user_id == user_id, Alert.acknowledged.is_(False))
            .order_by(Alert.triggered_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "count": total,
        "items": [
            {
                "severity": a.severity,
                "message": a.message,
                "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            }
            for a in rows
        ],
    }


async def journal_streak(session: AsyncSession, user_id: int, today: date) -> int:
    """Consecutive journal days ending today — or yesterday, when today's
    entry hasn't happened yet (a 23:00 journal habit must not read as 0 at
    09:00). Walks back day by day; journal use is sparse so this is cheap."""
    dates = set(
        await session.scalars(
            select(JournalEntry.date).where(JournalEntry.user_id == user_id)
        )
    )
    cursor = today if today in dates else today - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
