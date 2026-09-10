"""Weather normalization (§3 stage 2): raw Open-Meteo payloads → typed rows.

Two products:
- forecast payloads upsert `forecast_cache` (§6.4 DDL, UNIQUE (lat, lon, date))
  — the scheduled refresh is idempotent by construction (§17: re-running must
  not double-count).
- any payload can yield an `activities.weather_snapshot` dict (§14) for a
  given activity date / start hour.

The cache key uses the coordinates we ASKED for (stable across calls), not
the grid-snapped values Open-Meteo echoes back — echoed values drift by a
grid cell between refreshes and would quietly multiply near-duplicate rows.
The echoed coordinates are kept inside the payload for transparency.
"""

import logging
from datetime import date, datetime, timezone as tz_module
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather import ForecastCache

logger = logging.getLogger("connectors.weather.normalize")

SNAPSHOT_SOURCE = "open-meteo"


class WeatherNormalizeError(Exception):
    """A payload the normalizer cannot use — stays unprocessed (§3)."""


def _at(series: dict[str, Any] | None, key: str, i: int) -> Any:
    """Safe i-th element of an upstream parallel array (None when absent)."""
    if not series:
        return None
    values = series.get(key)
    if not isinstance(values, list) or i >= len(values):
        return None
    return values[i]


def daily_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Open-Meteo's parallel-arrays response → one dict per day. Raises on a
    payload with no daily block (an error response the client should have
    caught, or an upstream shape change — both stay unprocessed, §3)."""
    daily = payload.get("daily")
    if not isinstance(daily, dict) or not daily.get("time"):
        raise WeatherNormalizeError(f"payload has no daily series: {payload!r}")
    rows: list[dict[str, Any]] = []
    for i, day in enumerate(daily["time"]):
        try:
            parsed_date = date.fromisoformat(str(day))
        except ValueError as exc:
            raise WeatherNormalizeError(f"unparsable daily date {day!r}") from exc
        rows.append(
            {
                "date": parsed_date,
                "temperature_2m_max": _at(daily, "temperature_2m_max", i),
                "temperature_2m_min": _at(daily, "temperature_2m_min", i),
                "temperature_2m_mean": _at(daily, "temperature_2m_mean", i),
                "precipitation_sum": _at(daily, "precipitation_sum", i),
                "precipitation_probability_max": _at(
                    daily, "precipitation_probability_max", i
                ),
                "wind_speed_10m_max": _at(daily, "wind_speed_10m_max", i),
                "weather_code": _at(daily, "weather_code", i),
            }
        )
    return rows


def payload_for_date(payload: dict[str, Any], day: date) -> dict[str, Any] | None:
    """The cache row payload: the upstream daily slice for one date, plus
    provenance. None when the payload doesn't cover that date."""
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    day_iso = day.isoformat()
    if day_iso not in times:
        return None
    i = times.index(day_iso)
    return {
        "source": SNAPSHOT_SOURCE,
        "upstream_latitude": payload.get("latitude"),
        "upstream_longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "elevation": payload.get("elevation"),
        "daily": {key: _at(daily, key, i) for key in daily if key != "time"},
        "time": day_iso,
    }


async def upsert_forecast_cache(
    session: AsyncSession,
    *,
    lat: float,
    lon: float,
    payload: dict[str, Any],
    fetched_at: datetime,
) -> int:
    """Upsert every daily row of a forecast payload into forecast_cache on
    (lat, lon, date). Returns the number of days upserted (not accumulated —
    re-running the same payload rewrites the same rows, §17)."""
    count = 0
    for row in daily_rows(payload):
        day_payload = payload_for_date(payload, row["date"])
        existing = await session.scalar(
            select(ForecastCache).where(
                ForecastCache.lat == Decimal(str(lat)),
                ForecastCache.lon == Decimal(str(lon)),
                ForecastCache.date == row["date"],
            )
        )
        if existing is not None:
            existing.payload = day_payload
            existing.fetched_at = fetched_at
        else:
            session.add(
                ForecastCache(
                    lat=Decimal(str(lat)),
                    lon=Decimal(str(lon)),
                    date=row["date"],
                    payload=day_payload,
                    fetched_at=fetched_at,
                )
            )
        count += 1
    await session.flush()
    return count


def build_weather_snapshot(
    payload: dict[str, Any],
    day: date,
    *,
    start_hour: int | None = None,
    fetched_at: datetime | None = None,
) -> dict[str, Any] | None:
    """§14: the activities.weather_snapshot value for one activity — the
    day's daily summary plus, when the hourly series and the activity's start
    hour are available, the conditions at that hour. None when the payload
    doesn't cover the activity's date (caller leaves the column NULL)."""
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    day_iso = day.isoformat()
    if day_iso not in times:
        return None
    i = times.index(day_iso)

    snapshot: dict[str, Any] = {
        "source": SNAPSHOT_SOURCE,
        "date": day_iso,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "temperature_2m_max": _at(daily, "temperature_2m_max", i),
        "temperature_2m_min": _at(daily, "temperature_2m_min", i),
        "temperature_2m_mean": _at(daily, "temperature_2m_mean", i),
        "precipitation_sum": _at(daily, "precipitation_sum", i),
        "precipitation_probability_max": _at(daily, "precipitation_probability_max", i),
        "wind_speed_10m_max": _at(daily, "wind_speed_10m_max", i),
        "weather_code": _at(daily, "weather_code", i),
        "fetched_at": (fetched_at or datetime.now(tz_module.UTC)).isoformat(),
    }

    if start_hour is not None:
        hourly = payload.get("hourly") or {}
        htimes = hourly.get("time") or []
        prefix = f"{day_iso}T"
        for j, stamp in enumerate(htimes):
            if str(stamp).startswith(prefix) and str(stamp)[11:13].isdigit():
                if int(str(stamp)[11:13]) == start_hour:
                    snapshot["at_start"] = {
                        "hour": start_hour,
                        "temperature_2m": _at(hourly, "temperature_2m", j),
                        "precipitation": _at(hourly, "precipitation", j),
                        "weather_code": _at(hourly, "weather_code", j),
                    }
                    break
    return snapshot
