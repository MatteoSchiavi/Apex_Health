"""garminconnect 0.3.x response-shape regression tests.

The first LIVE connect (owner's real account, 2026-09-22) caught three
shape changes the recorded fixtures never showed:

- hrv readings: readingTimeGMT ISO strings instead of epoch-ms timestamps
- stress: stressGraph -> stressValuesArray with [epoch_ms, level] pairs
- no-recording days: structured payloads with null fields instead of {}

Fixtures here are trimmed variants of REAL 0.3.x payloads (user id scrubbed).
Both the legacy and the 0.3.x shapes must normalize — the raw-first design
(§3) makes every already-stored raw row replayable, so a parser fix
recovers data without re-fetching.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.connectors.garmin import fetch
from app.connectors.garmin.normalize import normalize_raw_row
from app.models.integration import RawIngest
from app.models.wellness import HrvReading, SleepSession, StressReading

from tests.test_garmin_sync import make_garmin_user

pytestmark = pytest.mark.asyncio

HRV_03X = {
    "hrvSummary": {
        "status": "NONE",
        "baseline": None,
        "weeklyAvg": 77,
        "calendarDate": "2026-09-21",
        "lastNightAvg": 75,
        "feedbackPhrase": "ONBOARDING_1",
        "createTimeStamp": "2026-09-21T05:18:01.618",
        "lastNight5MinHigh": 114,
    },
    "hrvReadings": [
        {"hrvValue": 70, "readingTimeGMT": "2026-09-20T21:25:02.0"},
        {"hrvValue": 68, "readingTimeGMT": "2026-09-20T21:30:02.0"},
        {"hrvValue": 64, "readingTimeGMT": "2026-09-20T21:35:02.0"},
    ],
    "userProfilePk": 1,
    "startTimestampGMT": "2026-09-20T21:00:00.0",
    "endTimestampGMT": "2026-09-21T09:00:00.0",
}

STRESS_03X = {
    "calendarDate": "2026-09-21",
    "userProfilePK": 1,
    "avgStressLevel": 24,
    "maxStressLevel": 95,
    "endTimestampGMT": "2026-09-21T22:00:00.0",
    "startTimestampGMT": "2026-09-20T22:00:00.0",
    "stressValuesArray": [
        [1789941600000, 14],
        [1789941780000, 9],
        [1789941960000, 11],
    ],
    "bodyBatteryValuesArray": [[1789941600000, 55]],
}

SLEEP_03X_NO_DATA = {
    "sleepLevels": [],
    "remSleepData": None,
    "dailySleepDTO": {
        "id": None,
        "retro": False,
        "calendarDate": "2026-09-11",
        "userProfilePK": 1,
        "napTimeSeconds": None,
        "remSleepSeconds": None,
        "deepSleepSeconds": None,
        "sleepTimeSeconds": None,
        "sleepResultTypePK": None,
    },
}


async def _store(session, user_id, payload_type, payload):
    return await fetch.store_raw(session, user_id, payload_type, payload)


async def _normalize_one(session, user_id, raw_row):
    from zoneinfo import ZoneInfo

    await normalize_raw_row(session, raw_row, ZoneInfo("Europe/Rome"), {})


async def test_hrv_03x_iso_timestamps_normalize(db_session):
    user, _ = await make_garmin_user(db_session)
    raw = await _store(db_session, user.id, "hrv", HRV_03X)
    await _normalize_one(db_session, user.id, raw)
    rows = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    values = sorted(float(r.hrv_ms) for r in rows if r.reading_type == "5min")
    assert values == [64.0, 68.0, 70.0]
    # overnight average anchored at the last 5-min reading
    overnight = [r for r in rows if r.reading_type == "overnight_avg"]
    assert len(overnight) == 1 and float(overnight[0].hrv_ms) == 75.0
    assert raw.processed is True


async def test_stress_03x_value_arrays_normalize(db_session):
    user, _ = await make_garmin_user(db_session)
    raw = await _store(db_session, user.id, "stress", STRESS_03X)
    await _normalize_one(db_session, user.id, raw)
    rows = (
        await db_session.scalars(select(StressReading).where(StressReading.user_id == user.id))
    ).all()
    assert len(rows) == 3
    by_level = {r.stress_level for r in rows}
    assert by_level == {14.0, 9.0, 11.0}
    body_battery = [r.body_battery for r in rows if r.body_battery is not None]
    assert body_battery == [55.0]
    assert raw.processed is True


async def test_sleep_03x_no_recording_day_is_clean_skip(db_session):
    user, _ = await make_garmin_user(db_session)
    raw = await _store(db_session, user.id, "sleep", SLEEP_03X_NO_DATA)
    before = (await db_session.scalars(select(SleepSession))).all()
    await _normalize_one(db_session, user.id, raw)
    after = (await db_session.scalars(select(SleepSession))).all()
    assert len(after) == len(before)  # nothing stored, nothing raised
    assert raw.processed is True


async def test_legacy_shapes_still_normalize(db_session):
    """The fixture-era shapes must keep working alongside 0.3.x."""
    user, _ = await make_garmin_user(db_session)
    hrv_legacy = {
        "hrvSummary": {"lastNightAvg": 40, "baseline": {"avg": 38}},
        "hrvReadings": [{"timestamp": 1789941600000, "hrvValue": 41}],
    }
    stress_legacy = {
        "stressGraph": [{"timestamp": 1789941600000, "stressLevel": 30}],
        "bodyBatteryChart": [{"timestamp": 1789941600000, "value": 60}],
    }
    raw_h = await _store(db_session, user.id, "hrv", hrv_legacy)
    raw_s = await _store(db_session, user.id, "stress", stress_legacy)
    await _normalize_one(db_session, user.id, raw_h)
    await _normalize_one(db_session, user.id, raw_s)
    hrv_rows = (await db_session.scalars(select(HrvReading).where(HrvReading.user_id == user.id))).all()
    stress_rows = (
        await db_session.scalars(select(StressReading).where(StressReading.user_id == user.id))
    ).all()
    assert {float(r.hrv_ms) for r in hrv_rows} == {41.0, 40.0}
    assert len(stress_rows) == 1 and stress_rows[0].stress_level == 30.0
