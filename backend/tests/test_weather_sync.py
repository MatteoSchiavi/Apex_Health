"""Phase 7 weather sync tests (§14, §17, §19, §23).

Forecast refresh: one fixture-backed payload lands raw-first (§17), then
upserts forecast_cache on (lat, lon, date); re-running the same payload
rewrites the same rows — never doubles them (§17: weather jobs are
idempotent, re-running must not double-count). Unset home coordinates skip
the beat tick instead of failing it. Beat carries the 6-hourly schedule.

No test touches the live Open-Meteo API (§0/§16.7/§20).
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.connectors.weather import normalize
from app.connectors.weather.client import WeatherError
from app.connectors.weather.sync import refresh_forecasts
from app.models.activity import Activity
from app.models.integration import RawIngest
from app.models.user import User
from app.models.weather import ForecastCache
from app.tasks.celery_app import celery_app
from app.tasks.weather_tasks import _refresh_all

FIXTURES = Path(__file__).resolve().parents[0] / "fixtures" / "weather"
FORECAST_FIXTURE = json.loads((FIXTURES / "forecast_response.json").read_text())

NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
HOME = (45.075, 9.725)


class FakeWeatherClient:
    """Fixture-backed stand-in for OpenMeteoClient; records calls."""

    def __init__(self, forecast_payload=None, archive_payload=None):
        self._forecast = forecast_payload
        self._archive = archive_payload
        self.forecast_calls: list[tuple[float, float, dict]] = []
        self.archive_calls: list[tuple[float, float, dict]] = []

    async def forecast(self, lat, lon, **kwargs):
        self.forecast_calls.append((lat, lon, kwargs))
        if self._forecast is None:
            raise WeatherError("no forecast fixture configured")
        return self._forecast

    async def archive(self, lat, lon, **kwargs):
        self.archive_calls.append((lat, lon, kwargs))
        if self._archive is None:
            raise WeatherError("no archive fixture configured")
        return self._archive


@pytest_asyncio.fixture(autouse=True)
async def clean_weather_tables(db_session):
    """Weather-domain tables (plus the activity domain the enrichment pass
    reads) start clean for every test in this file."""
    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, forecast_cache, activities, "
            "activity_source_links, activity_streams RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def test_refresh_upserts_cache_raw_first(db_session):
    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    report = await refresh_forecasts(
        db_session, client, user_id=1, lat=HOME[0], lon=HOME[1],
        days=7, tz_name="Europe/Rome", now=NOW,
    )
    await db_session.commit()

    assert report.forecast_days_cached == 8  # 1 past day + 7 forecast days
    rows = (await db_session.scalars(select(ForecastCache).order_by(ForecastCache.date))).all()
    assert [str(r.date) for r in rows][:3] == ["2025-03-09", "2025-03-10", "2025-03-11"]
    assert rows[0].payload["daily"]["weather_code"] == 1.0
    # §17: the raw payload landed BEFORE normalization, unprocessed
    raws = (await db_session.scalars(select(RawIngest).where(RawIngest.source == "open-meteo"))).all()
    assert len(raws) == 1
    assert raws[0].processed is False
    assert raws[0].payload_type == "forecast"
    assert raws[0].raw_json["daily"]["time"][0] == "2025-03-09"


async def test_refresh_twice_does_not_duplicate(db_session):
    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    for _ in range(2):
        await refresh_forecasts(
            db_session, client, user_id=1, lat=HOME[0], lon=HOME[1],
            days=7, tz_name="Europe/Rome", now=NOW,
        )
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(ForecastCache)) == 8
    assert await db_session.scalar(
        select(func.count()).select_from(RawIngest).where(RawIngest.source == "open-meteo")
    ) == 2  # raw history keeps both passes (§3)…


async def test_cache_key_uses_requested_coords_not_grid_echo(db_session):
    """Open-Meteo echoes grid-snapped coordinates; the UNIQUE key must stay
    on what we asked for or near-duplicates accumulate across refreshes."""
    echoed = dict(FORECAST_FIXTURE, latitude=45.1, longitude=9.7)
    client = FakeWeatherClient(forecast_payload=echoed)
    await refresh_forecasts(
        db_session, client, user_id=1, lat=HOME[0], lon=HOME[1],
        days=7, tz_name="Europe/Rome", now=NOW,
    )
    await db_session.commit()
    row = (
        await db_session.scalars(
            select(ForecastCache).where(ForecastCache.date == date(2025, 3, 9))
        )
    ).first()
    assert row.lat == Decimal(str(HOME[0])) and row.lon == Decimal(str(HOME[1]))
    assert row.payload["upstream_latitude"] == 45.1


async def test_normalize_rejects_payload_without_daily():
    with pytest.raises(normalize.WeatherNormalizeError):
        normalize.daily_rows({"latitude": 45.0})


def test_beat_carries_six_hourly_forecast_refresh():
    entry = celery_app.conf.beat_schedule["weather-refresh-every-6h"]
    assert entry["task"] == "weather.refresh_all"


async def test_task_skips_without_home_coordinates(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.tasks.weather_tasks.get_settings",
        lambda: SimpleNamespace(
            weather_home_lat=0.0,
            weather_home_lon=0.0,
            weather_forecast_days=7,
        ),
    )
    monkeypatch.setattr("app.tasks.weather_tasks.sessionmaker", None)  # must not touch DB
    result = await _refresh_all(client=FakeWeatherClient())
    assert result["status"] == "skipped"
    assert "not configured" in result["reason"]


# ------------------------------------------------------- §14 enrichment (AC1)


async def _make_activity(
    db_session,
    *,
    start_utc: datetime,
    local_date,
    with_streams: bool = True,
    stream_lat: float = 45.5,
    stream_lon: float = 9.9,
    weather_snapshot=None,
) -> "Activity":
    from app.models.activity import Activity, ActivityStream, Discipline

    discipline_id = await db_session.scalar(select(Discipline.id).limit(1))
    user_id = await db_session.scalar(select(User.id).order_by(User.id).limit(1))
    activity = Activity(
        user_id=user_id,
        discipline_id=discipline_id,
        start_time=start_utc,
        start_tz_offset_minutes=60,
        local_date=local_date,
        duration_s=3600,
    )
    if weather_snapshot is not None:
        activity.weather_snapshot = weather_snapshot
    db_session.add(activity)
    await db_session.flush()
    if with_streams:
        db_session.add_all(
            [
                ActivityStream(
                    activity_id=activity.id,
                    t_offset_s=0,
                    lat=Decimal(str(stream_lat)),
                    lon=Decimal(str(stream_lon)),
                ),
                ActivityStream(
                    activity_id=activity.id,
                    t_offset_s=60,
                    lat=Decimal(str(stream_lat + 0.01)),
                    lon=Decimal(str(stream_lon + 0.01)),
                ),
            ]
        )
    await db_session.flush()
    return activity


ARCHIVE_FIXTURE = json.loads((FIXTURES / "archive_response.json").read_text())


async def test_enrich_recent_activity_uses_stream_coords_and_start_hour(db_session):
    from app.connectors.weather.sync import enrich_activities

    # 2025-03-09 08:00 Europe/Rome == 07:00 UTC; fixture's forecast payload
    # covers that date and its hourly series the 08:00 sample.
    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 7, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
    )
    await db_session.commit()

    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    report = await enrich_activities(
        db_session, client, user_id=activity.user_id, home_lat=0.0, home_lon=0.0, now=NOW
    )
    await db_session.commit()

    assert report.activities_enriched == 1
    # coordinates come from the FIRST positioned stream sample, not home
    assert client.forecast_calls and client.forecast_calls[0][0] == 45.5
    snapshot = (await db_session.get(Activity, activity.id)).weather_snapshot
    assert snapshot["source"] == "open-meteo"
    assert snapshot["date"] == "2025-03-09"
    assert snapshot["weather_code"] == 1.0
    assert snapshot["at_start"]["hour"] == 8  # local start hour
    assert snapshot["at_start"]["temperature_2m"] == 9.1


async def test_enrich_activity_without_streams_falls_back_to_home(db_session):
    from app.connectors.weather.sync import enrich_activities

    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 7, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
        with_streams=False,
    )
    await db_session.commit()

    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    report = await enrich_activities(
        db_session, client, user_id=activity.user_id,
        home_lat=HOME[0], home_lon=HOME[1], now=NOW,
    )
    await db_session.commit()

    assert report.activities_enriched == 1
    assert client.forecast_calls[0][0] == HOME[0]
    assert (await db_session.get(Activity, activity.id)).weather_snapshot is not None


async def test_enrich_skipped_entirely_when_no_coords_anywhere(db_session):
    from app.connectors.weather.sync import enrich_activities

    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 7, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
        with_streams=False,
    )
    await db_session.commit()

    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    report = await enrich_activities(
        db_session, client, user_id=activity.user_id, home_lat=0.0, home_lon=0.0, now=NOW
    )
    await db_session.commit()

    assert report.activities_enriched == 0
    assert report.activities_skipped_no_weather == 1
    assert client.forecast_calls == []
    assert (await db_session.get(Activity, activity.id)).weather_snapshot is None


async def test_enrich_old_activity_rides_archive_api(db_session):
    from app.connectors.weather.sync import enrich_activities

    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 1, 11, 8, 0, tzinfo=UTC),
        local_date=date(2025, 1, 11),  # older than the archive lag from NOW
    )
    await db_session.commit()

    client = FakeWeatherClient(archive_payload=ARCHIVE_FIXTURE)
    report = await enrich_activities(
        db_session, client, user_id=activity.user_id,
        home_lat=HOME[0], home_lon=HOME[1], now=NOW,
    )
    await db_session.commit()

    assert report.activities_enriched == 1
    assert client.forecast_calls == []  # old dates never hit the forecast API
    assert client.archive_calls[0][2]["start_date"] == "2025-01-11"
    assert client.archive_calls[0][2]["end_date"] == "2025-01-11"
    snapshot = (await db_session.get(Activity, activity.id)).weather_snapshot
    assert snapshot["weather_code"] == 71.0  # snow, per the archive fixture


async def test_enrich_is_idempotent_and_never_overwrites(db_session):
    from app.connectors.weather.sync import enrich_activities

    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 7, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
    )
    manual = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
        with_streams=False,
        weather_snapshot={"source": "manual", "note": "owner wrote this"},
    )
    await db_session.commit()

    client = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    first = await enrich_activities(
        db_session, client, user_id=activity.user_id,
        home_lat=HOME[0], home_lon=HOME[1], now=NOW,
    )
    assert first.activities_enriched == 1  # the manual one is never touched

    await db_session.commit()
    manual_before = (await db_session.get(Activity, manual.id)).weather_snapshot

    # second pass: nothing pending → no upstream calls at all
    client2 = FakeWeatherClient(forecast_payload=FORECAST_FIXTURE)
    second = await enrich_activities(
        db_session, client2, user_id=activity.user_id,
        home_lat=HOME[0], home_lon=HOME[1], now=NOW,
    )
    assert second.activities_enriched == 0 and second.activities_skipped_no_weather == 0
    assert client2.forecast_calls == [] and client2.archive_calls == []
    assert (await db_session.get(Activity, manual.id)).weather_snapshot == manual_before


async def test_task_enriches_ingested_activities_end_to_end(db_session, monkeypatch):
    """AC1 driver: the same beat tick that refreshes the cache fills every
    ingested-but-unweathered activity (§14 'populated at ingestion')."""
    activity = await _make_activity(
        db_session,
        start_utc=datetime(2025, 3, 9, 7, 0, tzinfo=UTC),
        local_date=date(2025, 3, 9),
    )
    await db_session.commit()

    monkeypatch.setattr(
        "app.tasks.weather_tasks.get_settings",
        lambda: SimpleNamespace(
            weather_home_lat=HOME[0],
            weather_home_lon=HOME[1],
            weather_forecast_days=7,
        ),
    )
    result = await _refresh_all(
        client=FakeWeatherClient(forecast_payload=FORECAST_FIXTURE), now=NOW
    )

    assert result["status"] == "ok"
    assert result["forecast_days_cached"] == 8
    assert result["activities_enriched"] >= 1
    # the task committed in its own session — force a fresh load instead of
    # this session's identity-map cache (expire_on_commit=False keeps stale
    # instances, and expired-attribute refresh isn't available in async)
    snapshot = (
        await db_session.get(Activity, activity.id, populate_existing=True)
    ).weather_snapshot
    assert snapshot is not None and snapshot["source"] == "open-meteo"
