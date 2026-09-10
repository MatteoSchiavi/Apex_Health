"""Phase 1 acceptance tests — Garmin connector (§23 Phase 1).

AC1: fixture-based sync populates normalized tables.
AC2: running it twice does not duplicate rows.
Plus: §17 day-boundary rule, raw-first law, parser-isolates-history, §19
pacing + 6-hourly beat, §21 escalation, app-layer credential encryption.

No test touches the live Garmin API — every client here is fixture-backed
or failing-on-purpose (§0, §16.7, §20).
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.connectors.garmin.sync import run_user_sync_with_escalation
from app.connectors.garmin.type_map import resolve_type_key
from app.core.encryption import decrypt_json, encrypt_json
from app.models.activity import (
    Activity,
    ActivitySourceLink,
    ActivityStream,
    Discipline,
)
from app.models.integration import Integration, RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession, StressReading
from tests.helpers.fixture_client import (
    FailingGarminClient,
    FixtureGarminClient,
)

# The fixture world's "now": syncs run against this instant.
SYNC_NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
PAGE_SIZE = 3  # forces the 4-activity corpus onto two pages


@pytest_asyncio.fixture(autouse=True)
async def clean_sync_tables(db_session):
    """Sync-domain tables are global-unique keyed ((source, external_id)) and
    shared across tests in one schema build — truncate between tests."""
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "activity_streams, sleep_sessions, hrv_readings, stress_readings, "
            "daily_biometrics, integrations, alerts RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def make_garmin_user(session, tz: str = "Europe/Rome") -> tuple[User, Integration]:
    user = User(name="garmin-athlete", timezone=tz)
    session.add(user)
    await session.flush()
    integration = Integration(user_id=user.id, provider="garmin", status="active")
    session.add(integration)
    await session.commit()
    return user, integration


def sync_kwargs() -> dict:
    return dict(page_size=PAGE_SIZE, page_delay_s=0.0, empty_gap_days=10)


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def fetch_user(session) -> User:
    return await session.scalar(select(User).where(User.name == "garmin-athlete"))


async def fetch_integration(session) -> Integration:
    return await session.scalar(select(Integration).where(Integration.provider == "garmin"))


# ---------------------------------------------------------------- AC1: populate


async def test_backfill_populates_normalized_tables(db_session):
    user, integration = await make_garmin_user(db_session)
    client = FixtureGarminClient()

    report = await run_user_sync_with_escalation(
        db_session, user, integration, client, now=SYNC_NOW, **sync_kwargs()
    )

    assert report is not None and report.mode == "backfill"

    # --- raw-first law (§17): 4 summaries + 2 streams + 8 wellness payloads
    assert report.raw_rows_stored == 14
    raw_total = await count(db_session, RawIngest)
    assert raw_total == 14

    unprocessed = (
        (await db_session.scalars(select(RawIngest).where(RawIngest.processed.is_(False))))
        .all()
    )
    assert len(unprocessed) == 1  # the malformed 03-02 sleep drill (§3)
    assert unprocessed[0].payload_type == "sleep"

    processed_rows = (
        await db_session.scalars(select(RawIngest).where(RawIngest.processed.is_(True)))
    ).all()
    assert len(processed_rows) == 13
    # raw payloads are stored byte-pure: no injected metadata keys
    summary_rows = (
        await db_session.scalars(
            select(RawIngest).where(RawIngest.payload_type == "activity_summary")
        )
    ).all()
    assert all("calendar_date" not in r.raw_json for r in summary_rows)

    # --- activities + idempotency keys (source, external_id)
    assert await count(db_session, Activity) == 4
    links = (await db_session.scalars(select(ActivitySourceLink))).all()
    assert len(links) == 4
    assert all(l.source == "garmin" and l.raw_ingest_id is not None for l in links)

    by_external = {
        l.external_id: await db_session.get(Activity, l.activity_id) for l in links
    }

    # discipline mapping via type_map
    disc = {
        d.name: d.id for d in (await db_session.scalars(select(Discipline))).all()
    }
    assert by_external["7101"].discipline_id == disc["running"]
    assert by_external["7102"].discipline_id == disc["road_cycling"]
    assert by_external["7103"].discipline_id == disc["strength"]
    # 7104 'walking' -> generic bucket (explicitly MAPPED in type_map),
    # manual-entry completeness
    assert by_external["7104"].discipline_id == disc["gym_general"]

    # §17 day-boundary rule: 23:30 GMT start = 00:30 in Rome -> LOCAL next day
    act = by_external["7104"]
    assert act.start_time == datetime(2025, 3, 8, 23, 30, tzinfo=UTC)
    assert str(act.local_date) == "2025-03-09"
    assert act.start_tz_offset_minutes == 60
    assert act.data_completeness == "manual"

    run = by_external["7101"]
    assert str(run.local_date) == "2025-03-08"
    assert float(run.distance_m) == 12400.0
    assert run.avg_hr == 151
    assert float(run.training_load) == 82.0
    assert run.data_completeness == "full"

    # --- streams: 6 run samples (gap-filler skipped) + 4 ride samples
    assert await count(db_session, ActivityStream) == 10
    first = await db_session.get(ActivityStream, (by_external["7101"].id, 0))
    assert first.hr == 148
    assert first.lat == pytest.approx(45.5530, abs=1e-6)  # semicircles converted
    ride_row = await db_session.get(ActivityStream, (by_external["7102"].id, 600))
    assert ride_row.power == pytest.approx(231.0)
    assert ride_row.lat == pytest.approx(45.902, abs=1e-9)  # degrees kept as-is

    # --- sleep: wake-up day is the local_date (§17)
    sleeps = (await db_session.scalars(select(SleepSession))).all()
    assert len(sleeps) == 1
    s = sleeps[0]
    assert s.start_time == datetime(2025, 3, 8, 22, 30, tzinfo=UTC)
    assert s.end_time == datetime(2025, 3, 9, 6, 40, tzinfo=UTC)
    assert str(s.local_date) == "2025-03-09"
    assert s.deep_s == 4800 and s.rem_s == 4600 and s.total_sleep_s == 24900
    assert float(s.sleep_score) == 79

    # --- hrv: 4 x 5min + 1 overnight_avg (same timestamp, distinct type)
    hrvs = (await db_session.scalars(select(HrvReading).order_by(HrvReading.timestamp))).all()
    assert len(hrvs) == 5
    overnight = [h for h in hrvs if h.reading_type == "overnight_avg"]
    assert len(overnight) == 1
    assert float(overnight[0].hrv_ms) == 45.2
    five_min_same_ts = [
        h for h in hrvs if h.reading_type == "5min" and h.timestamp == overnight[0].timestamp
    ]
    assert len(five_min_same_ts) == 1 and float(five_min_same_ts[0].hrv_ms) == 44

    # --- stress with body battery joined by timestamp
    stress = (await db_session.scalars(select(StressReading))).all()
    assert len(stress) == 2
    midday = next(r for r in stress if r.timestamp.hour == 13)
    assert float(midday.stress_level) == 58 and float(midday.body_battery) == 71

    # --- daily biometrics (weight grams -> kg; vo2max from activities)
    bio = (await db_session.scalars(select(DailyBiometric).order_by(DailyBiometric.date))).all()
    assert len(bio) == 2
    d8, d9 = bio  # ascending date order
    assert str(d9.date) == "2025-03-09" and str(d8.date) == "2025-03-08"
    assert d9.resting_hr == 49 and d9.steps == 11020 and d9.floors == 8
    assert d9.weight_kg == pytest.approx(71.6) and d9.body_fat_pct == pytest.approx(12.9)
    assert d9.vo2max == pytest.approx(52.4)  # from the Alpine Ride
    assert d8.vo2max == pytest.approx(49.3)  # from the Morning Trail Run

    # --- integration bookkeeping
    assert integration.last_synced_at == SYNC_NOW
    assert integration.consecutive_failures == 0


# ------------------------------------------------------------- AC2: idempotent


async def test_second_sync_does_not_duplicate_rows(db_session):
    user, integration = await make_garmin_user(db_session)
    first = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert first is not None and first.mode == "backfill"
    activity_ids_before = sorted(
        (await db_session.scalars(select(Activity.id))).all()
    )
    sleep9_before = (
        await db_session.scalars(
            select(SleepSession).where(SleepSession.local_date == datetime(2025, 3, 9).date())
        )
    ).one()
    hrv_ids_before = {
        h.timestamp: h.id
        for h in (
            await db_session.scalars(
                select(HrvReading).where(HrvReading.reading_type == "5min")
            )
        ).all()
    }

    # Second run at the same instant: last_synced_at is set, so it is an
    # incremental pass whose window re-covers the tail by design — overlap
    # must be absorbed by upserts, never duplicated.
    second = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert second is not None and second.mode == "incremental"

    # activities: page re-fetched, rows UPDATED in place — same 4 ids
    assert await count(db_session, Activity) == 4
    assert sorted((await db_session.scalars(select(Activity.id))).all()) == activity_ids_before
    assert await count(db_session, ActivitySourceLink) == 4
    assert await count(db_session, ActivityStream) == 10  # no new activities -> untouched

    # sleep: the 03-09 row is the SAME row (id stable); the only other row is
    # the genuinely new 03-10 session pulled in by the incremental window
    assert await count(db_session, SleepSession) == 2
    sleep9_after = (
        await db_session.scalars(
            select(SleepSession).where(SleepSession.local_date == datetime(2025, 3, 9).date())
        )
    ).one()
    assert sleep9_after.id == sleep9_before.id

    # hrv: 5 existing readings keep their ids; +8 distinct new ones (03-10 —
    # its night starts 23:00Z on 03-09, which is correct per the wake-date rule)
    assert await count(db_session, HrvReading) == 13
    hrv_ids_after = {
        h.timestamp: h.id
        for h in (
            await db_session.scalars(
                select(HrvReading).where(
                    HrvReading.reading_type == "5min",
                    HrvReading.timestamp < datetime(2025, 3, 9, 12, 0, tzinfo=UTC),
                )
            )
        ).all()
    }
    assert hrv_ids_after == hrv_ids_before

    assert await count(db_session, StressReading) == 6  # 2 + 4 new
    assert await count(db_session, DailyBiometric) == 3  # 2 + 03-10

    # raw trail grows by design (+3 re-fetched summaries, +10 wellness in window)
    assert await count(db_session, RawIngest) == 14 + 13
    # the malformed 03-02 row is OUTSIDE the incremental window: still exactly 1
    unprocessed_count = len(
        (await db_session.scalars(select(RawIngest).where(RawIngest.processed.is_(False)))).all()
    )
    assert unprocessed_count == 1

    assert integration.last_synced_at == SYNC_NOW


async def test_incremental_sync_fetches_minimally_and_populates_new_day(db_session):
    user, integration = await make_garmin_user(db_session)
    await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(), now=SYNC_NOW, **sync_kwargs()
    )

    # 6 hours later (§19 cadence): the newest stored activity is 03-09 17:30 GMT,
    # so one activity page suffices and no streams are refetched.
    later_now = SYNC_NOW + timedelta(hours=6)
    client2 = FixtureGarminClient()
    report = await run_user_sync_with_escalation(
        db_session,
        user,
        integration,
        client2,
        now=later_now,
        **{**sync_kwargs(), "page_delay_s": 0.0},
    )

    assert report is not None and report.mode == "incremental"
    assert client2.activity_calls == [(0, 3)]  # boundary reached inside page 0
    assert client2.stream_calls == []  # nothing new -> no stream fetches

    # wellness window (last synced local day - 1 .. today) pulls in the
    # session that woke up on 03-10 and that day's aggregates
    assert await count(db_session, SleepSession) == 2
    s10 = (await db_session.scalars(select(SleepSession).where(SleepSession.local_date == datetime(2025, 3, 10).date()))).one()
    assert s10.start_time == datetime(2025, 3, 9, 22, 14, tzinfo=UTC)
    assert float(s10.sleep_score) == 84
    assert await count(db_session, HrvReading) == 13  # +7 5min +1 overnight on 03-10
    assert await count(db_session, StressReading) == 6
    bio10 = await db_session.scalar(
        select(DailyBiometric).where(DailyBiometric.date == datetime(2025, 3, 10).date())
    )
    assert bio10.resting_hr == 47 and bio10.steps == 14230
    assert bio10.weight_kg == pytest.approx(71.5)
    assert bio10.vo2max is None  # no activity that day -> no new estimate


# ------------------------------------------------- parser isolates history (§3)


def test_type_key_resolution_maps_and_falls_back():
    """Mapped keys resolve by name; unknown keys use the documented fallback
    bucket and are flagged so unmapped upstream types stay visible."""
    index = {"running": 1, "gym_general": 2}
    assert resolve_type_key("trail_running", index) == (1, "mapped")
    assert resolve_type_key("walking", index) == (2, "mapped")
    assert resolve_type_key("triathlon", index) == (2, "fallback")
    assert resolve_type_key(None, index) == (2, "fallback")


async def test_malformed_payload_stays_unprocessed_others_normalize(db_session):
    user, integration = await make_garmin_user(db_session)
    report = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert report is not None
    assert report.raw_rows_unprocessed == 1
    assert report.stats is not None
    # every non-malformed payload still normalized
    assert report.stats.activities_upserted == 4
    assert report.stats.sleep_upserted == 1


# ------------------------------------------------------------- §19 pacing


async def test_remote_calls_are_paced(db_session):
    user, integration = await make_garmin_user(db_session)
    started = datetime.now(UTC)
    report = await run_user_sync_with_escalation(
        db_session,
        user,
        integration,
        FixtureGarminClient(),
        now=SYNC_NOW,
        **{**sync_kwargs(), "page_delay_s": 0.02},
    )
    elapsed = (datetime.now(UTC) - started).total_seconds()
    # every remote call is paced: 1 inter-page + 4 stream fetches + paces
    # between the 18-day backfill wellness walk (last day not followed by one)
    assert report is not None and report.wellness_days == 18
    assert elapsed >= 22 * 0.02


# ------------------------------------------------- §21 escalation + §22 secrets


async def test_three_consecutive_failures_fire_sync_failure_alert_then_reset(db_session):
    user, integration = await make_garmin_user(db_session)

    from app.models.alert import Alert

    for attempt in range(1, 4):
        report = await run_user_sync_with_escalation(
            db_session, user, integration, FailingGarminClient(), **sync_kwargs()
        )
        assert report is None
    assert integration.consecutive_failures == 3
    alerts = (await db_session.scalars(select(Alert).where(Alert.type == "sync_failure"))).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert "3 consecutive" in alerts[0].message

    # non-multiples of three do not re-fire
    await run_user_sync_with_escalation(
        db_session, user, integration, FailingGarminClient(), **sync_kwargs()
    )
    assert integration.consecutive_failures == 4
    assert len((await db_session.scalars(select(Alert).where(Alert.type == "sync_failure"))).all()) == 1

    # a successful sync resets the counter
    ok = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureGarminClient(), **sync_kwargs()
    )
    assert ok is not None
    assert integration.consecutive_failures == 0


async def test_credentials_encrypt_before_touching_disk(db_session):
    secrets = {"oauth1": {"token": "a1b2c3"}, "oauth2": {"access_token": "x9y8z7"}}
    ciphertext = encrypt_json(secrets)
    assert isinstance(ciphertext, bytes)
    assert b"a1b2c3" not in ciphertext and b"x9y8z7" not in ciphertext
    assert decrypt_json(ciphertext) == secrets


# --------------------------------------------------------------- §19 beat entry


def test_beat_schedule_runs_garmin_sync_every_6h():
    from celery.schedules import crontab

    from app.tasks.celery_app import celery_app
    from app.tasks.garmin_sync import sync_all_garmin  # noqa: F401 — registers the task

    assert "garmin.sync_all" in celery_app.tasks
    entry = celery_app.conf.beat_schedule["garmin-sync-every-6h"]
    assert entry["task"] == "garmin.sync_all"
    assert entry["schedule"] == crontab(minute=0, hour="*/6")
