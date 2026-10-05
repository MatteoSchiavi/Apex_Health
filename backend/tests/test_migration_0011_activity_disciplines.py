"""Run migration 0011 against isolated populated accounts and raw records."""

import os
import subprocess
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def test_activity_sport_repair_uses_owned_linked_payload_and_device_priority():
    base = make_url(os.environ["DATABASE_URL"])
    name = f"apex_migration_{uuid4().hex}"
    admin = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = base.set(database=name)
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(target)
    env = {**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False)}

    def migrate(*args):
        return subprocess.run(["uv", "run", "alembic", *args], env=env, capture_output=True)

    try:
        assert migrate("upgrade", "0010").returncode == 0
        async with engine.begin() as connection:
            # Account A: Strava is main, so its known type wins over Garmin's
            # conflicting raw type on the same canonical activity.
            garmin_user = await connection.scalar(text("""
                INSERT INTO users(name) VALUES ('garmin-main') RETURNING id
            """))
            await connection.scalar(text("""
                INSERT INTO integrations(user_id, provider) VALUES (:user, 'garmin') RETURNING id
            """), {"user": garmin_user})
            strava_integration = await connection.scalar(text("""
                INSERT INTO integrations(user_id, provider) VALUES (:user, 'strava') RETURNING id
            """), {"user": garmin_user})
            await connection.execute(text("""
                UPDATE users SET main_integration_id = :integration WHERE id = :user
            """), {"integration": strava_integration, "user": garmin_user})
            garmin_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, discipline_id, start_time, start_tz_offset_minutes,
                    local_date, duration_s)
                VALUES (:user, (SELECT id FROM disciplines WHERE name='enduro'), now(), 0, current_date, 3600)
                RETURNING id
            """), {"user": garmin_user})
            garmin_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'garmin', 'activity_summary',
                    '{"activityId": "g-1", "activityType": {"typeKey": "mountain_biking"}}'::jsonb)
                RETURNING id
            """), {"user": garmin_user})
            strava_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'strava', 'activity_summary',
                    '{"id": "s-1", "sport_type": "Sail"}'::jsonb)
                RETURNING id
            """), {"user": garmin_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'garmin', 'g-1', :raw)
            """), {"user": garmin_user, "activity": garmin_activity, "raw": garmin_raw})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'strava', 's-1', :raw)
            """), {"user": garmin_user, "activity": garmin_activity, "raw": strava_raw})

            # Account B: no selected main device. Garmin's unknown raw label
            # wins fallback priority, clears its old gym/enduro guess, and
            # blocks a lower priority Whoop guess.
            fallback_user = await connection.scalar(text("""
                INSERT INTO users(name) VALUES ('fallback-priority') RETURNING id
            """))
            fallback_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, discipline_id, start_time, start_tz_offset_minutes,
                    local_date, duration_s)
                VALUES (:user, (SELECT id FROM disciplines WHERE name='enduro'), now(), 0, current_date, 3600)
                RETURNING id
            """), {"user": fallback_user})
            unknown_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'garmin', 'activity_summary',
                    '{"activityId": "g-2", "activityType": {"typeKey": "triathlon"}}'::jsonb)
                RETURNING id
            """), {"user": fallback_user})
            whoop_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'whoop', 'workout', '{"id": "w-2", "sport_name": "mountain_biking"}'::jsonb)
                RETURNING id
            """), {"user": fallback_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'garmin', 'g-2', :raw)
            """), {"user": fallback_user, "activity": fallback_activity, "raw": unknown_raw})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'whoop', 'w-2', :raw)
            """), {"user": fallback_user, "activity": fallback_activity, "raw": whoop_raw})

            # Account C: raw link points to another account's raw record. It
            # must not be used to reclassify this activity.
            other_user = await connection.scalar(text("""
                INSERT INTO users(name) VALUES ('other-owner') RETURNING id
            """))
            unlinked_owner_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, discipline_id, start_time, start_tz_offset_minutes,
                    local_date, duration_s)
                VALUES (:user, (SELECT id FROM disciplines WHERE name='enduro'), now(), 0, current_date, 3600)
                RETURNING id
            """), {"user": fallback_user})
            owner_mismatch_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'strava', 'activity_summary', '{"id": "s-3", "sport_type": "MountainBikeRide"}'::jsonb)
                RETURNING id
            """), {"user": other_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'strava', 's-3', :raw)
            """), {"user": fallback_user, "activity": unlinked_owner_activity, "raw": owner_mismatch_raw})

            whoop_user = await connection.scalar(text("""
                INSERT INTO users(name) VALUES ('whoop-walking') RETURNING id
            """))
            whoop_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, discipline_id, start_time, start_tz_offset_minutes,
                    local_date, duration_s)
                VALUES (:user, (SELECT id FROM disciplines WHERE name='gym_general'), now(), 0, current_date, 1800)
                RETURNING id
            """), {"user": whoop_user})
            walking_raw = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'whoop', 'workout', '{"id": "w-4", "sport_name": "walking"}'::jsonb)
                RETURNING id
            """), {"user": whoop_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'whoop', 'w-4', :raw)
            """), {"user": whoop_user, "activity": whoop_activity, "raw": walking_raw})

            # Unknown sport and NULL stay unknown; existing sailing seed stays
            # one row and linked raw payloads remain byte-for-byte JSON data.
            null_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, start_time, start_tz_offset_minutes, local_date, duration_s)
                VALUES (:user, now(), 0, current_date, 3600) RETURNING id
            """), {"user": other_user})
            manual_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, discipline_id, start_time, start_tz_offset_minutes,
                    local_date, duration_s, data_completeness)
                VALUES (:user, (SELECT id FROM disciplines WHERE name='gym_general'),
                    now(), 0, current_date, 1200, 'manual') RETURNING id
            """), {"user": other_user})
            unknown_strava = await connection.scalar(text("""
                INSERT INTO raw_ingest(user_id, source, payload_type, raw_json)
                VALUES (:user, 'strava', 'activity_summary', '{"id": "s-5", "sport_type": "CheeseRolling"}'::jsonb)
                RETURNING id
            """), {"user": other_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id, raw_ingest_id)
                VALUES (:user, :activity, 'strava', 's-5', :raw)
            """), {"user": other_user, "activity": null_activity, "raw": unknown_strava})
            sailing_id = await connection.scalar(text("SELECT id FROM disciplines WHERE name='sailing'"))

        upgraded = migrate("upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr.decode(errors="replace")
        async with engine.connect() as connection:
            rows = await connection.execute(text("""
                SELECT a.id, d.name FROM activities a
                LEFT JOIN disciplines d ON d.id = a.discipline_id
                WHERE a.id = ANY(:ids)
            """), {"ids": [garmin_activity, fallback_activity, unlinked_owner_activity, whoop_activity, null_activity, manual_activity]})
            sports = dict(rows.all())
            assert sports[garmin_activity] == "sailing"
            assert sports[fallback_activity] is None
            assert sports[unlinked_owner_activity] == "enduro"
            assert sports[whoop_activity] == "walking"
            assert sports[null_activity] is None
            assert sports[manual_activity] == "gym_general"
            assert await connection.scalar(text("SELECT count(*) FROM disciplines WHERE name='sailing'")) == 1
            assert await connection.scalar(text("SELECT raw_json->>'sport_type' FROM raw_ingest WHERE id=:id"), {"id": unknown_strava}) == "CheeseRolling"

        # Downgrade restores prior classes from the reversible snapshot and
        # preserves activity rows. New seed rows without references are removed.
        downgraded = migrate("downgrade", "0010")
        assert downgraded.returncode == 0, downgraded.stderr.decode(errors="replace")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM activities")) == 6
            restored = await connection.execute(text("""
                SELECT a.id, d.name FROM activities a LEFT JOIN disciplines d ON d.id=a.discipline_id
                WHERE a.id = ANY(:ids)
            """), {"ids": [garmin_activity, fallback_activity, unlinked_owner_activity, whoop_activity, null_activity, manual_activity]})
            restored_sports = dict(restored.all())
            assert restored_sports[garmin_activity] == "enduro"
            assert restored_sports[fallback_activity] == "enduro"
            assert restored_sports[unlinked_owner_activity] == "enduro"
            assert restored_sports[whoop_activity] == "gym_general"
            assert restored_sports[null_activity] is None
            assert restored_sports[manual_activity] == "gym_general"
            assert await connection.scalar(text("SELECT count(*) FROM disciplines WHERE name='sailing'")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM disciplines WHERE name='mountain_biking'")) == 0
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
