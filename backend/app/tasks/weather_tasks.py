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


async def _refresh_all(
    client: OpenMeteoClient | None = None, now: datetime | None = None
) -> dict:
    settings = get_settings()
    now = now or datetime.now(UTC)
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
# ---------------------------------------------------- §14 forecast × readiness


# §14: "cross-reference a good forecast window with a high readiness score for
# a proactive Telegram nudge". "Good window" is the spec's phrase but not its
# numbers — these thresholds are the documented judgment call (metric units,
# Open-Meteo defaults): a day you can actually train outside is not colder
# than 5°C, not hotter than 28°C, unlikely to rain, and not windy.
GOOD_WINDOW_MIN_TEMP_C = 5.0
GOOD_WINDOW_MAX_TEMP_C = 28.0
GOOD_WINDOW_MAX_RAIN_PROBABILITY = 40
GOOD_WINDOW_MAX_WIND_KMH = 35.0

NUDGE_LOCAL_HOUR = 7  # morning nudge, once per user per local day


async def _readiness_nudge(now_iso: str | None = None, client=None) -> dict:
    """§14 nudge: when TOMORROW's cached forecast is a good training window
    AND the user's latest readiness is high, proactively notify their linked
    chats — once per user per day (Redis SETNX dedup, §17-style).

    Hourly beat dispatch, task gates on LOCAL hour (the feature engine's
    pattern) so every timezone is served from one UTC schedule. No
    integrations row involvement — this is a read-only cross-reference.
    """
    from datetime import timedelta

    from redis.asyncio import Redis

    from app.connectors.telegram.alerts import notify_user
    from app.queries import describe_weather_code, get_forecast, latest_daily_feature

    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    settings = get_settings()

    if settings.weather_home_lat == 0.0 and settings.weather_home_lon == 0.0:
        return {"status": "skipped", "reason": "home coordinates not configured"}
    threshold = settings.weather_nudge_readiness_threshold
    if threshold <= 0:
        return {"status": "disabled"}

    telegram = None
    if settings.telegram_bot_token:
        from app.connectors.telegram.client import LiveTelegramClient

        telegram = LiveTelegramClient(settings.telegram_bot_token)

    nudged: list[dict] = []
    considered = 0

    async with sessionmaker() as session:
        user_ids = (await session.execute(select(User.id).order_by(User.id))).scalars().all()
        for user_id in user_ids:
            user = await session.get(User, user_id)
            feature = await latest_daily_feature(session, user_id)
            if feature is None or feature.readiness_score is None:
                continue
            if float(feature.readiness_score) < threshold:
                continue
            considered += 1

            local_today = now.astimezone(ZoneInfo(user.timezone)).date()
            if now.astimezone(ZoneInfo(user.timezone)).hour != NUDGE_LOCAL_HOUR:
                continue
            tomorrow = local_today + timedelta(days=1)

            rows = await get_forecast(
                session,
                lat=settings.weather_home_lat,
                lon=settings.weather_home_lon,
                days=2,
                today=local_today,
            )
            row = next((r for r in rows if r["date"] == tomorrow), None)
            if row is None:
                continue
            daily = row["payload"].get("daily") or {}
            temp_max = daily.get("temperature_2m_max")
            rain_prob = daily.get("precipitation_probability_max")
            wind = daily.get("wind_speed_10m_max")
            good = (
                temp_max is not None
                and GOOD_WINDOW_MIN_TEMP_C <= float(temp_max) <= GOOD_WINDOW_MAX_TEMP_C
                and rain_prob is not None
                and float(rain_prob) <= GOOD_WINDOW_MAX_RAIN_PROBABILITY
                and wind is not None
                and float(wind) <= GOOD_WINDOW_MAX_WIND_KMH
            )
            if not good:
                continue

            # one nudge per user per target day
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                key = f"weather_nudge:{user_id}:{tomorrow.isoformat()}"
                fresh = await redis.set(key, "1", nx=True, ex=60 * 60 * 48)
            finally:
                await redis.aclose()
            if not fresh:
                continue

            text = (
                f"☀️ Good training window tomorrow ({tomorrow.isoformat()}): "
                f"{describe_weather_code(daily.get('weather_code')) or 'fair conditions'}, "
                f"{daily.get('temperature_2m_min')}–{temp_max}°C, "
                f"rain chance {rain_prob}%, wind {wind}km/h. "
                f"Readiness {float(feature.readiness_score):.0f} supports a session (§14)."
            )
            if telegram is not None:
                await notify_user(sessionmaker, telegram, user_id, text)
            nudged.append({"user_id": user_id, "date": tomorrow.isoformat()})

    return {"status": "ok", "considered": considered, "nudged": nudged}


@celery_app.task(name="weather.readiness_nudge")
def readiness_nudge() -> dict:
    return asyncio.run(_readiness_nudge())
