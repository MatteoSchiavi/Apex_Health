"""Read functions over §6.4 tables (§8.2 shared query layer).

All reads go through mapped ORM models — lab_panels/gear were parameterized
SQL until Phase 4 mapped their models (same convention as models/user.py).
Labs/donation reads live in app/queries/labs.py.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, Discipline
from app.models.alert import Alert
from app.models.features import DailyFeature
from app.models.gear import Gear
from app.models.integration import Integration
from app.models.wellness import SleepSession


async def latest_daily_feature(session: AsyncSession, user_id: int) -> DailyFeature | None:
    row = await session.scalars(
        select(DailyFeature)
        .where(DailyFeature.user_id == user_id)
        .order_by(DailyFeature.date.desc())
        .limit(1)
    )
    return row.first()


async def recent_daily_features(session: AsyncSession, user_id: int, days: int = 7) -> list[DailyFeature]:
    rows = await session.scalars(
        select(DailyFeature)
        .where(DailyFeature.user_id == user_id)
        .order_by(DailyFeature.date.desc())
        .limit(days)
    )
    return list(rows)


async def integrations_overview(session: AsyncSession, user_id: int) -> list[dict]:
    rows = await session.scalars(
        select(Integration).where(Integration.user_id == user_id).order_by(Integration.provider)
    )
    return [
        {
            "provider": i.provider,
            "status": i.status,
            "last_synced_at": i.last_synced_at,
            "consecutive_failures": i.consecutive_failures,
        }
        for i in rows
    ]


async def open_alerts(session: AsyncSession, user_id: int) -> list[Alert]:
    rows = await session.scalars(
        select(Alert)
        .where(Alert.user_id == user_id, Alert.acknowledged.is_(False))
        .order_by(Alert.triggered_at.desc())
    )
    return list(rows)


async def gear_overview(session: AsyncSession, user_id: int, gear_id: int | None = None) -> list[dict]:
    """Usage vs service interval per gear item (§8.3 get_gear_status); a
    gear_id narrows to one item."""
    conditions = [Gear.user_id == user_id]
    if gear_id is not None:
        conditions.append(Gear.id == gear_id)
    rows = (
        await session.scalars(
            select(Gear).where(*conditions).order_by(Gear.active.desc(), Gear.name)
        )
    ).all()
    items = []
    for g in rows:
        usage_pct = None
        if g.service_interval_hours:
            usage_pct = float(g.hours_since_service or 0) / float(g.service_interval_hours) * 100
        if g.service_interval_km:
            km_pct = float(g.km_since_service or 0) / float(g.service_interval_km) * 100
            usage_pct = max(usage_pct or 0, km_pct)
        items.append(
            {
                "gear_id": g.id,
                "name": g.name,
                "gear_type": g.gear_type,
                "active": g.active,
                "hours_since_service": float(g.hours_since_service or 0),
                "km_since_service": float(g.km_since_service or 0),
                "service_interval_hours": (
                    float(g.service_interval_hours) if g.service_interval_hours else None
                ),
                "service_interval_km": (
                    float(g.service_interval_km) if g.service_interval_km else None
                ),
                "usage_pct": usage_pct,
            }
        )
    return items


async def activities_on_local_date(session: AsyncSession, user_id: int, day: date) -> list[dict]:
    rows = (
        await session.execute(
            select(Activity, Discipline.name)
            .join(Discipline, Activity.discipline_id == Discipline.id)
            .where(Activity.user_id == user_id, Activity.local_date == day)
            .order_by(Activity.start_time)
        )
    ).all()
    return [
        {
            "discipline": name,
            "duration_s": a.duration_s,
            "distance_m": float(a.distance_m) if a.distance_m is not None else None,
            "training_load": float(a.training_load) if a.training_load is not None else None,
        }
        for a, name in rows
    ]


async def sleep_on_local_date(session: AsyncSession, user_id: int, day: date) -> dict | None:
    row = await session.scalars(
        select(SleepSession)
        .where(SleepSession.user_id == user_id, SleepSession.local_date == day)
        .order_by(SleepSession.end_time.desc())
        .limit(1)
    )
    s = row.first()
    if s is None:
        return None
    return {
        "total_sleep_s": s.total_sleep_s,
        "sleep_score": float(s.sleep_score) if s.sleep_score is not None else None,
    }
