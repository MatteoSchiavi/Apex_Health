"""Garmin arrivals and re-syncs preserve an explicitly chosen main device."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.connectors.garmin.normalize import normalize_raw_row
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.integration import Integration, RawIngest
from app.models.user import User
from app.models.wellness import DailyBiometric

DAY = datetime(2026, 9, 21, tzinfo=UTC).date()
AT = datetime(2026, 9, 21, 8, tzinfo=UTC)
TZ = ZoneInfo("Europe/Rome")


async def make_user(session, *, choose_whoop=True):
    user = User(name="main-device-priority", timezone=TZ.key)
    session.add(user)
    await session.flush()
    whoop = Integration(user_id=user.id, provider="whoop", status="active")
    garmin = Integration(user_id=user.id, provider="garmin", status="active")
    session.add_all([whoop, garmin])
    await session.flush()
    if choose_whoop:
        user.main_integration_id = whoop.id
    await session.commit()
    return user


async def ingest(session, user, kind, payload, disciplines=None):
    raw = RawIngest(user_id=user.id, source="garmin", payload_type=kind,
                    raw_json=payload, fetched_at=AT, processed=False)
    session.add(raw)
    await session.flush()
    await normalize_raw_row(session, raw, TZ, disciplines or {})
    await session.flush()
    return raw


async def seed_activity(session, user, *, source="whoop"):
    discipline = await session.scalar(select(Discipline).where(Discipline.name == "running"))
    activity = Activity(user_id=user.id, discipline_id=discipline.id,
                        start_time=AT, start_tz_offset_minutes=120, local_date=DAY,
                        duration_s=3600, avg_hr=150, max_hr=180, calories=600,
                        data_completeness="partial", source_metrics={"whoop": {"strain": 14}})
    session.add(activity)
    await session.flush()
    session.add(ActivitySourceLink(user_id=user.id, activity_id=activity.id,
                                  source=source, external_id=f"{source}-primary"))
    await session.flush()
    return activity, {"running": discipline.id}


def summary(**overrides):
    return {
        "activityId": 73001, "startTimeGMT": "2026-09-21 08:02:00",
        "activityType": {"typeKey": "running"}, "duration": 3650,
        "averageHR": 165, "maxHR": 190, "calories": 700,
        "distance": 10000, "averagePower": 220, "manual": False,
        **overrides,
    }


async def test_whoop_main_daily_values_survive_garmin_resync_and_gaps_fill(db_session):
    user = await make_user(db_session)
    row = DailyBiometric(user_id=user.id, date=DAY, resting_hr=50,
                         spo2_avg=98, weight_kg=76, steps=100)
    db_session.add(row)
    await db_session.flush()
    for steps in (1000, 2000):
        await ingest(db_session, user, f"stats:{DAY}", {
            "restingHeartRate": 60, "averageSpo2": 94, "totalSteps": steps,
            "floorsAscended": 8,
        })
        await ingest(db_session, user, f"body_composition:{DAY}", {
            "totalAverage": {"weight": 81000, "bodyFat": 18},
        })
    assert row.resting_hr == 50 and float(row.spo2_avg) == 98
    assert float(row.weight_kg) == 76
    assert row.steps == 2000 and row.floors == 8 and float(row.body_fat_pct) == 18
    row.spo2_avg = None
    await ingest(db_session, user, f"stats:{DAY}", {"averageSpo2": 96})
    assert float(row.spo2_avg) == 96


async def test_default_garmin_daily_values_update_without_explicit_main(db_session):
    user = await make_user(db_session, choose_whoop=False)
    row = DailyBiometric(user_id=user.id, date=DAY, resting_hr=50,
                         spo2_avg=98, weight_kg=76)
    db_session.add(row)
    await db_session.flush()
    await ingest(db_session, user, f"stats:{DAY}", {
        "restingHeartRate": 60, "averageSpo2": 94,
    })
    await ingest(db_session, user, f"body_composition:{DAY}", {
        "totalAverage": {"weight": 81000},
    })
    assert row.resting_hr == 60 and float(row.spo2_avg) == 94 and float(row.weight_kg) == 81


async def test_garmin_arrival_and_resync_keep_whoop_main_activity_fields(db_session):
    user = await make_user(db_session)
    activity, index = await seed_activity(db_session, user)
    for heart_rate in (165, 170):
        await ingest(db_session, user, "activity_summary", summary(averageHR=heart_rate), index)
    assert await db_session.scalar(select(func.count()).select_from(Activity).where(Activity.user_id == user.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id)) == 2
    assert activity.avg_hr == 150 and activity.max_hr == 180
    assert activity.calories == 600 and activity.duration_s == 3600 and activity.start_time == AT
    assert float(activity.distance_m) == 10000 and float(activity.avg_power) == 220
    assert activity.source_metrics["whoop"]["strain"] == 14


async def test_garmin_only_effort_still_updates_when_whoop_main_has_no_link(db_session):
    user = await make_user(db_session)
    index = {"running": await db_session.scalar(select(Discipline.id).where(Discipline.name == "running"))}
    await ingest(db_session, user, "activity_summary", summary(), index)
    await ingest(db_session, user, "activity_summary", summary(averageHR=170), index)
    activity = await db_session.scalar(select(Activity).where(Activity.user_id == user.id))
    assert activity.avg_hr == 170


async def test_default_garmin_hr_preference_remains_without_explicit_main(db_session):
    user = await make_user(db_session, choose_whoop=False)
    activity, index = await seed_activity(db_session, user)
    await ingest(db_session, user, "activity_summary", summary(), index)
    assert activity.avg_hr == 165 and activity.max_hr == 190


async def test_explicit_incoming_main_replaces_secondary_fields_in_shared_reconciliation(db_session):
    from app.connectors.reconciliation import reconcile_activity

    user = await make_user(db_session)
    activity, index = await seed_activity(db_session, user, source="garmin")
    await reconcile_activity(
        db_session, existing=activity,
        incoming_values={"avg_hr": 155, "calories": 620, "duration_s": 3700,
                         "start_time": datetime(2026, 9, 21, 8, 1, tzinfo=UTC),
                         "distance_m": None},
        source="whoop", external_id="whoop-selected-main", raw_ingest_id=None,
    )
    assert activity.avg_hr == 155 and activity.calories == 620 and activity.duration_s == 3700
    assert activity.start_time == datetime(2026, 9, 21, 8, 1, tzinfo=UTC)
    assert activity.source_metrics["_merged_fields"]["avg_hr"] == "whoop"
