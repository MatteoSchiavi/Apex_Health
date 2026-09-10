"""Weather endpoints (MASTER_SPEC §18, §14): GET /weather/forecast.

§14: without the dashboard this round the primary access point is the
/forecast bot command, but "the data collection and caching logic is
identical either way" — the API reads the same forecast_cache through the
same query layer (§8.2) for programmatic access. Session-protected like
every non-public route (§17).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.models.user import User
from app.queries import describe_weather_code, get_forecast

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast")
async def weather_forecast(
    days: int = Query(default=7, ge=1, le=16),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if settings.weather_home_lat == 0.0 and settings.weather_home_lon == 0.0:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Weather source not configured — set WEATHER_HOME_LAT/WEATHER_HOME_LON",
        )

    rows = await get_forecast(
        session,
        lat=settings.weather_home_lat,
        lon=settings.weather_home_lon,
        days=days,
        today=date.today(),
    )
    return {
        "lat": settings.weather_home_lat,
        "lon": settings.weather_home_lon,
        "days": len(rows),
        "forecast": [
            {
                "date": row["date"].isoformat(),
                "weather_code": (row["payload"].get("daily") or {}).get("weather_code"),
                "description": describe_weather_code(
                    (row["payload"].get("daily") or {}).get("weather_code")
                ),
                "temp_min_c": (row["payload"].get("daily") or {}).get("temperature_2m_min"),
                "temp_max_c": (row["payload"].get("daily") or {}).get("temperature_2m_max"),
                "precipitation_sum_mm": (row["payload"].get("daily") or {}).get(
                    "precipitation_sum"
                ),
                "precipitation_probability_max_pct": (row["payload"].get("daily") or {}).get(
                    "precipitation_probability_max"
                ),
                "wind_max_kmh": (row["payload"].get("daily") or {}).get("wind_speed_10m_max"),
                "fetched_at": row["fetched_at"].isoformat(),
            }
            for row in rows
        ],
    }
