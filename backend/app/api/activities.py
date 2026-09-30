"""Activities API for the web UI: list, detail, streams.

- GET /activities        — paginated list with discipline + source joins
- GET /activities/{id}   — detail incl. FIT-derived laps (migration 0007)
- GET /activities/{id}/streams — column arrays (t[] + one array per type)

Every query is scoped to the session user — the UI is multi-user and the
id in the URL never bypasses ownership (§22 isolation law).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import (
    Activity,
    ActivityLap,
    ActivitySourceLink,
    ActivityStream,
)
from app.models.user import User
from app.schemas.ui import ActivityDetailOut, ActivityListOut, ActivityOut, StreamOut

router = APIRouter(prefix="/activities", tags=["activities"])

async def _sources_map(session: AsyncSession, activity_ids: list[int]) -> dict[int, list[str]]:
    if not activity_ids:
        return {}
    rows = await session.execute(
        select(ActivitySourceLink.activity_id, ActivitySourceLink.source).where(
            ActivitySourceLink.activity_id.in_(activity_ids)
        )
    )
    out: dict[int, list[str]] = {}
    for act_id, source in rows:
        out.setdefault(act_id, []).append(source)
    return out


def _fl(value) -> float | None:
    return float(value) if value is not None else None


async def _activity_out(session: AsyncSession, a: Activity, discipline_name: str | None) -> ActivityOut:
    return ActivityOut(
        id=a.id,
        start_time=a.start_time,
        local_date=a.local_date,
        discipline=discipline_name,
        duration_s=a.duration_s,
        distance_m=_fl(a.distance_m),
        elevation_gain_m=_fl(a.elevation_gain_m),
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        avg_power=_fl(a.avg_power),
        np_power=_fl(a.np_power),
        calories=a.calories,
        training_load=_fl(a.training_load),
        data_completeness=a.data_completeness,
        sources=[],
    )


async def _disciplines_map(session: AsyncSession) -> dict[int, str]:
    from app.models.activity import Discipline

    rows = await session.execute(select(Discipline.id, Discipline.name))
    return dict(rows.all())


@router.get("", response_model=ActivityListOut)
async def list_activities(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    start: date | None = None,
    end: date | None = None,
) -> ActivityListOut:
    conditions = [Activity.user_id == user.id]
    if start:
        conditions.append(Activity.local_date >= start)
    if end:
        conditions.append(Activity.local_date <= end)

    total = (
        await session.scalar(
            select(func.count()).select_from(Activity).where(*conditions)
        )
    ) or 0

    rows = (
        await session.scalars(
            select(Activity)
            .where(*conditions)
            .order_by(Activity.start_time.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    disciplines = await _disciplines_map(session)
    sources = await _sources_map(session, [a.id for a in rows])

    items = []
    for a in rows:
        out = await _activity_out(session, a, disciplines.get(a.discipline_id))
        out.sources = sources.get(a.id, [])
        items.append(out)

    return ActivityListOut(items=items, total=total, limit=limit, offset=offset)


async def _owned_activity(session: AsyncSession, user: User, activity_id: int) -> Activity:
    activity = await session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "activity not found")
    return activity


@router.get("/{activity_id}", response_model=ActivityDetailOut)
async def activity_detail(
    activity_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ActivityDetailOut:
    a = await _owned_activity(session, user, activity_id)
    disciplines = await _disciplines_map(session)
    sources = await _sources_map(session, [a.id])
    laps = (
        await session.scalars(
            select(ActivityLap)
            .where(ActivityLap.activity_id == a.id)
            .order_by(ActivityLap.lap_index)
        )
    ).all()
    counts = await session.execute(
        select(
            func.count(ActivityStream.hr),
            func.count(ActivityStream.power),
            func.count(ActivityStream.cadence),
            func.count(ActivityStream.speed),
            func.count(ActivityStream.altitude),
            func.count(ActivityStream.lat),
            func.count(ActivityStream.lon),
        ).where(ActivityStream.activity_id == a.id)
    )
    c = counts.one()
    types = [
        name
        for name, n in (
            ("hr", c[0]), ("power", c[1]), ("cadence", c[2]),
            ("speed", c[3]), ("altitude", c[4]), ("lat", c[5]),
        )
        if n > 0
    ]
    has = bool(types) or c[6] > 0

    from app.models.gear import Gear, ActivityGearLink  # local import: avoids cycles

    gear_rows = (
        await session.execute(
            select(Gear)
            .join(ActivityGearLink, ActivityGearLink.gear_id == Gear.id)
            .where(ActivityGearLink.activity_id == a.id)
        )
    ).scalars().all()

    return ActivityDetailOut(
        id=a.id,
        start_time=a.start_time,
        local_date=a.local_date,
        discipline=disciplines.get(a.discipline_id),
        duration_s=a.duration_s,
        distance_m=_fl(a.distance_m),
        elevation_gain_m=_fl(a.elevation_gain_m),
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        avg_power=_fl(a.avg_power),
        np_power=_fl(a.np_power),
        calories=a.calories,
        training_load=_fl(a.training_load),
        data_completeness=a.data_completeness,
        sources=sources.get(a.id, []),
        has_streams=has,
        stream_types=types,
        laps=[
            {
                "lap_index": l.lap_index,
                "start_time": l.start_time.isoformat() if l.start_time else None,
                "duration_s": l.duration_s,
                "distance_m": _fl(l.distance_m),
                "avg_hr": l.avg_hr,
                "max_hr": l.max_hr,
                "avg_power": _fl(l.avg_power),
                "calories": l.calories,
                "extras": l.extras,
            }
            for l in laps
        ],
        weather=a.weather_snapshot,
        source_metrics=a.source_metrics,
        gear=[
            {"id": g.id, "name": g.name, "type": g.gear_type} for g in gear_rows
        ],
    )


@router.get("/{activity_id}/streams", response_model=StreamOut)
async def activity_streams(
    activity_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    max_points: int = Query(default=1200, ge=100, le=5000),
) -> StreamOut:
    """Downsampled stream series as aligned column arrays.

    LTTB-lite: uniform stride decimation keeps the shape honest at UI
    resolution without shipping tens of thousands of points.
    """
    a = await _owned_activity(session, user, activity_id)
    rows = (
        await session.execute(
            select(ActivityStream)
            .where(ActivityStream.activity_id == a.id)
            .order_by(ActivityStream.t_offset_s)
        )
    ).scalars().all()
    if not rows:
        return StreamOut(activity_id=a.id, t=[], columns={})

    stride = max(1, len(rows) // max_points)
    picked = rows[::stride]
    if picked[-1].t_offset_s != rows[-1].t_offset_s:
        picked.append(rows[-1])

    def series(pick, cast=float) -> list:
        return [cast(pick(r)) if pick(r) is not None else None for r in picked]

    return StreamOut(
        activity_id=a.id,
        t=[r.t_offset_s for r in picked],
        columns={
            "hr": series(lambda r: r.hr, int),
            "power": series(lambda r: _fl(r.power)),
            "cadence": series(lambda r: _fl(r.cadence)),
            "speed": series(lambda r: _fl(r.speed)),
            "altitude": series(lambda r: _fl(r.altitude)),
            "lat": series(lambda r: _fl(r.lat)),
            "lon": series(lambda r: _fl(r.lon)),
        },
    )
