"""Seeder for the golden-dataset world (tests/fixtures/golden).

Loads the fixture JSON and writes its rows through the ORM exactly the way
the Phase 1 normalizer would have (§17: local_date derived from the user's
timezone; streams immutable rows). Tests then run the feature engine over
the world and compare against the hand-computed expectations.
"""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityStream
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "golden_dataset.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


async def seed_golden_world(session: AsyncSession) -> tuple[User, dict]:
    """Truncate domain tables, then insert the golden world. Returns
    (user, fixture)."""
    from sqlalchemy import text

    # feature_weights_backup_test does not exist (guard against typos in the
    # truncate list); keep the real statement minimal:
    await session.execute(
        text(
            "TRUNCATE daily_features, discipline_features, activities, "
            "activity_streams, activity_source_links, raw_ingest, "
            "sleep_sessions, hrv_readings, stress_readings, daily_biometrics, "
            "alerts RESTART IDENTITY CASCADE"
        )
    )
    fixture = load_fixture()
    user = User(
        name=fixture["user"]["name"],
        dob=date.fromisoformat(fixture["user"]["dob"]),
        timezone=fixture["user"]["timezone"],
    )
    session.add(user)
    await session.flush()
    tz = ZoneInfo(user.timezone)

    disciplines = {
        name: id
        for id, name in (
            row
            for row in (await session.execute(text("SELECT id, name FROM disciplines"))).all()
        )
    }

    for row in fixture["sleep_sessions"]:
        session.add(
            SleepSession(
                user_id=user.id,
                local_date=datetime.fromisoformat(row["end"]).astimezone(tz).date(),
                start_time=datetime.fromisoformat(row["start"]),
                end_time=datetime.fromisoformat(row["end"]),
                total_sleep_s=row["total_sleep_s"],
                deep_s=row["deep_s"],
                light_s=row["light_s"],
                rem_s=row["rem_s"],
                awake_s=row["awake_s"],
                sleep_score=row["sleep_score"],
                respiration_avg=row["respiration_avg"],
            )
        )
    for row in fixture["hrv_readings"]:
        session.add(
            HrvReading(
                user_id=user.id,
                timestamp=datetime.fromisoformat(row["timestamp"]),
                hrv_ms=row["hrv_ms"],
                # §6.4 CHECK: ('overnight_avg','5min')
                reading_type="overnight_avg",
            )
        )
    for row in fixture["daily_biometrics"]:
        session.add(
            DailyBiometric(
                user_id=user.id,
                date=date.fromisoformat(row["date"]),
                resting_hr=row["resting_hr"],
            )
        )
    for row in fixture["activities"]:
        start = datetime.fromisoformat(row["start"])
        local_date = start.astimezone(tz).date()  # §17, as the normalizer does
        activity = Activity(
            user_id=user.id,
            discipline_id=disciplines[row["discipline"]],
            start_time=start,
            start_tz_offset_minutes=row["tz_offset_minutes"],
            local_date=local_date,
            duration_s=row["duration_s"],
            distance_m=row.get("distance_m"),
            avg_hr=row.get("avg_hr"),
            training_load=row.get("training_load"),
            data_completeness="full",
        )
        session.add(activity)
        await session.flush()
        streams = row.get("streams")
        if streams:
            for i, t in enumerate(streams["t"]):
                session.add(
                    ActivityStream(
                        activity_id=activity.id,
                        t_offset_s=t,
                        hr=streams["hr"][i],
                        power=streams["power"][i] if "power" in streams else None,
                    )
                )
    await session.commit()
    return user, fixture
