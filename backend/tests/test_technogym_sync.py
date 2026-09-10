"""Phase 6 tests — Technogym connector (§23 Phase 6, §11a, §17, §19, §21).

Backfill populates normalized tables from recorded fixtures; re-running does
not duplicate normalized rows (§17 idempotent upserts); incremental passes
stop at the last_synced_at boundary; malformed payloads stay unprocessed and
replayable (§3); three consecutive failures fire sync_failure (§21); beat
carries the 6-hourly schedule (§19).

No test touches the live Technogym API — every client here is fixture-backed
or failing-on-purpose (§0, §16.7, §20).
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.connectors.technogym.sync import run_user_sync_with_escalation
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.alert import Alert
from app.models.integration import Integration, RawIngest
from app.models.user import User
from tests.helpers.fixture_client import (
    FailingTechnogymClient,
    FixtureTechnogymClient,
)

# The fixture world's "now" (consistent with the Garmin fixture world).
SYNC_NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
PAGE_SIZE = 2  # forces the 3-workout corpus onto two pages


@pytest_asyncio.fixture(autouse=True)
async def clean_sync_tables(db_session):
    """Sync-domain tables are shared across tests in one schema build —
    truncate between tests."""
    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "activity_streams, gear, gear_service_logs, activity_gear_links, "
            "integrations, alerts RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def make_technogym_user(session, tz: str = "Europe/Rome") -> tuple[User, Integration]:
    user = User(name="gym-athlete", timezone=tz)
    session.add(user)
    await session.flush()
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    session.add(integration)
    await session.commit()
    return user, integration


def sync_kwargs() -> dict:
    return dict(page_size=PAGE_SIZE, page_delay_s=0.0)


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


# ------------------------------------------------------------- backfill (AC-like)


async def test_backfill_populates_normalized_tables(db_session):
    user, integration = await make_technogym_user(db_session)

    report = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureTechnogymClient(), now=SYNC_NOW, **sync_kwargs()
    )

    assert report is not None and report.mode == "backfill"
    assert report.workout_pages == 2  # corpus of 3 on a page size of 2

    # --- raw-first law (§17): 3 workouts + 1 machine detail
    assert report.raw_rows_stored == 4
    assert await count(db_session, RawIngest) == 4
    unprocessed = (
        (await db_session.scalars(select(RawIngest).where(RawIngest.processed.is_(False))))
        .all()
    )
    assert unprocessed == []

    # --- activities + idempotency keys (source, external_id)
    assert await count(db_session, Activity) == 3
    links = (await db_session.scalars(select(ActivitySourceLink))).all()
    assert len(links) == 3
    assert all(l.source == "technogym" and l.raw_ingest_id is not None for l in links)

    by_external = {
        l.external_id: await db_session.get(Activity, l.activity_id) for l in links
    }
    assert set(by_external) == {"tg-wkt-001", "tg-wkt-002", "tg-wkt-003"}

    # discipline mapping over the 14-discipline seed
    names = dict(
        (await db_session.execute(select(Discipline.id, Discipline.name))).all()
    )
    assert names[by_external["tg-wkt-003"].discipline_id] == "running"      # treadmill
    assert names[by_external["tg-wkt-002"].discipline_id] == "strength"     # kinesis
    assert names[by_external["tg-wkt-001"].discipline_id] == "road_cycling"  # indoor_cycle

    # §17 day-boundary rule: local start date in the USER's timezone
    w3 = by_external["tg-wkt-003"]
    assert w3.start_time == datetime(2025, 3, 9, 9, 4, tzinfo=UTC)  # 10:04+01:00
    assert w3.local_date == datetime(2025, 3, 9).date()
    assert w3.start_tz_offset_minutes == 60  # Europe/Rome, pre-DST-switch March

    # machine fields normalized from the workout row
    assert w3.duration_s == 3720
    assert float(w3.distance_m) == 10250.0
    assert w3.avg_hr == 152 and w3.max_hr == 171
    assert float(w3.avg_power) == 210.0
    assert w3.np_power is None  # Technogym reports no NP equivalent
    assert w3.calories == 640
    assert w3.data_completeness == "full"

    # machine detail fetched per newly seen workout and stored raw
    assert report.details_fetched == 1  # fixture detail exists only for tg-wkt-003
    detail_rows = (
        (
            await db_session.scalars(
                select(RawIngest).where(
                    RawIngest.payload_type == "workout_detail:tg-wkt-003"
                )
            )
        )
        .all()
    )
    assert len(detail_rows) == 1

    # §6.3/§19: the integration's watermark advanced
    assert integration.last_synced_at == SYNC_NOW
    assert integration.consecutive_failures == 0


# ------------------------------------------------------------- AC2: idempotent


async def test_second_sync_does_not_duplicate_rows(db_session):
    user, integration = await make_technogym_user(db_session)
    first = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureTechnogymClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert first is not None and first.mode == "backfill"
    activity_ids_before = sorted((await db_session.scalars(select(Activity.id))).all())
    link_ids_before = sorted((await db_session.scalars(select(ActivitySourceLink.id))).all())

    # Second run: last_synced_at is set -> incremental; its window re-covers
    # the tail by design — overlap must be absorbed by upserts.
    second = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureTechnogymClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert second is not None and second.mode == "incremental"

    assert await count(db_session, Activity) == 3
    assert sorted((await db_session.scalars(select(Activity.id))).all()) == activity_ids_before
    assert await count(db_session, ActivitySourceLink) == 3
    assert (
        sorted((await db_session.scalars(select(ActivitySourceLink.id))).all())
        == link_ids_before
    )

    # raw trail grows by design: the incremental window stops after page 1
    # (oldest item on that page is already at/below the watermark), so only
    # the 2 page-1 workouts re-fetched. Normalized rows never duplicate.
    assert await count(db_session, RawIngest) == 4 + 2


# ---------------------------------------------------------- incremental window


async def test_incremental_stops_at_boundary_and_pulls_new_workouts(db_session):
    user, integration = await make_technogym_user(db_session)
    await run_user_sync_with_escalation(
        db_session, user, integration, FixtureTechnogymClient(), now=SYNC_NOW, **sync_kwargs()
    )

    class GrowingClient(FixtureTechnogymClient):
        """The corpus as it looks a day later: one genuinely new session on top."""

        def __init__(self) -> None:
            super().__init__()
            self._workouts.insert(
                0,
                {
                    "id": "tg-wkt-004",
                    "startDate": "2025-03-10T07:30:00+01:00",
                    "durationSeconds": 1800,
                    "equipment": "treadmill",
                    "avgHeartRate": 149,
                    "calories": 320,
                },
            )

    later = SYNC_NOW + timedelta(hours=6)
    client = GrowingClient()
    report = await run_user_sync_with_escalation(
        db_session, user, integration, client, now=later, **sync_kwargs()
    )

    assert report is not None and report.mode == "incremental"
    # boundary: first page already reaches back to tg-wkt-003 (09:04Z on
    # 03-09 <= watermark) -> exactly one page fetched
    assert client.workout_calls == [(0, PAGE_SIZE)]
    assert report.new_workouts == 1
    assert await count(db_session, Activity) == 4
    link = (
        await db_session.scalars(
            select(ActivitySourceLink).where(
                ActivitySourceLink.source == "technogym",
                ActivitySourceLink.external_id == "tg-wkt-004",
            )
        )
    ).one()
    activity = await db_session.get(Activity, link.activity_id)
    assert activity.local_date == datetime(2025, 3, 10).date()
    assert integration.last_synced_at == later


# --------------------------------------------------------- parser isolation (§3)


async def test_malformed_workout_stays_unprocessed_and_replayable(db_session):
    user, integration = await make_technogym_user(db_session)

    class BrokenClient(FixtureTechnogymClient):
        def __init__(self) -> None:
            super().__init__()
            # missing durationSeconds -> NormalizationError at parse time
            self._workouts.append(
                {
                    "id": "tg-wkt-bad",
                    "startDate": "2025-03-07T19:00:00+01:00",
                    "equipment": "treadmill",
                }
            )

    report = await run_user_sync_with_escalation(
        db_session, user, integration, BrokenClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert report is not None
    assert report.raw_rows_unprocessed == 1

    bad = (
        (
            await db_session.scalars(
                select(RawIngest).where(
                    RawIngest.payload_type == "workout",
                    RawIngest.processed.is_(False),
                )
            )
        )
        .all()
    )
    assert len(bad) == 1
    assert bad[0].raw_json["id"] == "tg-wkt-bad"  # raw intact -> replayable

    # the healthy rows still normalized
    assert await count(db_session, Activity) == 3


async def test_unknown_equipment_falls_back_to_gym_general_and_is_flagged(db_session):
    user, integration = await make_technogym_user(db_session)

    class ExoticClient(FixtureTechnogymClient):
        def __init__(self) -> None:
            super().__init__()
            self._workouts.insert(
                0,
                {
                    "id": "tg-wkt-005",
                    "startDate": "2025-03-09T15:00:00+01:00",
                    "durationSeconds": 900,
                    "equipment": "holodeck",
                    "avgHeartRate": 100,
                },
            )

    report = await run_user_sync_with_escalation(
        db_session, user, integration, ExoticClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert report is not None
    assert any("holodeck" in note for note in report.notes)  # flagged, not silent

    link = (
        await db_session.scalars(
            select(ActivitySourceLink).where(
                ActivitySourceLink.external_id == "tg-wkt-005"
            )
        )
    ).one()
    activity = await db_session.get(Activity, link.activity_id)
    names = dict(
        (await db_session.execute(select(Discipline.id, Discipline.name))).all()
    )
    assert names[activity.discipline_id] == "gym_general"
    assert activity.data_completeness == "full"


# --------------------------------------------------------- §21 escalation


async def test_three_consecutive_failures_fire_sync_failure_alert_then_reset(db_session):
    user, integration = await make_technogym_user(db_session)

    for _ in range(3):
        report = await run_user_sync_with_escalation(
            db_session, user, integration, FailingTechnogymClient(), **sync_kwargs()
        )
        assert report is None
    assert integration.consecutive_failures == 3
    alerts = (
        await db_session.scalars(select(Alert).where(Alert.type == "sync_failure"))
    ).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert "3 consecutive" in alerts[0].message

    # non-multiples of three do not re-fire
    await run_user_sync_with_escalation(
        db_session, user, integration, FailingTechnogymClient(), **sync_kwargs()
    )
    assert integration.consecutive_failures == 4
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Alert).where(Alert.type == "sync_failure")
        )
        == 1
    )

    # a successful sync resets the counter
    ok = await run_user_sync_with_escalation(
        db_session, user, integration, FixtureTechnogymClient(), now=SYNC_NOW, **sync_kwargs()
    )
    assert ok is not None
    assert integration.consecutive_failures == 0


# --------------------------------------------------------- §19 beat schedule


def test_beat_carries_technogym_every_6h():
    from app.tasks.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["technogym-sync-every-6h"]
    assert entry["task"] == "technogym.sync_all"
    assert entry["schedule"].hour == {0, 6, 12, 18}  # "*/6"
    assert entry["schedule"].minute == {10}  # staggered off the Garmin :00 tick
    assert "app.tasks.technogym_sync" in celery_app.conf.include
