"""Weather task (§19: forecast refresh every 6 hours, upserts forecast_cache).

One beat entry drives both weather operations:
- forecast refresh for the configured home coordinates (forecast_cache);
- §14 activity enrichment (activities.weather_snapshot for ingested
  activities that don't carry weather yet).

Coordinates come from Settings (WEATHER_HOME_LAT/LON). Unset coordinates
disable the refresh with a logged note — a beat tick must never fail because
the owner hasn't set a location yet. No integrations row exists for weather
(keyless source, nothing to authenticate or escalate — §21 applies to
authenticated per-user connectors).
"""

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.connectors.weather.client import OpenMeteoClient
from app.connectors.weather.fetch import owner_user_id
from app.connectors.weather.sync import enrich_activities, refresh_forecasts
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.weather")


def _client_factory(client: OpenMeteoClient | None) -> OpenMeteoClient:
    """One shared client per task run by default; tests inject a fake."""
    return client if client is not None else OpenMeteoClient()


async def _refresh_all(client: OpenMeteoClient | None = None) -> dict:
    settings = get_settings()
    now = datetime.now(UTC)
    out: dict = {"forecast_days_cached": 0, "activities_enriched": 0, "users": {}}

    if settings.weather_home_lat == 0.0 and settings.weather_home_lon == 0.0:
        out["status"] = "skipped"
        out["reason"] = "WEATHER_HOME_LAT/WEATHER_HOME_LON not configured"
        logger.info("weather refresh: %s", out["reason"])
        return out

    async with sessionmaker() as session:
        # resolve owner for raw-row attribution (§17 raw-first needs a user_id)
        owner_id = await owner_user_id(session)
        if owner_id is None:
            owner_id = await session.scalar(select(User.id).order_by(User.id).limit(1))
        if owner_id is None:
            out["status"] = "skipped"
            out["reason"] = "no user account exists yet"
            return out

        user = await session.get(User, owner_id)
        tz_name = user.timezone if user else "UTC"

        report = await refresh_forecasts(
            session,
            _client_factory(client),
            user_id=owner_id,
            lat=settings.weather_home_lat,
            lon=settings.weather_home_lon,
            days=settings.weather_forecast_days,
            tz_name=tz_name,
            now=now,
        )
        out["forecast_days_cached"] = report.forecast_days_cached

        # §14 enrichment: every user with not-yet-weathered activities.
        user_ids = (
            (await session.execute(
                select(User.id).order_by(User.id)
            ))
            .scalars()
            .all()
        )
        for uid in user_ids:
            enriched = await enrich_activities(
                session,
                _client_factory(client),
                user_id=uid,
                home_lat=settings.weather_home_lat,
                home_lon=settings.weather_home_lon,
                now=now,
            )
            out["activities_enriched"] += enriched.activities_enriched
            if enriched.notes:
                out["users"][str(uid)] = {"notes": enriched.notes[:5]}

        await session.commit()
    out["status"] = "ok"
    return out


@celery_app.task(name="weather.refresh_all")
def refresh_all() -> dict:
    return asyncio.run(_refresh_all())
