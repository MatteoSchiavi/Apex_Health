import os
"""Web UI surface tests (migration 0007 batch): /me prefs, /dashboard/overview,
/activities (+detail+streams), /sleep, /metrics, /settings/devices (main-device
law), services/device_merge, FIT lap upserts.

All endpoints are session-scoped: every probe includes cross-user isolation
checks (a foreign id must 404/422, never leak).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityLap, ActivitySourceLink, Discipline
from app.models.integration import Integration, RawIngest
from app.models.user import AuthCredential, User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.services.device_merge import (
    field_merge,
    main_provider,
    resolve_activity_winner,
    should_write_vitals,
)
from app.services.fit_enrichment import upsert_laps

pytestmark = pytest.mark.asyncio

CSRF = {"X-CSRF-Token": "test"}
OWNER = (os.environ["OWNER_EMAIL"], os.environ["OWNER_PASSWORD"])
TODAY = date(2026, 9, 22)


@pytest.fixture(autouse=True)
async def clean_ui_tables(db_session):
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "activity_streams, activity_laps, daily_biometrics, "
            "hrv_readings, sleep_sessions, integrations, ai_chat_sessions, "
            "ai_chat_messages RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


async def _login(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, headers=CSRF
    )
    assert resp.status_code == 200


async def _owner_user(db_session: AsyncSession) -> User:
    """The session user's User row — matched by the OWNER credential's email
