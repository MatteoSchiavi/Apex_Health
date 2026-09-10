"""Weather sync orchestration (§14, §19, §17).

Two operations, both driven by the same 6-hourly beat task:

- refresh_forecasts — one forecast-API call for the configured home
  coordinates; raw-first (§17), then the payload's daily rows upsert
  forecast_cache on (lat, lon, date). Idempotent: re-running rewrites the
  same rows.

- enrich_activities — §14 "activities.weather_snapshot populated at
  ingestion". Activities ingest through the Garmin/Technogym connectors;
  this pass is the weather connector's half of the pipeline: every activity
  with weather_snapshot IS NULL gets it filled — coordinates from its first
  positioned stream sample, falling back to the configured home coordinates
  (§14's judgment call, documented: activities without GPS data are weathered
  at home). Dates older than the archive lag go to the archive API; recent
  ones ride the forecast API's past_days window. Only NULLs are ever
  written — a snapshot already present is never overwritten, so the pass is
  idempotent and re-runs are free.

No integrations row: Open-Meteo is keyless (§2/§14) — there are no
credentials to store and no per-user account to escalate (§21's counter is
for authenticated sources; failures here are logged and retried next tick).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.weather import fetch, normalize
from app.connectors.weather.client import ARCHIVE_LAG_DAYS, OpenMeteoClient, WeatherError
from app.models.activity import Activity, ActivityStream
from app.models.user import User

logger = logging.getLogger("connectors.weather.sync")


@dataclass
class WeatherSyncReport:
    forecast_days_cached: int = 0
    raw_rows_stored: int = 0
    activities_enriched: int = 0
    activities_skipped_no_weather: int = 0
    notes: list[str] = field(default_factory=list)


async def refresh_forecasts(
    session: AsyncSession,
    client: OpenMeteoClient,
    *,
    user_id: int,
    lat: float,
    lon: float,
    days: int,
    tz_name: str,
    now: datetime | None = None,
) -> WeatherSyncReport:
    """Fetch (raw-first) + normalize the forecast for one location (§19:
    forecast refresh upserts forecast_cache)."""
    now = now or datetime.now(UTC)
    report = WeatherSyncReport()
    payload = await client.forecast(
        lat,
        lon,
        forecast_days=days,
        timezone=tz_name,
    )
    await fetch.store_raw(session, user_id, fetch.PAYLOAD_FORECAST, payload, fetched_at=now)
    report.raw_rows_stored += 1
    report.forecast_days_cached += await normalize.upsert_forecast_cache(
        session, lat=lat, lon=lon, payload=payload, fetched_at=now
    )
    return report


async def _activity_coords_map(
    session: AsyncSession, activities: list[Activity]
) -> dict[int, tuple[float, float]]:
    """activity_id → coordinates from its first positioned stream sample."""
    coords: dict[int, tuple[float, float]] = {}
    ids = [a.id for a in activities]
    if not ids:
        return coords
    rows = await session.execute(
        select(
            ActivityStream.activity_id,
            ActivityStream.lat,
            ActivityStream.lon,
        )
        .where(
            ActivityStream.activity_id.in_(ids),
            ActivityStream.lat.is_not(None),
            ActivityStream.lon.is_not(None),
        )
        .order_by(ActivityStream.activity_id, ActivityStream.t_offset_s)
    )
    for activity_id, lat, lon in rows.all():
        if activity_id not in coords:
            coords[int(activity_id)] = (float(lat), float(lon))
    return coords


async def enrich_activities(
    session: AsyncSession,
    client: OpenMeteoClient,
    *,
    user_id: int,
    home_lat: float,
    home_lon: float,
    now: datetime | None = None,
) -> WeatherSyncReport:
    """Fill weather_snapshot for every not-yet-weathered activity of one user
    (§14). Only NULL columns are written; the pass never overwrites."""
    now = now or datetime.now(UTC)
    report = WeatherSyncReport()

    user = await session.get(User, user_id)
    tz = ZoneInfo(user.timezone) if user else ZoneInfo("UTC")

    pending = (
        (
            await session.scalars(
                select(Activity)
                .where(
                    Activity.user_id == user_id,
                    Activity.weather_snapshot.is_(None),
                )
                .order_by(Activity.start_time)
            )
        )
        .all()
    )
    if not pending:
        return report

    coords_map = await _activity_coords_map(session, pending)
    archive_cut = now.astimezone(UTC).date() - timedelta(days=ARCHIVE_LAG_DAYS)

    # Group by coordinates: {coords: {"archive": [dates], "recent": [dates],
    # "activities": [(activity, day, start_hour)]}}
    groups: dict[tuple[float, float], dict[str, Any]] = {}
    for activity in pending:
        coords = coords_map.get(activity.id, (home_lat, home_lon))
        if coords[0] == 0.0 and coords[1] == 0.0:
            report.activities_skipped_no_weather += 1
            report.notes.append(
                f"activity {activity.id}: no stream coordinates and no home "
                "coordinates configured (WEATHER_HOME_LAT/LON) — skipped"
            )
            continue
        day = activity.local_date
        start_hour = activity.start_time.astimezone(tz).hour
        bucket = groups.setdefault(
            coords, {"archive": set(), "recent": set(), "items": []}
        )
        (bucket["archive"] if day < archive_cut else bucket["recent"]).add(day)
        bucket["items"].append((activity, day, start_hour))

    for (lat, lon), bucket in groups.items():
        payloads: dict[date, dict[str, Any]] = {}

        if bucket["archive"]:
            start = min(bucket["archive"])
            end = max(bucket["archive"])
            payload = await client.archive(
                lat,
                lon,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                timezone=str(tz),
            )
            await fetch.store_raw(
                session,
                user_id,
                fetch.PAYLOAD_ARCHIVE,
                payload,
                fetched_at=now,
            )
            report.raw_rows_stored += 1
            for row in normalize.daily_rows(payload):
                if row["date"] in bucket["archive"]:
                    payloads[row["date"]] = payload

        if bucket["recent"]:
            today = now.astimezone(UTC).date()
            past_days = min(92, (today - min(bucket["recent"])).days + 1)
            payload = await client.forecast(
                lat,
                lon,
                past_days=past_days,
                forecast_days=1,
                timezone=str(tz),
            )
            await fetch.store_raw(
                session,
                user_id,
                fetch.PAYLOAD_FORECAST,
                payload,
                fetched_at=now,
            )
            report.raw_rows_stored += 1
            for row in normalize.daily_rows(payload):
                if row["date"] in bucket["recent"]:
                    payloads[row["date"]] = payload

        for activity, day, start_hour in bucket["items"]:
            payload = payloads.get(day)
            if payload is None:
                report.notes.append(
                    f"activity {activity.id}: upstream returned no data for {day}"
                )
                continue
            snapshot = normalize.build_weather_snapshot(
                payload, day, start_hour=start_hour, fetched_at=now
            )
            if snapshot is not None:
                activity.weather_snapshot = snapshot
                report.activities_enriched += 1

    await session.flush()
    return report
