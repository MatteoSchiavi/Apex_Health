"""Personal ranges must not mix people/devices or assess against themselves."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.metrics import metric_trend
from app.models.lab import AthleteEntry
from app.models.wellness import SleepSession
from app.services.evidence import record_observation
from tests.test_garmin_sync import make_garmin_user

pytestmark = pytest.mark.asyncio
END = date(2026, 10, 5)


async def sample(session, user, day, value, device="watch-a"):
    measured = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=7)
    await record_observation(
        session, user_id=user.id, metric="hrv_overnight_rmssd", value=value,
        unit="ms", origin="garmin", source_record_id=f"{device}:{day}",
        measured_at=measured, timezone=user.timezone, fetched_at=measured,
        metadata={"device_id": device, "reading_context": "overnight"},
    )


async def test_personal_range_excludes_latest_and_other_accounts(db_session):
    user, _ = await make_garmin_user(db_session)
    other, _ = await make_garmin_user(db_session)
    for offset in range(1, 15):
        await sample(db_session, user, END - timedelta(days=offset), 60)
        await sample(db_session, other, END - timedelta(days=offset), 500)
    await sample(db_session, user, END, 100)
    result = await metric_trend("hrv_ms", user=user, session=db_session, days=7, end=END)
    assert result.reference_range["sample_count"] == 14
    assert result.reference_range["empirical_range"] == [60, 60]
    assert result.stats["latest"] == 100
    assert all(p.value in (60, 100) for p in result.points)
    assert result.start_date == "2026-09-29"


async def test_device_change_does_not_inherit_old_range(db_session):
    user, _ = await make_garmin_user(db_session)
    for offset in range(1, 15):
        await sample(db_session, user, END - timedelta(days=offset), 60)
    await sample(db_session, user, END, 90, device="watch-b")
    result = await metric_trend("hrv_ms", user=user, session=db_session, days=28, end=END)
    assert result.reference_range["sample_count"] == 0
    assert result.reference_range["empirical_range"] is None
    assert len(result.points) == 1
    # Explicit changes also reset ranges when the provider keeps the same ID.
    await sample(db_session, user, END + timedelta(days=1), 70, device="watch-b")
    db_session.add(AthleteEntry(user_id=user.id, kind="device_change", date=END + timedelta(days=1), payload={"metrics": ["hrv_overnight_rmssd"]}))
    await db_session.flush()
    result = await metric_trend("hrv_ms", user=user, session=db_session, days=28, end=END + timedelta(days=1))
    assert result.reference_range["sample_count"] == 0


async def test_sleep_metrics_select_the_same_whole_night(db_session):
    user, _ = await make_garmin_user(db_session)
    start = datetime(2026, 10, 4, 22, tzinfo=UTC)
    db_session.add_all([
        SleepSession(user_id=user.id, local_date=END, start_time=start,
                     end_time=start + timedelta(hours=8), total_sleep_s=30600, deep_s=3600, sleep_score=80),
        SleepSession(user_id=user.id, local_date=END, start_time=start + timedelta(hours=14),
                     end_time=start + timedelta(hours=16), total_sleep_s=7200, deep_s=5400, sleep_score=95),
    ])
    await db_session.flush()
    duration = await metric_trend("sleep_duration", user=user, session=db_session, days=7, end=END)
    deep = await metric_trend("sleep_deep", user=user, session=db_session, days=7, end=END)
    score = await metric_trend("provider_sleep_score", user=user, session=db_session, days=7, end=END)
    assert duration.stats["latest"] == 8.5
    assert deep.stats["latest"] == 1
    assert score.stats["latest"] == 80
