"""Weather reads (§8.2 — one implementation per read).

The /forecast bot command and the GET /weather/forecast endpoint both call
get_forecast, so "what's the forecast" has exactly one implementation. The
WMO code table lives here too — both presentation layers need readable
descriptions and must not drift.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weather import ForecastCache

# WMO 4677 weather-code table (Open-Meteo's `weather_code` field) — kept in
# the shared layer so the bot and the API never disagree about a code.
WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_weather_code(code) -> str | None:
    """Readable WMO description; None when the code is missing/unknown."""
    if code is None:
        return None
    try:
        return WEATHER_CODES.get(int(code), f"Code {int(code)}")
    except (TypeError, ValueError):
        return None


async def get_forecast(
    session: AsyncSession,
    *,
    lat: float,
    lon: float,
    days: int = 7,
    today: date | None = None,
) -> list[dict]:
    """Cached daily forecast rows for one location, starting today (or the
    `today` the caller's local calendar says it is). Values are metric per
    Open-Meteo defaults (°C, mm, km/h)."""
    today = today or date.today()
    rows = (
        await session.scalars(
            select(ForecastCache)
            .where(
                ForecastCache.lat == Decimal(str(lat)),
                ForecastCache.lon == Decimal(str(lon)),
                ForecastCache.date >= today,
            )
            .order_by(ForecastCache.date)
            .limit(max(1, days))
        )
    ).all()
    return [
        {
            "date": row.date,
            "payload": row.payload,
            "fetched_at": row.fetched_at,
        }
        for row in rows
    ]
