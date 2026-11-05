"""Synthetic historical response-shape compatibility tests.

All measurements, identifiers and dates below are fabricated constants.
No response captured from a Garmin account is included. The tests retain
coverage for ISO HRV timestamps, array stress readings and structured empty
sleep responses, alongside the older canonical shapes.
"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.connectors.garmin import fetch
from app.connectors.garmin.normalize import normalize_raw_row
from app.models.wellness import HrvReading, SleepSession, StressReading
from tests.test_garmin_sync import make_garmin_user

pytestmark = pytest.mark.asyncio
SYNTHETIC_DAY = "2025-02-02"
SYNTHETIC_EPOCH_MS = int(datetime(2025, 2, 1, 20, tzinfo=UTC).timestamp() * 1000)

HRV_ISO = {
    "hrvSummary": {"calendarDate": SYNTHETIC_DAY, "lastNightAvg": 45, "baseline": None},
    "hrvReadings": [
        {"hrvValue": 41, "readingTimeGMT": "2025-02-01T20:00:00.0"},
        {"hrvValue": 43, "readingTimeGMT": "2025-02-01T20:05:00.0"},
        {"hrvValue": 47, "readingTimeGMT": "2025-02-01T20:10:00.0"},
    ],
}
STRESS_ARRAYS = {
    "calendarDate": SYNTHETIC_DAY,
    "stressValuesArray": [[SYNTHETIC_EPOCH_MS, 21], [SYNTHETIC_EPOCH_MS + 300000, 31], [SYNTHETIC_EPOCH_MS + 600000, 41]],
    "bodyBatteryValuesArray": [[SYNTHETIC_EPOCH_MS, 61]],
}
SLEEP_NO_DATA = {
    "sleepLevels": [], "remSleepData": None,
    "dailySleepDTO": {"id": None, "calendarDate": SYNTHETIC_DAY, "napTimeSeconds": None,
                      "remSleepSeconds": None, "deepSleepSeconds": None, "sleepTimeSeconds": None},
}

async def _normalize(session, user_id, payload_type, payload):
    raw = await fetch.store_raw(session, user_id, payload_type, payload)
    await normalize_raw_row(session, raw, ZoneInfo("Europe/Rome"), {})
    return raw


async def test_hrv_iso_timestamps_normalize(db_session):
    user, _ = await make_garmin_user(db_session)
    raw = await _normalize(db_session, user.id, "hrv", HRV_ISO)
    rows = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    assert sorted(float(r.hrv_ms) for r in rows if r.reading_type == "5min") == [41.0, 43.0, 47.0]
    overnight = [r for r in rows if r.reading_type == "overnight_avg"]
    assert len(overnight) == 1 and float(overnight[0].hrv_ms) == 45.0
    assert overnight[0].timestamp == datetime(2025, 2, 1, 20, 10, tzinfo=UTC)
    assert raw.processed


async def test_hrv_summary_without_samples_is_not_discarded(db_session):
    from app.connectors.garmin.sync import _wellness_payload_has_content
    user, _ = await make_garmin_user(db_session)
    payload = {"hrvSummary": {"calendarDate": SYNTHETIC_DAY, "lastNightAvg": 51, "baseline": {"avg": 49}}, "hrvReadings": []}
    assert _wellness_payload_has_content("hrv", payload)
    raw = await _normalize(db_session, user.id, "hrv", payload)
    rows = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    assert len(rows) == 1 and rows[0].reading_type == "overnight_avg"
    assert float(rows[0].hrv_ms) == 51 and float(rows[0].rolling_baseline_ms) == 49
    assert rows[0].timestamp.date().isoformat() == SYNTHETIC_DAY
    assert raw.processed


async def test_stress_value_arrays_normalize(db_session):
    user, _ = await make_garmin_user(db_session)
    raw = await _normalize(db_session, user.id, "stress", STRESS_ARRAYS)
    rows = (await db_session.scalars(select(StressReading).where(StressReading.user_id == user.id))).all()
    assert len(rows) == 3 and {r.stress_level for r in rows} == {21.0, 31.0, 41.0}
    assert [r.body_battery for r in rows if r.body_battery is not None] == [61.0]
    assert raw.processed


async def test_structured_no_recording_day_is_clean_skip(db_session):
    user, _ = await make_garmin_user(db_session)
    before = (await db_session.scalars(select(SleepSession))).all()
    raw = await _normalize(db_session, user.id, "sleep", SLEEP_NO_DATA)
    after = (await db_session.scalars(select(SleepSession))).all()
    assert len(after) == len(before) and raw.processed


async def test_legacy_shapes_still_normalize(db_session):
    user, _ = await make_garmin_user(db_session)
    hrv = {"hrvSummary": {"lastNightAvg": 53, "baseline": {"avg": 46}},
           "hrvReadings": [{"timestamp": SYNTHETIC_EPOCH_MS, "hrvValue": 57}]}
    stress = {"stressGraph": [{"timestamp": SYNTHETIC_EPOCH_MS, "stressLevel": 33}],
              "bodyBatteryChart": [{"timestamp": SYNTHETIC_EPOCH_MS, "value": 63}]}
    raw_h = await _normalize(db_session, user.id, "hrv", hrv)
    raw_s = await _normalize(db_session, user.id, "stress", stress)
    hrv_rows = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    stress_rows = (await db_session.scalars(select(StressReading).where(StressReading.user_id == user.id))).all()
    assert {float(r.hrv_ms) for r in hrv_rows} == {53.0, 57.0}
    assert len(stress_rows) == 1 and stress_rows[0].stress_level == 33.0
    assert stress_rows[0].body_battery == 63.0
    assert raw_h.processed and raw_s.processed
