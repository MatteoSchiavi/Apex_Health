"""Shared database isolation for tests that touch the application domain."""

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture(autouse=True)
async def clean_domain_tables(db_session):
    """Keep domain rows isolated between tests that opt into this helper."""
    await db_session.execute(
        text(
            "TRUNCATE athlete_profiles, athlete_session_checkins, activity_plan_links, plan_document_drafts, lab_observations, lab_feed_states, change_drafts, decision_records, lab_notifications, athlete_entries, analysis_results, lab_jobs, lab_documents, change_audit, activities, activity_source_links, activity_streams, "
            "activity_gear_links, alerts, ai_chat_messages, ai_chat_sessions, "
            "daily_biometrics, daily_features, discipline_features, "
            "discipline_gear_defaults, gear, gear_service_logs, hrv_readings, "
            "integrations, journal_entries, lab_metrics, lab_panels, "
            "nutrition_logs, segments, segment_efforts, sleep_sessions, "
            "stress_readings, supplement_logs, supplement_protocols, "
            "telegram_links, telegram_messages, training_plans, planned_sessions, "
            "technogym_sync_log, watch_sync_log, weekly_rollups, monthly_rollups, "
            "embeddings, token_usage, agent_tool_calls, forecast_cache "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield
