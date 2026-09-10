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
from app.models.integration import RawIngest
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
    await db_session.execute(
        text("TRUNCATE raw_ingest, forecast_cache RESTART IDENTITY CASCADE")
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
