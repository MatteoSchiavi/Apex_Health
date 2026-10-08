"""Account-owned calculation and explanation invalidation after data changes."""
from datetime import timedelta
from sqlalchemy import delete, text


async def invalidate_calculation_dates(session, user_id, changed_days):
    """Caller holds changes; scores can use inputs from the prior 28 days."""
    from app.models.features import DailyFeature, DisciplineFeature
    dates = {day + timedelta(days=offset) for day in changed_days for offset in range(29)}
    if dates:
        for model in (DailyFeature, DisciplineFeature):
            await session.execute(delete(model).where(model.user_id == user_id, model.date.in_(dates)))


async def clear_derived_health_data(session, user_id):
    """Caller owns the account changes lock and transaction.

    Lineage does not identify every cached explanation's individual inputs,
    so deletion purges owned derivatives conservatively. Original independent
    provider records remain available for recomputation.
    """
    params = {"owner": user_id}
    await session.execute(text("DELETE FROM embeddings WHERE source_table='ai_reports' AND source_id IN (SELECT id FROM ai_reports WHERE user_id=:owner)"), params)
    for table in ("analysis_results", "ai_reports", "daily_features", "discipline_features", "weekly_rollups", "monthly_rollups", "decision_records", "lab_notifications"):
        await session.execute(text(f"DELETE FROM {table} WHERE user_id=:owner"), params)
    await session.execute(text("DELETE FROM agent_tool_calls WHERE user_id=:owner OR session_id IN (SELECT id FROM ai_chat_sessions WHERE user_id=:owner)"), params)
    await session.execute(text("DELETE FROM ai_chat_messages WHERE session_id IN (SELECT id FROM ai_chat_sessions WHERE user_id=:owner)"), params)
    await session.execute(text("DELETE FROM ai_chat_sessions WHERE user_id=:owner"), params)
