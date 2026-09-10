"""Phase 7 API + shared-query tests (§18, §14, §8.2, §23 AC2).

GET /weather/forecast reads forecast_cache through the same get_forecast
query the /forecast bot command uses (§8.2: one implementation per read).
Session-protected (§17); days is clamped to 1..16; unconfigured coordinates
are an honest 503, never an empty-looking success.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.weather import ForecastCache

# Same session-based client conventions as the other API tests: GETs need no
# CSRF header; POST /auth/login does (§22.3).
CSRF = {"X-CSRF-Token": "test"}

OWNER_EMAIL = "owner@apexhealth.dev"
OWNER_PASSWORD = "test-owner-password"

HOME = {"weather_home_lat": 45.075, "weather_home_lon": 9.725}


@pytest_asyncio.fixture(autouse=True)
async def clean_forecast_cache(db_session):
    """The cache is shared global state across the session-scoped DB —
    start every test with an empty one."""
    await db_session.execute(text("TRUNCATE forecast_cache RESTART IDENTITY CASCADE"))
    await db_session.commit()
    yield


def _day_payload(day: date) -> dict:
    return {
        "source": "open-meteo",
        "time": day.isoformat(),
        "daily": {
            "temperature_2m_max": 16.1,
            "temperature_2m_min": 7.1,
            "temperature_2m_mean": 11.2,
            "precipitation_sum": 0.4,
            "precipitation_probability_max": 35,
            "wind_speed_10m_max": 18.6,
            "weather_code": 2.0,
        },
    }


async def _seed_cache(db_session, *, days: int = 3, lat: float = 45.075, lon: float = 9.725) -> None:
    start = date.today()
    for offset in range(days):
        day = start + timedelta(days=offset)
        db_session.add(
            ForecastCache(
                lat=Decimal(str(lat)),
                lon=Decimal(str(lon)),
                date=day,
                payload=_day_payload(day),
                fetched_at=datetime.now(UTC),
            )
        )
    await db_session.commit()


async def _login(client) -> None:
    resp = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=CSRF
    )
    assert resp.status_code == 200


def _patch_home(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(
        "app.api.weather.get_settings",
        lambda: SimpleNamespace(**{**HOME, **overrides}),
    )


async def test_forecast_requires_session(client, db_session):
    resp = await client.get("/weather/forecast")
    assert resp.status_code == 401


async def test_forecast_503_when_not_configured(client, db_session, monkeypatch):
    await _login(client)
    _patch_home(monkeypatch, weather_home_lat=0.0, weather_home_lon=0.0)
    resp = await client.get("/weather/forecast")
    assert resp.status_code == 503


async def test_forecast_returns_cached_days(client, db_session, monkeypatch):
    await _seed_cache(db_session, days=3)
    await _login(client)
    _patch_home(monkeypatch)

    resp = await client.get("/weather/forecast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lat"] == 45.075 and body["lon"] == 9.725
    assert body["days"] == 3
    first = body["forecast"][0]
    assert first["date"] == date.today().isoformat()
    assert first["description"] == "Partly cloudy"
    assert first["temp_max_c"] == 16.1
    assert first["precipitation_sum_mm"] == 0.4
    assert first["wind_max_kmh"] == 18.6
    assert "fetched_at" in first


async def test_forecast_days_clamped_and_scoped_to_coords(client, db_session, monkeypatch):
    await _seed_cache(db_session, days=3)
    # a row for a DIFFERENT location must never leak in
    await _seed_cache(db_session, days=3, lat=40.0, lon=5.0)
    await _login(client)
    _patch_home(monkeypatch)

    resp = await client.get("/weather/forecast?days=16")
    assert resp.status_code == 200  # only home coords, never the 40.0/5.0 rows
    assert resp.json()["days"] == 3

    rejected = await client.get("/weather/forecast?days=99")  # above le=16
    assert rejected.status_code == 422

    too_small = await client.get("/weather/forecast?days=0")
    assert too_small.status_code == 422


async def test_get_forecast_query_is_the_single_implementation(db_session):
    """§8.2: the shared query both presentation layers call — verify ordering
    and the days limit directly."""
    from app.queries import get_forecast

    await _seed_cache(db_session, days=5)
    rows = await get_forecast(db_session, lat=45.075, lon=9.725, days=2)
    assert len(rows) == 2
    assert rows[0]["date"] < rows[1]["date"]
    assert rows[0]["payload"]["daily"]["weather_code"] == 2.0
