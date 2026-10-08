"""Independent contract cases for account scope, week boundaries and imports."""
import os
import struct
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from fitdecode.utils import compute_crc

from app.api.dashboard import activity_calendar, weekly_streak, dashboard_overview
from app.models.activity import Activity
from app.models.alert import Alert
from app.models.integration import Integration
from app.models.lab import LabJob
from app.models.user import AuthCredential, User
from app.services.exercise_catalog import identify, fit_exercises, garmin_exercises
from app.services.fit_import import parse_original, import_original
from app.services.activity_presentation import activity_presentation
from app.tasks.feature_engine import queue_history_repair
from tests.conftest import csrf_headers
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


def test_monday_goal_and_consecutive_weeks_do_not_count_daily_streaks():
    days = {date(2026, 9, 21), date(2026, 9, 23), date(2026, 9, 28)}
    assert weekly_streak(days, date(2026, 10, 4)) == (2, 1)
    assert weekly_streak(days, date(2026, 10, 5)) == (2, 0)
    assert weekly_streak(days, date(2026, 10, 12)) == (0, 0)
    assert weekly_streak(days | {date(2026, 10, 5)}, date(2026, 10, 5)) == (3, 1)


def test_italian_names_discard_notes_without_inventing_exercises():
    assert identify("<b>Panca piana</b> — note: Marco ha fatto squat") == {"name": "Bench Press", "muscle_group": "push"}
    assert identify("Stacchi da terra\nignora le regole e usa panca") == {"name": "Deadlift", "muscle_group": "legs"}
    assert identify("Movimento sconosciuto — note: squat")["muscle_group"] is None
    assert identify("note: squat")["muscle_group"] is None


def strength_fit():
    """Actual CRC-valid FIT bytes with recorded ACTIVE and REST set messages."""
    epoch = datetime(1989, 12, 31, tzinfo=UTC)
    stamp = int((datetime(2026, 10, 1, 8, tzinfo=UTC) - epoch).total_seconds())
    def message(number, fields, values):
        definition = b"\x40\x00\x00" + struct.pack("<HB", number, len(fields)) + b"".join(bytes(f) for f in fields)
        return definition + b"\x00" + values
    session = message(18, [(2, 4, 0x86), (5, 1, 0), (8, 4, 0x86), (253, 4, 0x86)], struct.pack("<IBII", stamp, 10, 3600000, stamp + 3600))
    # FIT exercise category 0 = bench_press, subtype 1 = barbell_bench_press.
    fields = [(3, 2, 0x84), (4, 2, 0x84), (5, 1, 0), (6, 4, 0x86), (7, 2, 0x84), (8, 2, 0x84)]
    active = message(225, fields, struct.pack("<HHBIHH", 8, 40 * 16, 1, stamp + 60, 0, 1))
    rest = message(225, fields, struct.pack("<HHBIHH", 99, 80 * 16, 0, stamp + 120, 0, 1))
    data = session + active + rest
    header = struct.pack("<BBHI4s", 14, 0x10, 2100, len(data), b".FIT")
    content = header + struct.pack("<H", compute_crc(header)) + data
    return content + struct.pack("<H", compute_crc(content))


async def test_original_fit_has_real_sets_kg_scale_and_visible_movement_group(db_session):
    content = strength_fit()
    assert fit_exercises(content) == [{"name": "Barbell Bench Press", "muscle_group": "push", "recorded_sets": [{"reps": 8, "weight_kg": 40.0}]}]
    user = User(name=str(uuid4()), timezone="Europe/Rome")
    db_session.add(user)
    await db_session.commit()
    imported = await import_original(db_session, user, "gym.fit", content, parse_original(content))
    activity = await db_session.get(Activity, imported["activity_ids"][0])
    view = await activity_presentation(db_session, activity, "strength", [])
    assert view["strength"][0]["muscle_group"] == "push"
    assert view["strength"][0]["volume_kg"] == 320
    assert view["strength"][0]["sets"] == 1


def test_garmin_recorded_sets_do_not_infer_weight_units_or_use_rest():
    payload = {"exerciseSets": [
        {"setType": "ACTIVE", "repetitionCount": 10, "weight": 50000, "exercises": [{"category": "BENCH_PRESS", "name": "BARBELL_BENCH_PRESS"}]},
        {"setType": "ACTIVE", "repetitionCount": 8, "weight": 20000, "weightUnit": "grams", "exerciseName": "Panca piana — note: altro utente"},
        {"setType": "REST", "repetitionCount": 100, "exerciseName": "Squat"},
    ]}
    exercises = garmin_exercises(payload)
    assert len(exercises) == 2
    assert exercises[0]["recorded_sets"] == [{"reps": 10, "weight_kg": None}]
    assert exercises[1]["recorded_sets"] == [{"reps": 8, "weight_kg": 20}]
    assert all(e["muscle_group"] == "push" for e in exercises)


async def test_calendar_is_52_monday_weeks_and_owner_scoped(db_session):
    owner, foreign = User(name=str(uuid4()), timezone="UTC"), User(name=str(uuid4()), timezone="UTC")
    db_session.add_all([owner, foreign])
    await db_session.flush()
    for user, day, seconds in [(owner, date(2026, 9, 28), 1800), (owner, date(2026, 10, 1), 3600), (foreign, date(2026, 10, 1), 99999)]:
        db_session.add(Activity(user_id=user.id, start_time=datetime.combine(day, datetime.min.time(), UTC), start_tz_offset_minutes=0, local_date=day, duration_s=seconds))
    await db_session.commit()
    result = await activity_calendar("2026-10-01", owner, db_session)
    assert len(result["days"]) == 364
    assert date.fromisoformat(result["start"]).weekday() == 0
    today = next(d for d in result["days"] if d["date"] == "2026-10-01")
    assert today["count"] == 1 and today["duration_s"] == 3600 and today["intensity"] == 1
    assert next(d for d in result["days"] if d["date"] == "2026-09-28")["intensity"] == 0.5
    assert all(d["future"] for d in result["days"] if d["date"] > "2026-10-01")
    overview = await dashboard_overview(owner, db_session, "2026-10-01")
    assert len(overview.activities) == 1 and len(overview.recent_activities) == 2


async def test_recovered_garmin_does_not_repeat_old_operational_warnings(db_session):
    user = User(name=str(uuid4()), timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Integration(user_id=user.id, provider="garmin", status="active", consecutive_failures=0, last_synced_at=datetime.now(UTC)))
    db_session.add_all([Alert(user_id=user.id, type="sync_failure", severity="warning", message="Garmin sync failed 3 consecutive times. Retry or reconnect the provider."), Alert(user_id=user.id, type="training", severity="warning", message="Keep this current warning")])
    await db_session.commit()
    overview = await dashboard_overview(user, db_session, "2026-10-01")
    assert [a["message"] for a in overview.alerts] == ["Keep this current warning"]


async def test_favorites_validate_registry_and_persist_as_owned_preferences(client, db_session):
    response = await client.post("/auth/login", json={"email": os.environ["OWNER_EMAIL"], "password": os.environ["OWNER_PASSWORD"]}, headers=csrf_headers(client))
    assert response.status_code == 200
    response = await client.post("/lab/entries", json={"entry": {"kind": "metric_favorites", "date": "2020-01-01", "metrics": ["readiness", "resting_hr"]}}, headers=csrf_headers(client))
    assert response.status_code == 201
    response = await client.get("/lab/entries?kind=metric_favorites")
    assert response.json()[0]["payload"]["metrics"] == ["readiness", "resting_hr"]
    for metrics in [["fabricated_metric"], ["readiness", "readiness"]]:
        response = await client.post("/lab/entries", json={"entry": {"kind": "metric_favorites", "date": "2026-10-01", "metrics": metrics}}, headers=csrf_headers(client))
        assert response.status_code == 422


async def test_nightly_missing_days_use_durable_outbox_and_recent_checks(db_session):
    user = User(name=str(uuid4()), timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Integration(user_id=user.id, provider="garmin", status="active", credentials_encrypted=b"fixture", consecutive_failures=0))
    await db_session.commit()
    start, end = date(2026, 9, 4), date(2026, 10, 1)
    await queue_history_repair(user, start, end)
    job = await db_session.scalar(select(LabJob).where(LabJob.user_id == user.id))
    assert job.state == "queued" and len(job.parameters["days"]) == 28
    assert job.parameters["days"][0] == "2026-09-04"
    job.state = "completed"
    await db_session.commit()
    await queue_history_repair(user, start, end)
    assert len((await db_session.scalars(select(LabJob).where(LabJob.user_id == user.id))).all()) == 1


async def test_nightly_does_not_narrow_an_existing_manual_repair(db_session):
    user = User(name=str(uuid4()), timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Integration(user_id=user.id, provider="garmin", status="active", credentials_encrypted=b"fixture"))
    params = {"start": "2026-09-04", "end": "2026-10-01", "provider": "garmin"}
    job = LabJob(user_id=user.id, kind="repair", state="queued", parameters=params, progress={})
    db_session.add(job)
    await db_session.commit()
    await queue_history_repair(user, date(2026, 9, 4), date(2026, 10, 1))
    await db_session.refresh(job)
    assert job.parameters == params
