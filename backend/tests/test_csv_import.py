"""CSV import tests: workouts CSV, daily metrics CSV, idempotency, and the
Apple Health header vocabulary."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.activity import Activity
from app.models.wellness import DailyBiometric, HrvReading
from app.services.csv_import import import_csv

WORKOUTS_CSV = """Workout Type,Start Time,End Time,Distance (km),Energy Burned (kcal),Average Heart Rate (bpm),Max Heart Rate (bpm)
Running,2026-09-15 07:30:00,2026-09-15 08:15:00,8.2,610,148,171
Strength Training,2026-09-16 18:00:00,2026-09-16 19:00:00,,280,120,155
"""

DAILY_CSV = """date,steps,weight (kg),resting heart rate (bpm),hrv (ms),spo2 (%)
2026-09-15,11234,76.2,52,98.4,96.8
2026-09-16,9876,76.0,53,101.2,97.1
"""


@pytest.fixture(autouse=True)
async def clean_csv_tables(db_session):
    from sqlalchemy import text

    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "daily_biometrics, hrv_readings RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def make_user(db_session) -> int:
    from app.models.user import User

    user = User(name="csv-importer")
    db_session.add(user)
    await db_session.commit()
    return user.id


async def test_workouts_csv_imports_activities(db_session):
    user_id = await make_user(db_session)
    report = await import_csv(db_session, user_id, "export.csv", WORKOUTS_CSV)
    assert report.activities_upserted == 2
    assert report.errors == []

    rows = (await db_session.scalars(select(Activity).order_by(Activity.start_time))).all()
    assert len(rows) == 2
    run = rows[0]
    assert run.duration_s == 2700
    assert run.distance_m == 8200
    assert run.calories == 610
    assert run.avg_hr == 148 and run.max_hr == 171
    assert run.data_completeness == "manual"
    gym = rows[1]
    assert gym.duration_s == 3600
    assert gym.distance_m is None
    assert gym.source_metrics["csv_import"]["sport_raw"] == "Strength Training"


async def test_import_is_idempotent(db_session):
    user_id = await make_user(db_session)
    await import_csv(db_session, user_id, "export.csv", WORKOUTS_CSV)
    report = await import_csv(db_session, user_id, "export.csv", WORKOUTS_CSV)
    assert report.activities_upserted == 0
    assert report.skipped == 2
    assert await db_session.scalar(select(__import__("sqlalchemy").func.count()).select_from(Activity)) == 2


async def test_daily_csv_merges_biometrics_and_hrv(db_session):
    user_id = await make_user(db_session)
    report = await import_csv(db_session, user_id, "daily.csv", DAILY_CSV)
    assert report.biometrics_upserted == 2
    assert report.hrv_upserted == 2

    bios = (
        (
            await db_session.scalars(
                select(DailyBiometric).order_by(DailyBiometric.date)
            )
        )
        .all()
    )
    assert len(bios) == 2
    assert bios[0].steps == 11234
    assert float(bios[0].weight_kg) == 76.2
    assert bios[0].resting_hr == 52
    assert float(bios[0].spo2_avg) == 96.8

    hrvs = (
        (
            await db_session.scalars(
                select(HrvReading).order_by(HrvReading.timestamp)
            )
        )
        .all()
    )
    assert len(hrvs) == 2
    assert hrvs[0].reading_type == "overnight_avg"
    assert float(hrvs[0].hrv_ms) == 98.4
    # timestamptz comes back in UTC; the stored instant is 07:00 Europe/Rome
    assert hrvs[0].timestamp.astimezone(ZoneInfo("Europe/Rome")).hour == 7


async def test_unrecognized_shape_is_reported_not_thrown(db_session):
    user_id = await make_user(db_session)
    report = await import_csv(db_session, user_id, "x.csv", "foo,bar\n1,2\n")
    assert report.rows_seen == 0
    assert report.errors and "unrecognized" in report.errors[0]
