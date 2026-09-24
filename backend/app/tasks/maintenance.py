"""Nightly maintenance tasks (D-01, D-03, D-10, F-08 audit fixes).

- ``purge_sessions``: deletes expired session rows (F-08). Bounded by the
  ``idx_sessions_expires_at`` index added in migration 0008.
- ``prune_streams``: retention policy for ``activity_streams`` and
  ``raw_ingest`` (D-01). Streams older than 400 days whose activity already
  has summary metrics are deleted; raw_ingest older than 180 days is deleted
  oldest-first in batches.
- ``vacuum_analyze``: weekly VACUUM ANALYZE on bulk-insert tables (D-10).

All tasks are memory-bounded: stream pruning uses ``DELETE ... USING`` (no
Python-side materialization); raw_ingest pruning uses keyset pagination.
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.db import sessionmaker
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.maintenance")

# D-01 retention windows.
STREAM_RETENTION_DAYS = 400
RAW_INGEST_RETENTION_DAYS = 180
AI_LOG_RETENTION_DAYS = 400
RAW_INGEST_PRUNE_BATCH = 500


@celery_app.task(name="maintenance.purge_sessions")
def purge_sessions() -> dict:
    """F-08: delete sessions whose sliding OR absolute expiry has passed.

    Bounded by ``idx_sessions_expires_at`` (migration 0008). Runs nightly.
    """
    return asyncio.run(_purge_sessions())


async def _purge_sessions() -> dict:
    async with sessionmaker() as session:
        result = await session.execute(
            text(
                "DELETE FROM sessions "
                "WHERE expires_at < now() "
                "   OR (absolute_expires_at IS NOT NULL AND absolute_expires_at < now())"
            )
        )
        await session.commit()
        deleted = result.rowcount or 0
        logger.info("session purge: deleted %s expired sessions", deleted)
        return {"deleted": deleted}


@celery_app.task(name="maintenance.prune_streams")
def prune_streams() -> dict:
    """D-01: retention policy for activity_streams and raw_ingest.

    Streams: kept raw for STREAM_RETENTION_DAYS (400d). After that, the
    activity's summary metrics are already computed and the 1Hz stream is
    no longer needed — deleted in one ``DELETE ... USING`` statement.

    raw_ingest: kept for RAW_INGEST_RETENTION_DAYS (180d) as the replay
    window. Older rows are deleted oldest-first in batches of
    RAW_INGEST_PRUNE_BATCH to keep WAL churn bounded.
    """
    return asyncio.run(_prune_streams())


async def _prune_streams() -> dict:
    streams_deleted = 0
    raw_deleted = 0
    async with sessionmaker() as session:
        # Streams: drop rows whose activity is older than the retention
        # window AND already has summary metrics (so the feature engine
        # never needs the raw stream again).
        streams_result = await session.execute(
            text(
                "DELETE FROM activity_streams st "
                "USING activities a "
                "WHERE a.id = st.activity_id "
                "  AND a.start_time < now() - (:days || ' days')::interval "
                "  AND a.metrics IS NOT NULL"
            ),
            {"days": STREAM_RETENTION_DAYS},
        )
        streams_deleted = streams_result.rowcount or 0

        # raw_ingest: oldest-first batched delete (D-03 chunked pattern).
        # The partial index idx_raw_unproc (migration 0008) keeps unprocessed
        # rows safe — only PROCESSED rows older than the window are pruned.
        while True:
            result = await session.execute(
                text(
                    "DELETE FROM raw_ingest "
                    "WHERE id IN ("
                    "  SELECT id FROM raw_ingest "
                    "  WHERE processed = true "
                    "    AND fetched_at < now() - (:days || ' days')::interval "
                    "  ORDER BY id LIMIT :batch"
                    ")"
                ),
                {"days": RAW_INGEST_RETENTION_DAYS, "batch": RAW_INGEST_PRUNE_BATCH},
            )
            batch_deleted = result.rowcount or 0
            raw_deleted += batch_deleted
            await session.commit()
            if batch_deleted < RAW_INGEST_PRUNE_BATCH:
                break

        # ai_llm_calls / agent_tool_calls / sync_log: rolling 400-day delete.
        # budget math needs ≥90d; 400d matches the stream window.
        for table in ("token_usage", "agent_tool_calls", "sync_log"):
            await session.execute(
                text(
                    f"DELETE FROM {table} "
                    f"WHERE created_at < now() - (:days || ' days')::interval"
                ),
                {"days": AI_LOG_RETENTION_DAYS},
            )

        # Bounded WAL after bulk delete (D-10).
        await session.execute(text("CHECKPOINT"))
        await session.commit()

    logger.info(
        "retention prune: streams_deleted=%s raw_ingest_deleted=%s",
        streams_deleted, raw_deleted,
    )
    return {
        "streams_deleted": streams_deleted,
        "raw_ingest_deleted": raw_deleted,
        "retention_days_streams": STREAM_RETENTION_DAYS,
        "retention_days_raw": RAW_INGEST_RETENTION_DAYS,
    }


@celery_app.task(name="maintenance.vacuum_analyze")
def vacuum_analyze() -> dict:
    """D-10: weekly VACUUM ANALYZE on bulk-insert tables.

    VACUUM reclaims dead tuples left by deletes/updates (raw_ingest churn,
    stream pruning); ANALYZE refreshes planner statistics so the indexes
    added in migration 0008 are actually used.
    """
    return asyncio.run(_vacuum_analyze())


async def _vacuum_analyze() -> dict:
    tables = (
        "raw_ingest",
        "activity_streams",
        "activities",
        "daily_biometrics",
        "hrv_readings",
        "sleep_sessions",
        "stress_readings",
        "sessions",
        "token_usage",
        "agent_tool_calls",
    )
    async with sessionmaker() as session:
        for table in tables:
            # VACUUM cannot run inside a transaction; use a raw connection.
            async with session.connection() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(text(f"VACUUM ANALYZE {table}"))
        logger.info("vacuum_analyze: %s tables maintained", len(tables))
    return {"tables": list(tables)}
