"""Synthetic Oura v2 records shaped from the verified public OpenAPI 1.41.

These are contract fixtures, not recordings or evidence of live account access.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from zoneinfo import ZoneInfo

from app.connectors.garmin.normalize import NormalizerStats
from app.connectors.oura.fetch import store_raw
from app.connectors.oura.normalize import NormalizationError, normalize_raw_row
from app.connectors.oura.sync import sync_user_oura
from app.models.ai import AiReport
from app.models.integration import Integration
from app.models.lab import FeedState, Observation
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401

SCORE = {"id": "score-1", "day": "2026-10-01", "timestamp": "2026-10-01T00:00:00+02:00", "score": 83,
         "contributors": {"deep_sleep": 91, "rem_sleep": 82, "total_sleep": 80}}
SLEEP = {"id": "period-1", "day": "2026-10-01", "type": "long_sleep", "bedtime_start": "2026-09-30T23:02:00+02:00",
         "bedtime_end": "2026-10-01T07:02:00+02:00", "total_sleep_duration": 27000,
         "deep_sleep_duration": 5000, "light_sleep_duration": 16000, "rem_sleep_duration": 6000,
         "awake_time": 1800, "average_hrv": 54, "average_heart_rate": 61, "lowest_heart_rate": 45,
         "average_breath": 14, "ring_id": "ring-1", "sleep_phase_5_min": "441223"}


def test_default_oauth_scopes_match_official_schema_and_implemented_feeds():
    from app.core.config import Settings
    # Official OpenAPI 1.41 components.securitySchemes.OAuth2 authorizationCode.
    allowed = {"email", "personal", "daily", "heartrate", "workout", "tag", "session", "spo2", "heart_health"}
    requested = set(Settings(_env_file=None).oura_scope.split())
    assert requested <= allowed
    assert requested == {"daily", "heartrate", "personal"}


async def owner(db_session):
    user = User(name=str(uuid4()), timezone="Europe/Rome")
    db_session.add(user)
    await db_session.flush()
    return user


async def normalize(session, user, kind, payload):
    raw = await store_raw(session, user.id, kind, payload, fetched_at=datetime(2026, 10, 2, tzinfo=UTC))
    stats = NormalizerStats()
    await normalize_raw_row(session, raw, payload, ZoneInfo(user.timezone), stats)
    raw.processed = True
    await session.flush()
    return raw, stats


async def test_real_schema_uses_period_durations_not_daily_contributor_scores(db_session):
    user = await owner(db_session)
    await normalize(db_session, user, "daily_sleep", SCORE)
    assert await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id)) is None
    await normalize(db_session, user, "sleep", SLEEP)
    night = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id))
    assert night.total_sleep_s == 27000
    assert night.deep_s == 5000 and night.light_s == 16000 and night.rem_s == 6000
    assert float(night.sleep_score) == 83
    assert str(night.local_date) == "2026-10-01"
    hrv = await db_session.scalar(select(HrvReading).where(HrvReading.user_id == user.id))
    assert hrv.timestamp == datetime.fromisoformat(SLEEP["bedtime_end"])
    assert float(hrv.hrv_ms) == 54 and hrv.origin == "oura"
    assert await db_session.scalar(select(DailyBiometric).where(DailyBiometric.user_id == user.id)) is None
    measurements = (await db_session.scalars(select(Observation).where(Observation.user_id == user.id, Observation.current))).all()
    assert {r.metric for r in measurements} == {"sleep_duration", "sleep_score", "hrv_overnight_rmssd", "respiration"}
    assert next(r for r in measurements if r.metric == "sleep_duration").value == {"value": 7.5}
    assert all(r.origin == "oura" and r.raw_ingest_id for r in measurements)


async def test_score_corrections_and_hrv_values_refresh_without_merging_foreign_nights(db_session):
    user, foreign = await owner(db_session), await owner(db_session)
    for account in (user, foreign):
        await normalize(db_session, account, "sleep", SLEEP)
    await normalize(db_session, user, "daily_sleep", {**SCORE, "score": 90})
    await normalize(db_session, user, "sleep", {**SLEEP, "average_hrv": 62})
    owner_night = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id))
    foreign_night = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == foreign.id))
    assert float(owner_night.sleep_score) == 90 and foreign_night.sleep_score is None
    assert float(await db_session.scalar(select(HrvReading.hrv_ms).where(HrvReading.user_id == user.id))) == 62
    assert float(await db_session.scalar(select(HrvReading.hrv_ms).where(HrvReading.user_id == foreign.id))) == 54


async def test_upstream_deleted_sleep_removes_owned_data_and_cached_reports(db_session):
    user, foreign = await owner(db_session), await owner(db_session)
    for account in (user, foreign):
        await normalize(db_session, account, "sleep", SLEEP)
        db_session.add(AiReport(user_id=account.id, report_type="daily", period_start=datetime(2026, 10, 1).date(), period_end=datetime(2026, 10, 1).date(), content_md="A cached measurement"))
    await db_session.flush()
    await normalize(db_session, user, "sleep", {**SLEEP, "type": "deleted"})
    for model in (SleepSession, HrvReading, Observation, AiReport):
        assert await db_session.scalar(select(model).where(model.user_id == user.id)) is None
        assert await db_session.scalar(select(model).where(model.user_id == foreign.id)) is not None


async def test_undated_profile_and_continuous_hr_do_not_invent_resting_hr_or_weight_days(db_session):
    user = await owner(db_session)
    await normalize(db_session, user, "personal_info", {"id": "profile", "weight": 82, "height": 1.8})
    await normalize(db_session, user, "heartrate", {"timestamp": "2026-10-01T09:00:00Z", "bpm": 70, "source": "awake"})
    assert await db_session.scalar(select(DailyBiometric).where(DailyBiometric.user_id == user.id)) is None
    feed = await db_session.scalar(select(FeedState).where(FeedState.user_id == user.id, FeedState.feed == "continuous_hr"))
    assert feed.availability == "not_supported" and feed.details["storage"] == "raw_only"


async def test_naive_sleep_times_are_rejected_without_guessing_utc(db_session):
    user = await owner(db_session)
    with pytest.raises(NormalizationError):
        await normalize(db_session, user, "sleep", {**SLEEP, "bedtime_start": "2026-09-30T23:02:00"})


async def test_sync_populates_real_sleep_and_evidence_instead_of_accepting_an_empty_fixture(db_session):
    user = await owner(db_session)
    integration = Integration(user_id=user.id, provider="oura", status="active")
    db_session.add(integration)
    await db_session.flush()
    class Client:
        async def fetch_daily_sleep(self, *args): return [SCORE]
        async def fetch_sleep_periods(self, *args): return [SLEEP]
        async def fetch_heartrate(self, *args): return []
        async def fetch_personal_info(self): return {"id": "profile", "weight": 82}
    report = await sync_user_oura(db_session, user, integration, Client(), now=datetime(2026, 10, 2, tzinfo=UTC))
    assert report.raw_rows_unprocessed == 0 and report.stats.sleep_upserted == 1
    assert await db_session.scalar(select(Observation).where(Observation.user_id == user.id, Observation.metric == "sleep_duration")) is not None


async def test_retimed_period_and_nap_correction_remove_obsolete_overnight_hrv(db_session):
    user = await owner(db_session)
    await normalize(db_session, user, "sleep", SLEEP)
    corrected = {**SLEEP, "bedtime_end": "2026-10-01T08:02:00+02:00"}
    await normalize(db_session, user, "sleep", corrected)
    readings = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    assert len(readings) == 1 and readings[0].timestamp == datetime.fromisoformat(corrected["bedtime_end"])
    await normalize(db_session, user, "sleep", {**corrected, "type": "sleep"})
    assert await db_session.scalar(select(HrvReading).where(HrvReading.user_id == user.id)) is None
    assert await db_session.scalar(select(Observation).where(Observation.user_id == user.id, Observation.metric == "hrv_overnight_rmssd")) is None


async def test_hypnogram_uses_selected_provider_and_exact_owned_period(db_session):
    from app.api.sleep import sleep_stages
    from datetime import date
    user = await owner(db_session)
    # 96 five-minute epochs cover eight hours. The first ten minutes are awake.
    await normalize(db_session, user, "sleep", {**SLEEP, "sleep_phase_5_min": "44" + "2" * 94})
    result = await sleep_stages(date(2026, 10, 1), user, db_session)
    assert result.source == "oura" and len(result.segments) == 2
    assert result.segments[0]["stage"] == "awake"
    assert datetime.fromisoformat(result.segments[0]["t_start"]) == datetime.fromisoformat(SLEEP["bedtime_start"])
    assert datetime.fromisoformat(result.segments[0]["t_end"]).minute == 12
    assert datetime.fromisoformat(result.segments[-1]["t_end"]) == datetime.fromisoformat(SLEEP["bedtime_end"])


def test_partial_phase_string_is_not_stretched_to_a_full_night():
    from app.connectors.oura.stages import extract_sleep_stage_segments
    assert extract_sleep_stage_segments(SLEEP) is None


async def test_operator_replay_repairs_processed_history_without_crossing_source_or_owner(db_session):
    from datetime import date
    from tools.replay_oura import replay
    user, foreign = await owner(db_session), await owner(db_session)
    for account in (user, foreign):
        # Simulate old code that marked a provider period processed without
        # creating a canonical night. The original payload remains available.
        raw = await store_raw(db_session, account.id, "sleep", SLEEP, fetched_at=datetime(2026, 10, 2, tzinfo=UTC))
        raw.processed = True
    result = await replay(db_session, user, date(2026, 10, 1), date(2026, 10, 1))
    assert result["replayed"] == 1
    assert await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id)) is not None
    assert await db_session.scalar(select(SleepSession).where(SleepSession.user_id == foreign.id)) is None
    assert await db_session.scalar(select(HrvReading.hrv_ms).where(HrvReading.user_id == user.id)) == 54


async def test_oura_awake_totals_cannot_borrow_matching_garmin_epochs(db_session):
    from app.models.integration import RawIngest
    from app.services.sleep_summary import recorded_awake_totals
    user = await owner(db_session)
    await normalize(db_session, user, "sleep", {**SLEEP, "awake_time": 0})
    night = await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id))
    db_session.add(RawIngest(user_id=user.id, source="garmin", payload_type="sleep", raw_json={
        "dailySleepDTO": {"sleepStartTimestampGMT": int(night.start_time.timestamp() * 1000),
                         "sleepLevels": [{"activityLevel": 0, "startGMT": night.start_time.isoformat(), "endGMT": night.end_time.isoformat()}]}}))
    await db_session.flush()
    assert await recorded_awake_totals(db_session, [night]) == {}


async def test_replay_honors_latest_deletion_even_if_provider_day_changed(db_session):
    from datetime import date
    from tools.replay_oura import replay
    user = await owner(db_session)
    await normalize(db_session, user, "sleep", SLEEP)
    await normalize(db_session, user, "sleep", {**SLEEP, "day": "2026-09-30", "type": "deleted"})
    assert await db_session.scalar(select(SleepSession).where(SleepSession.user_id == user.id)) is None
    await replay(db_session, user, date(2026, 10, 1), date(2026, 10, 1))
    for model in (SleepSession, HrvReading, Observation):
        assert await db_session.scalar(select(model).where(model.user_id == user.id)) is None
