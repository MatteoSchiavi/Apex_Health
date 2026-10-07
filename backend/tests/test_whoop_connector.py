import os
"""Whoop connector tests: OAuth flow (MockTransport) + sync pipeline
(fixture client) + the annotation law that motivated the connector.

The annotation assertions are the point of this file: Whoop data must land
in the SAME canonical shapes the Garmin connector writes (HRV in ms,
recovery as overnight_avg, sleep stages in SECONDS, kcal from kJ) while
Whoop-only quantities (sleep performance, strain, recovery score, zones) stay
in source_metrics and NEVER touch generic provider fields.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.connectors.whoop.sync import run_user_sync_with_escalation
from app.core.encryption import decrypt_json
from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import Integration, RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.models.lab import Observation
from tests.conftest import csrf_headers

OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]

SETTINGS = SimpleNamespace(
    whoop_client_id="whoop-cid",
    whoop_client_secret="whoop-secret",
    whoop_redirect_uri="http://localhost:8000/integrations/whoop/callback",
    whoop_oauth_authorize_url="https://api.prod.whoop.com/oauth/oauth2/auth",
    whoop_oauth_token_url="https://api.prod.whoop.com/oauth/oauth2/token",
    whoop_api_base="https://api.prod.whoop.com/developer/v2",
    whoop_scope="offline read:recovery read:sleep read:workout",
    whoop_page_size=25,
    whoop_page_delay_seconds=0.0,
)

SYNC_NOW = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)

SLEEP_RECORD = {
    "id": "11111111-1111-1111-1111-111111111111",
    "user_id": 9012,
    "start": "2026-09-20T23:10:00.000Z",
    "end": "2026-09-21T07:10:00.000Z",
    "timezone_offset": "+02:00",
    "nap": False,
    "score_state": "SCORED",
    "score": {
        "stage_summary": {
            "total_in_bed_time_milli": 28800000,
            "total_awake_time_milli": 2400000,
            "total_no_data_time_milli": 0,
            "total_light_sleep_time_milli": 14400000,
            "total_slow_wave_sleep_time_milli": 5400000,
            "total_rem_sleep_time_milli": 6600000,
            "sleep_cycle_count": 5,
            "disturbance_count": 3,
        },
        "sleep_needed": {
            "baseline_sleep_need_milli": 28800000,
            "sleep_need_from_recent_strain_milli": 1800000,
            "sleep_need_from_sleep_debt_milli": 0,
            "sleep_need_from_sleep_efficiency_milli": 0,
        },
        "respiratory_rate": 15.4,
        "sleep_performance_percentage": 91.0,
        "sleep_consistency_percentage": 78.0,
        "sleep_efficiency_percentage": 91.7,
    },
}

RECOVERY_RECORD = {
    "cycle_id": 93845,
    "sleep_id": SLEEP_RECORD["id"],
    "user_id": 9012,
    "score_state": "SCORED",
    "score": {
        "user_calibrating": False,
        "recovery_score": 88.0,
        "resting_heart_rate": 51.3,
        "hrv_rmssd_milli": 98.6,
        "spo2_percentage": 96.9,
        "skin_temp_celsius": 34.8,
    },
}

CYCLE_RECORD = {
    "id": 93845,
    "user_id": 9012,
    "start": "2026-09-21T05:10:00.000Z",
    "end": "2026-09-22T05:30:00.000Z",
    "timezone_offset": "+02:00",
    "score_state": "SCORED",
    "score": {
        "strain": 12.4,
        "kilojoule": 9000.0,
        "average_heart_rate": 72,
        "max_heart_rate": 181,
    },
}

WORKOUT_RECORD = {
    "id": "22222222-2222-2222-2222-222222222222",
    "user_id": 9012,
    "start": "2026-09-21T08:00:00.000Z",
    "end": "2026-09-21T09:30:00.000Z",
    "timezone_offset": "+02:00",
    "sport_name": "running",
    "sport_id": 1,
    "score_state": "SCORED",
    "score": {
        "strain": 14.2,
        "average_heart_rate": 152,
        "max_heart_rate": 178,
        "kilojoule": 5434.0,
        "percent_recorded": 100,
        "distance_meter": 15230.0,
        "altitude_gain_meter": 120.0,
        "zone_durations": {
            "zone_zero_milli": 0,
            "zone_one_milli": 900000,
            "zone_two_milli": 1800000,
            "zone_three_milli": 1200000,
            "zone_four_milli": 600000,
            "zone_five_milli": 300000,
        },
    },
}

BODY_RECORD = {
    "height_meter": 1.8,
    "weight_kilogram": 76.5,
    "max_heart_rate": 195,
}


class FixtureWhoopClient:
    """Client double: the sync pipeline depends only on the collection
    methods (no HTTP layer), mirroring the Garmin fixture-client idiom."""

    page_delay_s = 0.0
    tokens_out = None

    def __init__(self):
        self.profile_calls = 0

    async def fetch_sleeps(self, start=None, end=None):
        return [SLEEP_RECORD]

    async def fetch_recoveries(self, start=None, end=None):
        return [RECOVERY_RECORD]

    async def fetch_cycles(self, start=None, end=None):
        return [CYCLE_RECORD]

    async def fetch_workouts(self, start=None, end=None):
        return [WORKOUT_RECORD]

    async def fetch_body_measurement(self):
        self.profile_calls += 1
        return BODY_RECORD

    async def fetch_profile(self):
        self.profile_calls += 1
        return {"user_id": 9012, "email": "a@b.c", "first_name": "A", "last_name": "B"}


async def make_whoop_user(session, tz: str = "Europe/Rome"):
    user = User(name="whoop-athlete", timezone=tz)
    session.add(user)
    await session.flush()
    integration = Integration(user_id=user.id, provider="whoop", status="active")
    session.add(integration)
    await session.commit()
    return user, integration


async def _login(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, headers=csrf_headers(client)
    )
    assert login.status_code == 200


def _token_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "whoop_access_fixture",
                "refresh_token": "whoop_refresh_fixture",
                "expires_in": 14400,
                "scope": SETTINGS.whoop_scope,
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def fake_whoop_settings(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.whoop.client.get_settings", lambda: SETTINGS
    )
    monkeypatch.setattr("app.connectors.whoop.flow.get_settings", lambda: SETTINGS)
    monkeypatch.setattr("app.connectors.oauth2.get_settings", lambda: SETTINGS)


@pytest.fixture(autouse=True)
async def clean_whoop_tables(db_session):
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


# ---------------------------------------------------------------- OAuth flow


async def test_authorize_requires_configured_client(client: AsyncClient, monkeypatch):
    await _login(client)
    stripped = SimpleNamespace(
        **{**SETTINGS.__dict__, "whoop_client_id": "", "whoop_client_secret": ""}
    )
    monkeypatch.setattr("app.connectors.whoop.flow.get_settings", lambda: stripped)
    resp = await client.post("/settings/integrations/whoop/authorize", headers=csrf_headers(client))
    assert resp.status_code == 400
    assert "developer.whoop.com" in resp.json()["detail"]


async def test_authorize_mints_state_and_whoop_url(client: AsyncClient):
    await _login(client)
    resp = await client.post("/settings/integrations/whoop/authorize", headers=csrf_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorize_url"].startswith(SETTINGS.whoop_oauth_authorize_url)
    assert f"state={body['state']}" in body["authorize_url"]
    assert body["expires_in_seconds"] == 600


async def test_full_flow_stores_encrypted_tokens(client: AsyncClient, db_session, monkeypatch):
    await _login(client)
    minted = (
        await client.post("/settings/integrations/whoop/authorize", headers=csrf_headers(client))
    ).json()

    captured: list[httpx.Request] = []
    from app.connectors.whoop.client import WhoopOAuth

    monkeypatch.setattr(
        "app.connectors.whoop.flow.WhoopOAuth",
        lambda: WhoopOAuth(transport=_token_transport(captured)),
    )

    callback = await client.get(
        "/integrations/whoop/callback",
        params={"code": "whoop-auth-code", "state": minted["state"]},
    )
    assert callback.status_code == 200
    body = callback.json()
    assert body["status"] == "connected" and body["provider"] == "whoop"

    req_body = (await captured[0].aread()).decode()
    assert "grant_type=authorization_code" in req_body

    integration = (
        await db_session.scalars(
            select(Integration).where(Integration.provider == "whoop")
        )
    ).one()
    stored = decrypt_json(integration.credentials_encrypted)
    assert stored["access_token"] == "whoop_access_fixture"
    assert stored["refresh_token"] == "whoop_refresh_fixture"
    assert stored["expires_at"] is not None

    listed = (await client.get("/settings/integrations")).json()
    whoop = next(i for i in listed if i["provider"] == "whoop")
    assert whoop["credentials_stored"] is True


async def test_state_single_use(client: AsyncClient, monkeypatch):
    await _login(client)
    minted = (
        await client.post("/settings/integrations/whoop/authorize", headers=csrf_headers(client))
    ).json()
    from app.connectors.whoop.client import WhoopOAuth

    monkeypatch.setattr(
        "app.connectors.whoop.flow.WhoopOAuth",
        lambda: WhoopOAuth(transport=_token_transport([])),
    )
    first = await client.get(
        "/integrations/whoop/callback",
        params={"code": "c", "state": minted["state"]},
    )
    assert first.status_code == 200
    replay = await client.get(
        "/integrations/whoop/callback",
        params={"code": "c", "state": minted["state"]},
    )
    assert replay.status_code == 400


# ------------------------------------------------------------------- sync


async def test_backfill_normalizes_with_annotation_laws(db_session):
    user, integration = await make_whoop_user(db_session)
    report = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW
    )
    assert report is not None and report.mode == "backfill"
    # raw-first: sleep + recovery + cycle + workout + body = 5 payloads
    assert report.raw_rows_stored == 5

    # --- sleep: ms -> s, provider performance stays provider-scoped
    sleeps = (await db_session.scalars(select(SleepSession))).all()
    assert len(sleeps) == 1
    s = sleeps[0]
    assert s.total_sleep_s == (14400 + 5400 + 6600) // 1  # light+deep+rem seconds
    assert s.deep_s == 5400 and s.rem_s == 6600 and s.light_s == 14400
    assert s.awake_s == 2400
    assert s.origin == "whoop"
    assert s.sleep_score is None
    assert s.source_metrics["whoop"]["sleep_performance_pct"] == 91.0
    assert s.respiration_avg == 15.4
    assert s.local_date.isoformat() == "2026-09-21"  # wake-up local date (+02:00)

    # --- recovery: HRV ms as overnight_avg; rhr/spo2 merged; score in metrics
    hrv = (await db_session.scalars(select(HrvReading))).all()
    assert len(hrv) == 1
    assert hrv[0].reading_type == "overnight_avg"
    assert hrv[0].timestamp == datetime(2026, 9, 21, 7, 10, tzinfo=UTC)
    assert float(hrv[0].hrv_ms) == 98.6
    bio = (await db_session.scalars(select(DailyBiometric))).all()
    # one row for the wake-up day (recovery), one for the sync day (body
    # measurement weight)
    assert len(bio) == 2
    bio21 = next(b for b in bio if b.date.isoformat() == "2026-09-21")
    assert bio21.resting_hr == 51
    assert float(bio21.spo2_avg) == 96.9
    assert bio21.source_metrics["whoop"]["recovery_score"] == 88.0
    bio22 = next(b for b in bio if b.date.isoformat() == "2026-09-22")
    assert float(bio22.weight_kg) == 76.5

    # --- workout: kJ -> kcal; strain NEVER in training_load; distance kept
    activities = (await db_session.scalars(select(Activity))).all()
    assert len(activities) == 1
    a = activities[0]
    assert a.duration_s == 5400
    assert a.distance_m == 15230
    assert a.avg_hr == 152 and a.max_hr == 178
    assert a.calories == round(5434.0 / 4.184)
    assert a.training_load is None  # annotation law
    assert a.source_metrics["whoop"]["strain"] == 14.2
    assert a.source_metrics["whoop"]["sport_name"] == "running"
    assert a.data_completeness == "partial"

    links = (await db_session.scalars(select(ActivitySourceLink))).all()
    assert len(links) == 1
    assert links[0].source == "whoop"
    assert links[0].external_id == WORKOUT_RECORD["id"]

    # everything normalized
    unprocessed = (
        (
            await db_session.scalars(
                select(RawIngest).where(RawIngest.processed.is_(False))
            )
        ).all()
    )
    assert unprocessed == []


async def test_sync_is_idempotent(db_session):
    user, integration = await make_whoop_user(db_session)
    client = FixtureWhoopClient()
    first = await run_user_sync_with_escalation(
        db_session, user, integration, client, now=SYNC_NOW
    )
    assert first is not None
    second = await run_user_sync_with_escalation(
        db_session, user, integration, client, now=SYNC_NOW
    )
    assert second is not None
    # second pass upserts in place: no duplicate canonical rows
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 1
    assert await db_session.scalar(select(func.count()).select_from(SleepSession)) == 1
    assert await db_session.scalar(select(func.count()).select_from(HrvReading)) == 1


async def test_raw_recovery_preserved_and_context_observations_are_idempotent(db_session):
    user, integration = await make_whoop_user(db_session)
    for _ in range(2):
        report = await run_user_sync_with_escalation(
            db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW
        )
        assert report is not None
    rows = (await db_session.scalars(select(Observation).where(
        Observation.user_id == user.id, Observation.origin == "whoop",
    ))).all()
    assert len(rows) == 7
    hrv = next(row for row in rows if row.metric == "hrv_overnight_rmssd")
    assert hrv.unit == "ms" and hrv.value["value"] == 98.6
    assert hrv.metadata_json["hrv_method"] == "RMSSD"
    assert hrv.metadata_json["reading_context"] == "overnight"
    assert hrv.metadata_json["sleep_id"] == SLEEP_RECORD["id"]
    assert hrv.local_date.isoformat() == "2026-09-21"
    raw = await db_session.scalar(select(RawIngest).where(
        RawIngest.user_id == user.id, RawIngest.payload_type == "recovery",
    ).limit(1))
    assert raw.raw_json == RECOVERY_RECORD
    assert "cycle_start" not in raw.raw_json


async def test_recovery_without_timing_stays_unprocessed_instead_of_using_fetch_date(db_session):
    class MissingContext(FixtureWhoopClient):
        async def fetch_sleeps(self, start=None, end=None):
            return []
        async def fetch_cycles(self, start=None, end=None):
            return []
    user, integration = await make_whoop_user(db_session)
    report = await run_user_sync_with_escalation(db_session, user, integration, MissingContext(), now=SYNC_NOW)
    assert report is not None and report.raw_rows_unprocessed == 1
    assert await db_session.scalar(select(func.count()).select_from(HrvReading)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Observation).where(
        Observation.user_id == user.id, Observation.metric == "hrv_overnight_rmssd",
    )) == 0


async def test_pending_sleep_does_not_overwrite_scored_sleep(db_session):
    user, integration = await make_whoop_user(db_session)
    await run_user_sync_with_escalation(db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW)
    class PendingSleep(FixtureWhoopClient):
        async def fetch_sleeps(self, start=None, end=None):
            return [{**SLEEP_RECORD, "score_state": "PENDING_SCORE", "score": None}]
    report = await run_user_sync_with_escalation(db_session, user, integration, PendingSleep(), now=SYNC_NOW)
    assert report is not None
    sleep = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id))
    assert sleep.deep_s == 5400 and sleep.sleep_score is None
    assert sleep.source_metrics["whoop"]["sleep_performance_pct"] == 91.0


async def test_secondary_workout_resync_preserves_main_device_and_all_whoop_metrics(db_session):
    user, integration = await make_whoop_user(db_session)
    garmin = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(garmin)
    start = datetime(2026, 9, 21, 8, tzinfo=UTC)
    activity = Activity(user_id=user.id, start_time=start, start_tz_offset_minutes=120,
                        local_date=start.date(), duration_s=5400, avg_hr=140,
                        max_hr=175, distance_m=16000, calories=900,
                        training_load=45, data_completeness="full")
    db_session.add(activity)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=activity.id,
                                     source="garmin", external_id="garmin-workout"))
    await db_session.commit()
    for _ in range(2):
        report = await run_user_sync_with_escalation(db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW)
        assert report is not None and report.stats.activities_merged == 1
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 1
    assert activity.avg_hr == 140 and activity.calories == 900 and activity.training_load == 45
    assert activity.source_metrics["whoop"]["strain"] == 14.2
    assert activity.source_metrics["whoop"]["zone_seconds"]["one"] == 900
    assert activity.source_metrics["whoop"]["avg_hr"] == 152


async def test_whoop_main_takes_over_secondary_activity_without_duplicate(db_session):
    user, integration = await make_whoop_user(db_session)
    user.main_integration_id = integration.id
    start = datetime(2026, 9, 21, 8, tzinfo=UTC)
    activity = Activity(user_id=user.id, start_time=start, start_tz_offset_minutes=120,
                        local_date=start.date(), duration_s=5400, avg_hr=140,
                        data_completeness="full")
    db_session.add(activity)
    await db_session.flush()
    db_session.add(ActivitySourceLink(user_id=user.id, activity_id=activity.id,
                                     source="garmin", external_id="garmin-secondary"))
    await db_session.commit()
    report = await run_user_sync_with_escalation(db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW)
    assert report is not None and report.stats.activities_merged == 1
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 1
    assert activity.avg_hr == 152
    assert await db_session.scalar(select(func.count()).select_from(ActivitySourceLink)) == 2


async def test_secondary_sleep_keeps_provider_rows_separate_and_deduplicates_whoop_night(db_session):
    user, integration = await make_whoop_user(db_session)
    garmin = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(garmin)
    user.main_integration_id = garmin.id
    start = datetime(2026, 9, 20, 23, tzinfo=UTC)
    sleep = SleepSession(user_id=user.id, local_date=datetime(2026, 9, 21).date(),
                         start_time=start, end_time=datetime(2026, 9, 21, 7, tzinfo=UTC),
                         total_sleep_s=25000, deep_s=5000, light_s=20000,
                         sleep_score=82, origin="garmin",
                         source_metrics={"garmin": {"fixture": "main-night"}},
                         spo2_avg=98.2)
    db_session.add(sleep)
    await db_session.commit()
    for _ in range(2):
        report = await run_user_sync_with_escalation(
            db_session, user, integration, FixtureWhoopClient(), now=SYNC_NOW
        )
        assert report is not None
    sleeps = (await db_session.scalars(select(SleepSession))).all()
    assert len(sleeps) == 2
    assert sleep.total_sleep_s == 25000 and sleep.deep_s == 5000
    assert sleep.light_s == 20000 and sleep.sleep_score == 82
    assert float(sleep.spo2_avg) == 98.2
    assert sleep.source_metrics == {"garmin": {"fixture": "main-night"}}
    whoop_sleep = next(row for row in sleeps if row.origin == "whoop")
    assert whoop_sleep.total_sleep_s == 26400
    assert whoop_sleep.deep_s == 5400 and whoop_sleep.light_s == 14400
    assert whoop_sleep.sleep_score is None
    assert whoop_sleep.source_metrics["whoop"]["sleep_performance_pct"] == 91.0


def fresh_tokens():
    from app.connectors.oauth2 import OAuthTokens
    return OAuthTokens("fixture-access", "fixture-refresh", datetime.now(UTC) + timedelta(hours=1))


async def test_v2_client_uses_exact_url_and_paginates(monkeypatch):
    from app.connectors.whoop.client import LiveWhoopClient
    captured = []
    def handler(req):
        captured.append(req)
        assert req.url.path == "/developer/v2/activity/sleep"
        if req.url.params.get("nextToken"):
            return httpx.Response(200, json={"records": [{"id": "second"}], "next_token": None})
        return httpx.Response(200, json={"records": [{"id": "first"}], "next_token": "page-two"})
    async with httpx.AsyncClient(base_url=SETTINGS.whoop_api_base + "/", transport=httpx.MockTransport(handler)) as http:
        client = LiveWhoopClient(fresh_tokens(), http=http)
        assert await client.fetch_sleeps() == [{"id": "first"}, {"id": "second"}]
    assert captured[1].url.params["nextToken"] == "page-two"


async def test_401_forces_refresh_once_and_stops_on_repeated_401():
    from app.connectors.whoop.client import LiveWhoopClient, WhoopAuthError
    calls = []
    class OAuth:
        async def refresh(self, token):
            calls.append(token)
            return fresh_tokens()
    async with httpx.AsyncClient(base_url=SETTINGS.whoop_api_base + "/", transport=httpx.MockTransport(
        lambda req: httpx.Response(401, json={"message": "expired"})
    )) as http:
        client = LiveWhoopClient(fresh_tokens(), http=http, oauth=OAuth())
        with pytest.raises(WhoopAuthError, match="after refresh"):
            await client.fetch_sleeps()
    assert len(calls) == 1 and client.tokens_out is not None


async def test_profile_checks_http_status_before_json():
    from app.connectors.whoop.client import LiveWhoopClient, WhoopAuthError
    async with httpx.AsyncClient(base_url=SETTINGS.whoop_api_base + "/", transport=httpx.MockTransport(
        lambda req: httpx.Response(403, text="provider denied access")
    )) as http:
        client = LiveWhoopClient(fresh_tokens(), http=http)
        with pytest.raises(WhoopAuthError, match="access denied"):
            await client.fetch_profile()


async def test_repeated_page_token_is_bounded():
    from app.connectors.whoop.client import LiveWhoopClient, WhoopAPIError
    async with httpx.AsyncClient(base_url=SETTINGS.whoop_api_base + "/", transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"records": [], "next_token": "same"})
    )) as http:
        client = LiveWhoopClient(fresh_tokens(), http=http)
        with pytest.raises(WhoopAPIError, match="repeated"):
            await client.fetch_sleeps()


async def test_missing_collection_cycle_is_fetched_without_redating_recovery(db_session):
    class CycleLookup(FixtureWhoopClient):
        calls = 0
        async def fetch_sleeps(self, start=None, end=None):
            return []
        async def fetch_cycles(self, start=None, end=None):
            return []
        async def fetch_cycle(self, cycle_id):
            self.calls += 1
            assert cycle_id == str(CYCLE_RECORD["id"])
            return CYCLE_RECORD
    user, integration = await make_whoop_user(db_session)
    client = CycleLookup()
    report = await run_user_sync_with_escalation(db_session, user, integration, client, now=SYNC_NOW)
    assert report is not None and client.calls == 1
    hrv = await db_session.scalar(select(HrvReading).where(HrvReading.user_id == user.id))
    assert hrv.timestamp == datetime(2026, 9, 21, 5, 10, tzinfo=UTC)


async def test_malformed_score_retains_raw_for_retry(db_session):
    class MalformedSleep(FixtureWhoopClient):
        async def fetch_sleeps(self, start=None, end=None):
            return [{**SLEEP_RECORD, "score": ["schema changed"]}]
    user, integration = await make_whoop_user(db_session)
    report = await run_user_sync_with_escalation(db_session, user, integration, MalformedSleep(), now=SYNC_NOW)
    assert report is not None and report.raw_rows_unprocessed == 1
    raw = await db_session.scalar(select(RawIngest).where(
        RawIngest.user_id == user.id, RawIngest.payload_type == "sleep",
    ))
    assert raw.processed is False and raw.raw_json["score"] == ["schema changed"]


async def test_refresh_retains_previous_refresh_token_if_rotation_omits_it():
    from app.connectors.whoop.client import LiveWhoopClient
    class OAuth:
        async def refresh(self, token):
            fresh = fresh_tokens()
            fresh.refresh_token = None
            return fresh
    client = LiveWhoopClient(fresh_tokens(), oauth=OAuth())
    await client.ensure_fresh(force=True)
    assert client.tokens_out.refresh_token == "fixture-refresh"
