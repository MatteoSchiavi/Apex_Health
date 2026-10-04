"""Exercise an upgrade with populated 0008 data in a separate database."""

import os
import subprocess
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def test_populated_upgrade_preserves_links_and_downgrade_refuses_collisions():
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
        assert migrate("upgrade", "0008").returncode == 0
        async with engine.begin() as connection:
            user = await connection.scalar(text("INSERT INTO users(name) VALUES ('migration-one') RETURNING id"))
            activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, start_time, start_tz_offset_minutes, local_date, duration_s)
                VALUES (:user, now(), 0, current_date, 100) RETURNING id
            """), {"user": user})
            link = await connection.scalar(text("""
                INSERT INTO activity_source_links(activity_id, source, external_id)
                VALUES (:activity, 'garmin', 'shared-id') RETURNING id
            """), {"activity": activity})
        assert migrate("upgrade", "head").returncode == 0
        async with engine.begin() as connection:
            assert (await connection.execute(text(
                "SELECT id, activity_id, user_id FROM activity_source_links"
            ))).one() == (link, activity, user)
            second_user = await connection.scalar(text("INSERT INTO users(name) VALUES ('migration-two') RETURNING id"))
            second_activity = await connection.scalar(text("""
                INSERT INTO activities(user_id, start_time, start_tz_offset_minutes, local_date, duration_s)
                VALUES (:user, now(), 0, current_date, 200) RETURNING id
            """), {"user": second_user})
            await connection.execute(text("""
                INSERT INTO activity_source_links(user_id, activity_id, source, external_id)
                VALUES (:user, :activity, 'garmin', 'shared-id')
            """), {"user": second_user, "activity": second_activity})
        rejected = migrate("downgrade", "0008")
        assert rejected.returncode != 0
        assert b"Cannot downgrade" in rejected.stderr
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM activity_source_links")) == 2
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
        # Once collisions are absent the downgrade path remains usable.
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM activity_source_links WHERE user_id = :user"), {"user": second_user})
        assert migrate("downgrade", "0008").returncode == 0
        assert migrate("upgrade", "head").returncode == 0
    finally:
        await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