(ensure_owner names the user after the email local-part)."""
    cred = (
        await db_session.scalars(
            select(AuthCredential).where(AuthCredential.role == "owner").limit(1)
        )
    ).first()
    assert cred is not None
    return await db_session.get(User, cred.user_id)


async def _seed_day(db_session: AsyncSession, user_id: int) -> None:
    disc = (
        await db_session.scalars(
            select(Discipline).where(Discipline.name == "running")
        )
    ).first()
    db_session.add(
        Activity(
            user_id=user_id,
            discipline_id=disc.id if disc else None,
            start_time=datetime(TODAY.year, TODAY.month, TODAY.day, 8, 0, tzinfo=UTC),
            start_tz_offset_minutes=120,
            local_date=TODAY,
            duration_s=3600,
            distance_m=10000,
            avg_hr=150,
            max_hr=172,
            training_load=88,
            data_completeness="full",
        )
    )
    await db_session.flush()
    db_session.add(
        SleepSession(
            user_id=user_id,
            local_date=TODAY,
            start_time=datetime(TODAY.year, TODAY.month, TODAY.day, 23, 0, tzinfo=UTC)
            - timedelta(days=1),
            end_time=datetime(TODAY.year, TODAY.month, TODAY.day, 7, 0, tzinfo=UTC),
            total_sleep_s=25200,
            deep_s=5400,
            light_s=12600,
            rem_s=6600,
            awake_s=600,
            sleep_score=88,
            respiration_avg=13.4,
            spo2_avg=97.8,
        )
    )
    db_session.add(
        DailyBiometric(
            user_id=user_id,
            date=TODAY,
            resting_hr=44,
            weight_kg=75.2,
            vo2max=58.4,
            steps=12480,
            spo2_avg=97.9,
        )
    )
    db_session.add(
        HrvReading(
            user_id=user_id,
            timestamp=datetime(TODAY.year, TODAY.month, TODAY.day, 4, 0, tzinfo=UTC),
            hrv_ms=68,
            reading_type="overnight_avg",
            rolling_baseline_ms=63,
        )
    )
    await db_session.commit()


# ------------------------------------------------------------------- /me


async def test_me_roundtrip_and_validation(client: AsyncClient, db_session):
    await _login(client)
    me = await client.get("/me")
    assert me.status_code == 200
    body = me.json()
    assert body["locale"] in ("en", "it")
    assert body["theme"] in ("dark", "light")

    upd = await client.put(
        "/me",
        json={"locale": "it", "theme": "light", "units": "imperial"},
        headers=CSRF,
    )
    assert upd.status_code == 200
    assert upd.json()["locale"] == "it"
    assert upd.json()["theme"] == "light"

    bad = await client.put("/me", json={"locale": "fr"}, headers=CSRF)
    assert bad.status_code == 422  # CHECK-compatible schema rejects


async def test_me_password_change(client: AsyncClient):
    await _login(client)
    # wrong current password → 401
    bad = await client.put(
        "/me/password",
        json={"current_password": "nope", "new_password": "another-pass-1"},
        headers=CSRF,
    )
    assert bad.status_code == 401


# --------------------------------------------------------- /dashboard/overview


async def test_dashboard_overview(client: AsyncClient, db_session):
    await _login(client)
    user = await _owner_user(db_session)
    await _seed_day(db_session, user.id)

    resp = await client.get(f"/dashboard/overview?date={TODAY.isoformat()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == TODAY.isoformat()
    assert body["resting_hr"] == 44
    assert body["steps"] == 12480
    assert body["sleep_hours"] == 7.0
    assert body["sleep"]["stages"]["deep_s"] == 5400
    assert len(body["activities"]) == 1
    assert body["activities"][0]["duration_s"] == 3600
    assert body["hrv_ms"] == 68.0
    assert body["hrv_baseline_ms"] == 63.0


async def test_dashboard_requires_auth(client: AsyncClient):
    resp = await client.get(
        "/dashboard/overview", headers={"X-CSRF-Token": "test"}
    )
    assert resp.status_code == 401


# --------------------------------------------------------------- /activities


async def test_activities_list_and_detail(client: AsyncClient, db_session):
    await _login(client)
    user = await _owner_user(db_session)
    await _seed_day(db_session, user.id)

    listing = await client.get("/activities?limit=10")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    act = body["items"][0]
    assert act["duration_s"] == 3600
    assert act["training_load"] == 88.0

    detail = await client.get(f"/activities/{act['id']}")
    assert detail.status_code == 200
    assert detail.json()["avg_hr"] == 150

    # foreign id → 404 (isolation law)
    other = User(name="Stranger")
    db_session.add(other)
    await db_session.commit()
    foreign = Activity(
        user_id=other.id,
        start_time=datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
        start_tz_offset_minutes=120,
        local_date=TODAY,
        duration_s=600,
    )
    db_session.add(foreign)
    await db_session.commit()
    leak = await client.get(f"/activities/{foreign.id}")
    assert leak.status_code == 404


# ------------------------------------------------------------------- /sleep


async def test_sleep_list_and_day(client: AsyncClient, db_session):
    await _login(client)
    user = await _owner_user(db_session)
    await _seed_day(db_session, user.id)

    listing = await client.get("/sleep")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["total_sleep_s"] == 25200

    day = await client.get(f"/sleep/{TODAY.isoformat()}")
    assert day.status_code == 200
    body = day.json()
    assert body["session"]["sleep_score"] == 88.0
    assert body["biometrics"]["resting_hr"] == 44
    assert len(body["hrv_readings"]) == 1
    assert body["hrv_readings"][0]["hrv_ms"] == 68.0


# ----------------------------------------------------------------- /metrics


async def test_metrics_catalog_and_trend(client: AsyncClient, db_session):
    await _login(client)
    user = await _owner_user(db_session)
    await _seed_day(db_session, user.id)

    catalog = await client.get("/metrics")
    assert catalog.status_code == 200
    assert "resting_hr" in catalog.json()
    assert "acwr" in catalog.json()

    trend = await client.get("/metrics/resting_hr?days=30")
    assert trend.status_code == 200
    body = trend.json()
    assert body["metric"] == "resting_hr"
    assert body["unit"] == "bpm"
    values = [p["value"] for p in body["points"] if p["value"] is not None]
    assert 44.0 in values

    unknown = await client.get("/metrics/does_not_exist")
    assert unknown.status_code == 404


# --------------------------------------------------------- /settings/devices


async def test_devices_main_device_flow(client: AsyncClient, db_session):
    await _login(client)
    user = await _owner_user(db_session)
    g = Integration(user_id=user.id, provider="garmin")
    w = Integration(user_id=user.id, provider="whoop")
    db_session.add_all([g, w])
    await db_session.commit()

    listing = await client.get("/settings/devices")
    assert listing.status_code == 200
    devices = listing.json()
    assert len(devices) == 2
    # legacy: main flag falls to garmin when nothing declared
    by_provider = {d["provider"]: d for d in devices}
    assert by_provider["garmin"]["is_main"] is True
    assert by_provider["whoop"]["is_main"] is False

    set_main = await client.put(
        "/settings/devices/main",
        json={"integration_id": w.id},
        headers=CSRF,
    )
    assert set_main.status_code == 200
    devices = set_main.json()
    by_provider = {d["provider"]: d for d in devices}
    assert by_provider["whoop"]["is_main"] is True
    assert by_provider["garmin"]["is_main"] is False

    # foreign integration → 422
    stranger = User(name="Stranger2")
    db_session.add(stranger)
    await db_session.commit()
    foreign = Integration(user_id=stranger.id, provider="whoop")
    db_session.add(foreign)
    await db_session.commit()
    steal = await client.put(
        "/settings/devices/main",
        json={"integration_id": foreign.id},
        headers=CSRF,
    )
    assert steal.status_code == 422


# ------------------------------------------------- device_merge service laws


async def test_main_provider_fallback(db_session):
    user = User(name="MergeUser")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Integration(user_id=user.id, provider="whoop"))
    db_session.add(Integration(user_id=user.id, provider="garmin"))
    await db_session.commit()

    # No declaration → garmin wins by fallback priority.
    assert await main_provider(db_session, user) == "garmin"

    # Declaration wins over fallback.
    whoop = (
        await db_session.scalars(
            select(Integration).where(
                Integration.user_id == user.id, Integration.provider == "whoop"
            )
        )
    ).first()
    user.main_integration_id = whoop.id
    await db_session.commit()
    assert await main_provider(db_session, user) == "whoop"


async def test_vitals_merge_law(db_session):
    user = User(name="VitalsUser")
    db_session.add(user)
    await db_session.flush()
    garmin = Integration(user_id=user.id, provider="garmin")
    db_session.add(garmin)
    await db_session.commit()
    user.main_integration_id = garmin.id
    await db_session.commit()

    # main device always writes
    d1 = await should_write_vitals(db_session, user, "daily_biometrics", TODAY, "garmin", True)
    assert d1.write is True

    # secondary over existing main data → blocked
    db_session.add(DailyBiometric(user_id=user.id, date=TODAY, resting_hr=44))
    await db_session.commit()
    d2 = await should_write_vitals(db_session, user, "daily_biometrics", TODAY, "oura", True)
    assert d2.write is False

    # secondary over a MISSING day → fills
    other_day = TODAY - timedelta(days=3)
    d3 = await should_write_vitals(db_session, user, "daily_biometrics", other_day, "oura", True)
    assert d3.write is True

    # empty payload never overwrites regardless of source
    d4 = await should_write_vitals(db_session, user, "daily_biometrics", other_day, "oura", False)
    assert d4.write is False


async def test_activity_same_effort_resolution(db_session):
    user = User(name="ActivityUser")
    db_session.add(user)
    await db_session.flush()
    garmin = Integration(user_id=user.id, provider="garmin")
    db_session.add(garmin)
    await db_session.commit()
    user.main_integration_id = garmin.id
    await db_session.commit()

    start = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)
    main_act = Activity(
        user_id=user.id,
        start_time=start,
        start_tz_offset_minutes=120,
        local_date=TODAY,
        duration_s=3600,
    )
    db_session.add(main_act)
    await db_session.flush()
    db_session.add(
        ActivitySourceLink(activity_id=main_act.id, source="garmin", external_id="g1")
    )
    await db_session.commit()

    # Whoop logs the same effort 4 minutes later → deduped onto main's row
    decision = await resolve_activity_winner(
        db_session, user, start + timedelta(minutes=4), 3500, "whoop"
    )
    assert decision.write is False
    assert decision.winner_activity_id == main_act.id

    # A different window → Whoop's session writes (secondary covers a gap)
    decision2 = await resolve_activity_winner(
        db_session, user,
        datetime(2026, 9, 22, 17, 0, tzinfo=UTC), 1800, "whoop",
    )
    assert decision2.write is True


def test_field_merge_rule():
    assert field_merge(1, 2) == (1, "main")
    assert field_merge(None, 2) == (2, "secondary")
    assert field_merge(None, None) == (None, "none")


# ----------------------------------------------------- FIT lap upserts


async def test_lap_upsert_idempotent(db_session):
    user = User(name="LapUser")
    db_session.add(user)
    await db_session.flush()
    act = Activity(
        user_id=user.id,
        start_time=datetime(2026, 9, 22, 8, 0, tzinfo=UTC),
        start_tz_offset_minutes=120,
        local_date=TODAY,
        duration_s=3600,
    )
    db_session.add(act)
    await db_session.commit()

    def laps():
        return [
            {
                "lap_index": 1,
                "start_time": datetime(2026, 9, 22, 8, 0, tzinfo=UTC),
                "duration_s": 1800,
                "distance_m": 5000.0,
                "avg_hr": 148,
                "max_hr": 160,
                "avg_power": None,
                "calories": 600,
                "extras": {"total_ascent": 120.0},
            },
            {
                "lap_index": 2,
                "duration_s": 1800,
                "distance_m": 5000.0,
                "avg_hr": 152,
                "max_hr": 170,
                "avg_power": 240.0,
                "calories": 620,
                "extras": {},
            },
        ]

    written = await upsert_laps(db_session, act.id, laps())
    assert written == 2
    # second pass updates in place — no duplicates
    await upsert_laps(db_session, act.id, laps())
    rows = (
        await db_session.scalars(
            select(ActivityLap).where(ActivityLap.activity_id == act.id)
        )
    ).all()
    assert len(rows) == 2
    assert rows[0].avg_hr == 148
    assert rows[1].avg_power == 240.0


# ------------------------------------------------------------------ anchor
# fallback (fresh-connect reality: today unsynced but history populated)


async def test_overview_falls_back_to_latest_measured_day(
    client: AsyncClient, db_session: AsyncSession
):
    await _login(client)
    user = await _owner_user(db_session)

    old_day = date.today() - timedelta(days=12)
    db_session.add(
        DailyBiometric(
            user_id=user.id, date=old_day, resting_hr=46, steps=8000, spo2_avg=97.1
        )
    )
    await db_session.commit()

    resp = await client.get("/dashboard/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == old_day.isoformat()
    assert body["anchor_is_today"] is False
    assert body["resting_hr"] == 46


async def test_overview_pinned_date_wins_over_fallback(
    client: AsyncClient, db_session: AsyncSession
):
    await _login(client)
    user = await _owner_user(db_session)

    old_day = date.today() - timedelta(days=20)
    db_session.add(
        DailyBiometric(user_id=user.id, date=old_day, resting_hr=44)
    )
    await db_session.commit()

    resp = await client.get("/dashboard/overview?date=2020-01-01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2020-01-01"
    # explicit date never falls back, even when empty
    assert body["anchor_is_today"] is False


# ------------------------------------------------------------- sleep stages


async def test_sleep_stages_from_raw_payload(
    client: AsyncClient, db_session: AsyncSession
):
    await _login(client)
    user = await _owner_user(db_session)

    night_date = date.today()
    start = datetime(night_date.year, night_date.month, night_date.day, 22, 30, tzinfo=UTC) - timedelta(days=1)
    end = start + timedelta(hours=8)
    session_row = SleepSession(
        user_id=user.id,
        local_date=night_date,
        start_time=start,
        end_time=end,
        total_sleep_s=27000,
        deep_s=5000,
        light_s=15000,
        rem_s=6000,
        awake_s=800,
        sleep_score=88,
    )
    db_session.add(session_row)
    levels = [
        {"activityLevel": {"value": 1}, "startGMT": "2026-09-23T21:30:00.0", "endGMT": "2026-09-23T22:15:00.0"},
        {"activityLevel": {"value": 2}, "startGMT": "2026-09-23T22:15:00.0", "endGMT": "2026-09-23T23:00:00.0"},
        {"activityLevel": {"value": 3}, "startGMT": "2026-09-23T23:00:00.0", "endGMT": "2026-09-24T00:05:00.0"},
    ]
    db_session.add(
        RawIngest(
            user_id=user.id,
            source="garmin",
            payload_type="sleep",
            raw_json={
                "dailySleepDTO": {
                    "sleepStartTimestampGMT": int(start.timestamp() * 1000),
                    "sleepEndTimestampGMT": int(end.timestamp() * 1000),
                    "sleepLevels": levels,
                }
            },
        )
    )
    await db_session.commit()

    resp = await client.get(f"/sleep/{night_date.isoformat()}/stages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == night_date.isoformat()
    assert body["source"] == "garmin"
    segs = body["segments"]
    assert segs is not None and len(segs) == 3
    assert [s["stage"] for s in segs] == ["deep", "light", "rem"]


async def test_sleep_stages_null_when_no_raw_timeline(
    client: AsyncClient, db_session: AsyncSession
):
    await _login(client)
    user = await _owner_user(db_session)
    night_date = date.today()
    db_session.add(
        SleepSession(
            user_id=user.id,
            local_date=night_date,
            start_time=datetime(night_date.year, night_date.month, night_date.day, 23, 0, tzinfo=UTC),
            end_time=datetime(night_date.year, night_date.month, night_date.day, 7, 0, tzinfo=UTC) + timedelta(days=1),
            total_sleep_s=20000,
        )
    )
    await db_session.commit()
    resp = await client.get(f"/sleep/{night_date.isoformat()}/stages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["segments"] is None


# ----------------------------------------------------------- garmin connect


async def test_garmin_connect_mfa_then_success(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    await _login(client)

    from app.api import integrations as integrations_mod
    from app.api.integrations import _MfaRequired

    state = {"login_calls": 0, "codes": []}

    class FakeClient:
        def dump_tokens(self):
            return {"di_token": "tok", "di_refresh_token": "ref"}

    def fake_from_password(email, password, prompt_mfa):
        state["login_calls"] += 1
        code = prompt_mfa()  # raises _MfaRequired when the API got no code
        state["codes"].append(code)
        return FakeClient()

    monkeypatch.setattr(
        integrations_mod.LiveGarminClient,
        "from_password",
        staticmethod(fake_from_password),
    )

    # Step 1: no mfa code -> the login thread sees MFA required
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "a@b.c", "password": "pw"},
        headers=CSRF,
    )
    assert resp.status_code == 200
    assert resp.json()["mfa_required"] is True
    assert state["login_calls"] == 1

    # Step 2: with mfa code -> connected, tokens stored encrypted
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "a@b.c", "password": "pw", "mfa_code": "123456"},
        headers=CSRF,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["mfa_required"] is False
    assert state["codes"] == ["123456"]

    integration = (
        await db_session.execute(
            select(Integration).where(Integration.provider == "garmin")
        )
    ).scalars().first()
    await db_session.refresh(integration)
    assert integration is not None
    assert integration.status == "active"
    assert integration.credentials_encrypted is not None
    assert integration.last_synced_at is None


async def test_garmin_connect_bad_credentials_400(client: AsyncClient, monkeypatch):
    await _login(client)
    from app.api import integrations as integrations_mod
    from app.connectors.garmin.client import GarminAuthError

    def fail_login(email, password, prompt_mfa):
        raise GarminAuthError("Garmin login failed: nope")

    monkeypatch.setattr(
        integrations_mod.LiveGarminClient, "from_password", staticmethod(fail_login)
    )
    resp = await client.post(
        "/settings/integrations/garmin/connect",
        json={"email": "a@b.c", "password": "pw"},
        headers=CSRF,
    )
    assert resp.status_code == 400
    assert "Garmin connect failed" in resp.json()["detail"]


async def test_garmin_sync_now_requires_connection(client: AsyncClient):
    await _login(client)
    resp = await client.post("/settings/integrations/garmin/sync", headers=CSRF)
    assert resp.status_code == 400
