import os
"""Strava connector tests: OAuth flow + activity sync into canonical
activities (source='strava', idempotent by ActivitySourceLink)."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.connectors.strava.sync import run_user_sync_with_escalation
from app.core.encryption import decrypt_json
from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import Integration, RawIngest
from app.models.user import User

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]

SETTINGS = SimpleNamespace(
    strava_client_id="strava-cid",
    strava_client_secret="strava-secret",
    strava_redirect_uri="http://localhost:8000/integrations/strava/callback",
    strava_oauth_authorize_url="https://www.strava.com/oauth/authorize",
    strava_oauth_token_url="https://www.strava.com/oauth/token",
    strava_api_base="https://www.strava.com/api/v3",
    strava_scope="activity:read_all",
    strava_page_delay_seconds=0.0,
    strava_activity_page_size=100,
)

SYNC_NOW = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)

RIDE = {
    "id": 777001,
    "name": "Morning ride",
    "sport_type": "Ride",
    "start_date": "2026-09-20T06:30:00Z",
    "start_date_local": "2026-09-20T08:30:00+02:00",
    "elapsed_time": 5400,
    "moving_time": 5100,
    "distance": 42100.0,
    "total_elevation_gain": 310.0,
    "average_heartrate": 138.5,
    "max_heartrate": 172,
    "kilojoules": 1800.0,
    "suffer_score": 120.0,
}

RUN = {
    "id": 777002,
    "name": "Tempo 5k",
    "sport_type": "TrailRun",
    "start_date": "2026-09-21T17:00:00Z",
    "start_date_local": "2026-09-21T19:00:00+02:00",
    "elapsed_time": 1620,
    "moving_time": 1610,
    "distance": 5020.0,
    "average_heartrate": 158.0,
    "calories": 350,
    "suffer_score": 60.0,
}

UNKNOWN = {
    "id": 777003,
    "name": "Cheese rolling",
    "sport_type": "CheeseRolling",
    "start_date": "2026-09-21T12:00:00Z",
    "start_date_local": "2026-09-21T14:00:00+02:00",
    "elapsed_time": 600,
}


class FixtureStravaClient:
    page_delay_s = 0.0
    tokens_out = None

    def __init__(self, activities=None):
        self._activities = activities if activities is not None else [RIDE, RUN, UNKNOWN]

    async def fetch_activities(self, *, after_epoch=None, before_epoch=None, page_size=None):
        return list(self._activities)


async def make_strava_user(session, tz: str = "Europe/Rome"):
    user = User(name="strava-athlete", timezone=tz)
    session.add(user)
    await session.flush()
    integration = Integration(user_id=user.id, provider="strava", status="active")
    session.add(integration)
    await session.commit()
    return user, integration


async def _login(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=CSRF
    )
    assert login.status_code == 200


def _token_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "strava_access_fixture",
                "refresh_token": "strava_refresh_fixture",
                "expires_at": 1790000000,
                "expires_in": 21600,
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def fake_strava_settings(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.strava.client.get_settings", lambda: SETTINGS
    )
    monkeypatch.setattr("app.connectors.strava.flow.get_settings", lambda: SETTINGS)
    monkeypatch.setattr("app.connectors.oauth2.get_settings", lambda: SETTINGS)


@pytest.fixture(autouse=True)
async def clean_strava_tables(db_session):
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "activity_streams, sleep_sessions, hrv_readings, stress_readings, "
            "daily_biometrics, integrations RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def test_full_flow_stores_encrypted_tokens(client: AsyncClient, db_session, monkeypatch):
    await _login(client)
    minted = (
        await client.post("/settings/integrations/strava/authorize", headers=CSRF)
    ).json()
    assert minted["authorize_url"].startswith(SETTINGS.strava_oauth_authorize_url)

    captured: list[httpx.Request] = []
    from app.connectors.strava.client import StravaOAuth

    monkeypatch.setattr(
        "app.connectors.strava.flow.StravaOAuth",
        lambda: StravaOAuth(transport=_token_transport(captured)),
    )
    callback = await client.get(
        "/integrations/strava/callback",
        params={"code": "strava-code", "state": minted["state"]},
    )
    assert callback.status_code == 200
    assert callback.json()["status"] == "connected"

    integration = (
        await db_session.scalars(
            select(Integration).where(Integration.provider == "strava")
        )
    ).one()
    stored = decrypt_json(integration.credentials_encrypted)
    assert stored["access_token"] == "strava_access_fixture"


async def test_sync_normalizes_activities(db_session):
    user, integration = await make_strava_user(db_session)
    report = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureStravaClient(), now=SYNC_NOW
    )
    assert report is not None and report.mode == "backfill"
    assert report.raw_rows_stored == 3

    activities = (await db_session.scalars(select(Activity))).all()
    assert len(activities) == 3

    by_link = {
        link.external_id: link.activity_id
        for link in (await db_session.scalars(select(ActivitySourceLink))).all()
    }
    assert set(by_link) == {"777001", "777002", "777003"}

    ride = await db_session.get(Activity, by_link["777001"])
    assert ride.duration_s == 5400
    assert ride.distance_m == 42100
    assert ride.elevation_gain_m == 310.0
    assert ride.avg_hr == 138
    assert ride.calories == round(1800.0 / 4.184)
    assert ride.training_load is None
    assert ride.source_metrics["strava"]["relative_effort"] == 120.0
    assert ride.local_date.isoformat() == "2026-09-20"

    run = await db_session.get(Activity, by_link["777002"])
    assert run.duration_s == 1620
    assert run.distance_m == 5020
    assert run.calories == 350
    assert run.discipline_id is not None  # TrailRun -> running alias

    unknown = await db_session.get(Activity, by_link["777003"])
    assert unknown.discipline_id is None  # never invent a discipline
    assert unknown.source_metrics["strava"]["sport_type"] == "CheeseRolling"

    unprocessed = (
        (
            await db_session.scalars(
                select(RawIngest).where(RawIngest.processed.is_(False))
            )
        ).all()
    )
    assert unprocessed == []


async def test_sync_is_idempotent(db_session):
    user, integration = await make_strava_user(db_session)
    client = FixtureStravaClient()
    await run_user_sync_with_escalation(
        db_session, user, integration, client, now=SYNC_NOW
    )
    await run_user_sync_with_escalation(
        db_session, user, integration, client, now=SYNC_NOW
    )
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 3
    assert (
        await db_session.scalar(select(func.count()).select_from(ActivitySourceLink))
    ) == 3
