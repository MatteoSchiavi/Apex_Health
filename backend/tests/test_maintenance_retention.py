"""Integration coverage for the scheduled stream-retention task."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks import maintenance
from app.tasks import runtime
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


async def _seed_retention_rows(maker) -> tuple[dict[str, int], dict[str, int]]:
    async with maker() as session:
        user_id = await session.scalar(
            text("SELECT user_id FROM auth_credentials WHERE role = 'owner' LIMIT 1")
        )
        assert user_id is not None

        activity_ids: dict[str, int] = {}
        for name, age_days, completeness, avg_hr in (
            ("eligible_old", 450, "full", 145),
            ("incomplete_old", 450, "partial", None),
            ("recent", 10, "full", 150),
        ):
            activity_id = await session.scalar(
                text(
                    "INSERT INTO activities "
                    "(user_id, start_time, start_tz_offset_minutes, local_date, "
                    " duration_s, avg_hr, data_completeness) "
                    "VALUES (:user_id, now() - make_interval(days => :age_days), "
                    "0, current_date, 3600, :avg_hr, :completeness) "
                    "RETURNING id"
                ),
                {
                    "user_id": user_id,
                    "age_days": age_days,
                    "avg_hr": avg_hr,
                    "completeness": completeness,
                },
            )
            activity_ids[name] = activity_id
            await session.execute(
                text(
                    "INSERT INTO activity_streams (activity_id, t_offset_s, hr) "
                    "VALUES (:activity_id, 0, 140)"
                ),
                {"activity_id": activity_id},
            )

        event_ids: dict[str, int] = {}
        for name, age_days in (("old", 450), ("recent", 10)):
            event_id = await session.scalar(
                text(
                    "INSERT INTO alpha_events "
                    "(user_id, event, created_at, metadata_json) "
                    "VALUES (:user_id, 'overview_viewed', "
                    "now() - make_interval(days => :age_days), '{}'::jsonb) "
                    "RETURNING id"
                ),
                {"user_id": user_id, "age_days": age_days},
            )
            event_ids[name] = event_id

        await session.commit()
        return activity_ids, event_ids


async def _stream_and_activity_counts(
    maker, activity_ids: dict[str, int],
) -> tuple[dict[str, int], int]:
    async with maker() as session:
        streams: dict[str, int] = {}
        for name, activity_id in activity_ids.items():
            streams[name] = await session.scalar(
                text("SELECT count(*) FROM activity_streams WHERE activity_id = :id"),
                {"id": activity_id},
            )
        activities = await session.scalar(
            text("SELECT count(*) FROM activities WHERE id = ANY(:ids)"),
            {"ids": list(activity_ids.values())},
        )
        return streams, activities


async def _alpha_event_count(maker, event_id: int) -> int:
    async with maker() as session:
        return await session.scalar(
            text("SELECT count(*) FROM alpha_events WHERE id = :id"),
            {"id": event_id},
        )


def test_prune_streams_deletes_only_old_summary_complete_streams(monkeypatch) -> None:
    """Run the registered task against the migrated PostgreSQL schema."""
    # The Celery wrapper creates a fresh event loop. A NullPool test engine
    # avoids reusing asyncpg connections created by pytest's fixture loop.
    test_engine = create_async_engine(
        get_settings().database_url, poolclass=NullPool
    )
    test_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(maintenance, "sessionmaker", test_maker)
    monkeypatch.setattr(runtime, "engine", test_engine)
    try:
        activity_ids, event_ids = asyncio.run(_seed_retention_rows(test_maker))

        first_run = maintenance.prune_streams()
        assert first_run["streams_deleted"] == 1
        assert first_run["raw_ingest_deleted"] == 0
        assert first_run["alpha_events_deleted"] == 1

        second_run = maintenance.prune_streams()
        assert second_run["streams_deleted"] == 0
        assert second_run["raw_ingest_deleted"] == 0
        assert second_run["alpha_events_deleted"] == 0

        streams, activities = asyncio.run(
            _stream_and_activity_counts(test_maker, activity_ids)
        )
        assert streams == {"eligible_old": 0, "incomplete_old": 1, "recent": 1}
        assert activities == 3
        assert asyncio.run(_alpha_event_count(test_maker, event_ids["old"])) == 0
        assert asyncio.run(_alpha_event_count(test_maker, event_ids["recent"])) == 1
    finally:
        asyncio.run(test_engine.dispose())


def test_vacuum_analyze_uses_an_autocommit_connection(monkeypatch) -> None:
    """Exercise VACUUM against the migrated tables, outside a transaction."""
    test_engine = create_async_engine(
        get_settings().database_url, poolclass=NullPool
    )
    monkeypatch.setattr(maintenance, "engine", test_engine)
    monkeypatch.setattr(runtime, "engine", test_engine)
    try:
        result = maintenance.vacuum_analyze()
        assert "activity_streams" in result["tables"]
        assert "token_usage" in result["tables"]
    finally:
        asyncio.run(test_engine.dispose())
