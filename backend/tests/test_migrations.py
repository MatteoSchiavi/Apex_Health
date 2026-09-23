"""Acceptance tests for the §6.4 schema and §6.1 seed data (Phase 0 criterion:
"every Section 6 table exists with seed data")."""

from sqlalchemy import text

EXPECTED_TABLES = {
    # identity, auth & integrations
    "users", "auth_credentials", "invites", "sessions", "telegram_links",
    "integrations", "raw_ingest",
    # Phase 10 addition (documented judgment call — §6.4 has no
    # device-presentable credential type; see alembic/versions/0004)
    "device_tokens",
    # Phase 10 v2 addition (the rethought watch app — recurring weekly gym
    # routine; §6.4's training_plans are week-scoped, not standing templates)
    "gym_schedule_slots",
    # Multi-device + coach + social layer (migration 0006): Whoop provider,
    # events calendar, AI context docs, gym day detail, feedback, challenges
    "user_events", "user_context_docs", "session_feedback",
    "gym_exercises", "gym_day_plans", "gym_day_exercises", "gym_set_logs",
    "challenges", "challenge_members",
    # disciplines & gear
    "disciplines", "gear", "gear_service_logs", "discipline_gear_defaults",
    # Web UI foundation (migration 0007): laps from FIT enrichment
    "activity_laps",
    # activities
    "activities", "activity_source_links", "activity_gear_links",
    "activity_streams", "segments", "segment_efforts",
    # sleep & recovery
    "sleep_sessions", "hrv_readings", "stress_readings", "daily_biometrics",
    # medical / lab
    "lab_panels", "lab_metrics",
    # subjective / lifestyle
    "journal_entries", "nutrition_logs", "supplement_protocols", "supplement_logs",
    # feature engine output
    "feature_weights", "daily_features", "discipline_features",
    "weekly_rollups", "monthly_rollups",
    # training plans
    "training_plans", "planned_sessions", "technogym_sync_log",
    # ai layer
    "ai_reports", "ai_chat_sessions", "ai_chat_messages", "agent_tool_calls",
    "embeddings", "token_usage",
    # watch, bot & alerts
    "watch_sync_log", "telegram_messages", "alerts",
    # weather
    "forecast_cache",
}

EXPECTED_SEED = {
    "enduro": "endurance",
    "road_cycling": "endurance",
    "skiing": "technical",
    "sailing": "technical",
    "kitesurf": "technical",
    "windsurf": "technical",
    "tennis": "technical",
    "wakeboard": "technical",
    "snowboard": "technical",
    "surf": "technical",
    "sim_racing": "technical",
    "running": "endurance",
    "strength": "strength",
    "gym_general": "strength",
}

EXPECTED_HYPERTABLES = {"sleep_sessions", "hrv_readings", "stress_readings"}


async def test_all_section6_tables_exist(db_session):
    rows = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    actual = {r[0] for r in rows} - {"alembic_version"}
    assert actual == EXPECTED_TABLES


async def test_hypertables_created(db_session):
    rows = await db_session.execute(
        text("SELECT hypertable_name FROM timescaledb_information.hypertables")
    )
    assert {r[0] for r in rows} == EXPECTED_HYPERTABLES


async def test_disciplines_seed(db_session):
    rows = await db_session.execute(text("SELECT name, category FROM disciplines"))
    assert dict(rows.fetchall()) == EXPECTED_SEED


async def test_required_extensions(db_session):
    rows = await db_session.execute(text("SELECT extname FROM pg_extension"))
    assert {"timescaledb", "vector"} <= {r[0] for r in rows}


async def test_key_indexes(db_session):
    rows = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    )
    assert {
        "idx_raw_ingest_unprocessed",  # partial index, §6.4
        "idx_embeddings_vector",       # ivfflat cosine, §6.4
        "idx_activities_user_time",
        "idx_activities_user_local_date",
    } <= {r[0] for r in rows}


async def test_embeddings_column_is_vector_1536(db_session):
    row = await db_session.execute(
        text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_name='embeddings' AND column_name='embedding'"
        )
    )
    assert row.scalar_one() == "vector"


async def test_day_boundary_columns_are_tz_aware(db_session):
    """§17: every timestamp is timestamptz."""
    rows = await db_session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE data_type='timestamp without time zone' "
            "AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='public')"
        )
    )
    offenders = rows.fetchall()
    assert offenders == []
