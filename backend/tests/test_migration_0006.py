"""Migration 0006 acceptance: multi-device + coach + social layer.

- 'whoop' joins the integrations.provider CHECK ('strava' was pre-allowed)
- activities/daily_biometrics gain source_metrics JSONB
- the 9 new capability tables exist (calendar, context docs, gym detail,
  feedback, challenges)
- the gym exercise catalog seeds idempotently
"""

import pytest
from sqlalchemy import text

from tests.test_migrations import EXPECTED_TABLES

NEW_TABLES = {
    "user_events",
    "user_context_docs",
    "gym_exercises",
    "gym_day_plans",
    "gym_day_exercises",
    "gym_set_logs",
    "session_feedback",
    "challenges",
    "challenge_members",
}


async def test_expected_tables_include_0006(db_session):
    rows = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    actual = {r[0] for r in rows.all()} - {"alembic_version"}
    assert actual == EXPECTED_TABLES  # exact-equality law
    assert NEW_TABLES <= actual


async def test_whoop_provider_is_accepted(db_session):
    await db_session.execute(
        text(
            "INSERT INTO integrations (user_id, provider) "
            "SELECT id, 'whoop' FROM users ORDER BY id LIMIT 1"
        )
    )
    await db_session.commit()
    provider = await db_session.scalar(
        text("SELECT provider FROM integrations WHERE provider='whoop' LIMIT 1")
    )
    assert provider == "whoop"


async def test_source_metrics_columns_exist(db_session):
    for table in ("activities", "daily_biometrics"):
        rows = await db_session.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name='{table}'"
            )
        )
        cols = {name: dtype for name, dtype in rows.all()}
        assert cols.get("source_metrics") == "jsonb", table


async def test_gym_exercise_catalog_seeded(db_session):
    count = await db_session.scalar(text("SELECT count(*) FROM gym_exercises"))
    assert count >= 30
    high_impact = await db_session.scalar(
        text("SELECT count(*) FROM gym_exercises WHERE impact_level='high'")
    )
    assert high_impact >= 3  # plyo work the advisor can drop
    groups = await db_session.execute(
        text("SELECT DISTINCT muscle_group FROM gym_exercises")
    )
    assert {r[0] for r in groups.all()} == {"legs", "push", "pull", "core", "full_body"}


async def test_new_timestamps_are_tz_aware(db_session):
    """The §17 day-boundary law holds for the 0006 tables too (the global
    migration test asserts repo-wide; this pins the new tables)."""
    rows = await db_session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND data_type='timestamp without time zone'"
        )
    )
    assert rows.all() == []
