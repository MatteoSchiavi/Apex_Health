"""§12 Multi-source activity reconciliation tests (Phase 6 AC2).

THE acceptance criterion: reconciliation prevents a duplicate when a
Technogym session lands inside the same ±10-minute window as an existing
Garmin entry — one activities row, two source links, fields merged per the
richer-source-per-field rule, populated fields never overwritten with NULL.

Symmetric direction (Garmin arrives over Technogym), window edges,
discipline compatibility, same-source near-duplicates, and the §12 merge
floor rules are all pinned here. Every client is fixture-backed or a plain
in-test stub — no live API (§0/§16.7/§20).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.connectors.garmin.sync import run_user_sync_with_escalation as run_garmin_sync
from app.connectors.technogym.sync import (
    run_user_sync_with_escalation as run_technogym_sync,
)
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.integration import Integration, RawIngest
from app.models.user import User
from tests.helpers.fixture_client import FixtureGarminClient, FixtureTechnogymClient

SYNC_NOW = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
ROME = ZoneInfo("Europe/Rome")


@pytest_asyncio.fixture(autouse=True)
async def clean_sync_tables(db_session):
    await db_session.execute(
        text(
            "TRUNCATE raw_ingest, activities, activity_source_links, "
            "activity_streams, gear, gear_service_logs, activity_gear_links, "
            "integrations, alerts RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    yield


async def make_user(session, tz: str = "Europe/Rome") -> User:
    user = User(name="dual-source-athlete", timezone=tz)
    session.add(user)
    await session.commit()
    return user


async def seed_source_activity(
    session,
    user_id: int,
    *,
    source: str,
    external_id: str,
    discipline_name: str,
    start_time: datetime,
    **fields,
) -> Activity:
    """A normalized activity row owned by one source (the 'already there'
    side of a reconciliation scenario)."""
    discipline_id = (
        await session.scalars(
            select(Discipline.id).where(Discipline.name == discipline_name)
        )
    ).one()
    activity = Activity(
        user_id=user_id,
        discipline_id=discipline_id,
        start_time=start_time,
        start_tz_offset_minutes=60,
        local_date=start_time.astimezone(ROME).date(),
        duration_s=fields.pop("duration_s", 3600),
        **fields,
    )
    session.add(activity)
    await session.flush()
    session.add(
        ActivitySourceLink(
            activity_id=activity.id, source=source, external_id=external_id
        )
    )
    await session.commit()
    return activity


def technogym_client_with(workouts: list[dict]) -> FixtureTechnogymClient:
    client = FixtureTechnogymClient()
    client._workouts = workouts
    return client


def treadmill_workout(
    external_id: str, start_iso: str, **overrides
) -> dict:
    payload = {
        "id": external_id,
        "startDate": start_iso,
        "durationSeconds": 3900,
        "equipment": "treadmill",
        "totalDistanceMeters": 10250.0,
        "avgHeartRate": 152,
        "maxHeartRate": 171,
        "avgPowerWatts": 210.0,
        "calories": 640,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------- THE Phase 6 acceptance test


async def test_technogym_session_reconciles_into_same_window_garmin_entry(db_session):
    """AC2: reconciliation prevents a duplicate against a same-window Garmin
    entry — no second activities row; a technogym source link is attached;
    fields merge per §12's richer-source-per-field rule."""
    user = await make_user(db_session)

    garmin_row = await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9001",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),  # 10:00 local
        duration_s=3600,
        distance_m=9800.0,  # GPS/footpod-derived distance
        avg_hr=150,
        max_hr=168,
        avg_power=None,  # wrist-only recording, no power
        calories=610,
    )

    # Technogym treadmill session starting 10:04 local — inside the window.
    client = technogym_client_with(
        [treadmill_workout("tg-ac2", "2025-03-09T10:04:00+01:00")]
    )
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    report = await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    assert report is not None

    # --- THE core assertion: no duplicate row was created
    activities = (await db_session.scalars(select(Activity))).all()
    assert len(activities) == 1
    merged = activities[0]
    assert merged.id == garmin_row.id

    # --- two source links now point at the SAME row
    links = (
        (
            await db_session.scalars(
                select(ActivitySourceLink).where(
                    ActivitySourceLink.activity_id == merged.id
                )
            )
        )
        .all()
    )
    assert {(l.source, l.external_id) for l in links} == {
        ("garmin", "g-9001"),
        ("technogym", "tg-ac2"),
    }
    tg_link = next(l for l in links if l.source == "technogym")
    assert tg_link.raw_ingest_id is not None  # raw-first trail intact

    # --- merged fields per §12
    assert merged.avg_hr == 150  # Garmin for HR — machine grips lose
    assert merged.max_hr == 168
    assert merged.avg_power is not None and float(merged.avg_power) == 210.0  # machine power merged
    assert float(merged.distance_m) == 9800.0  # GPS-derived: Garmin preferred, TG value in raw trail
    assert merged.calories == 610  # first-come wins, TG's 640 does not stomp it
    assert merged.duration_s == 3600  # existing wins
    # identity fields stay the garmin row's own
    assert merged.start_time == datetime(2025, 3, 9, 9, 0, tzinfo=UTC)
    assert merged.discipline_id == garmin_row.discipline_id


# --------------------------------------------------------------- window edges


async def test_outside_window_creates_a_new_row(db_session):
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9002",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        avg_hr=150,
    )
    # 11 minutes later — outside the ±10 min window
    client = technogym_client_with(
        [treadmill_workout("tg-late", "2025-03-09T10:11:00+01:00")]
    )
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 2


async def test_incompatible_discipline_creates_a_new_row(db_session):
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9003",
        discipline_name="road_cycling",  # ride, not run — different session
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        avg_hr=140,
    )
    client = technogym_client_with(
        [treadmill_workout("tg-run", "2025-03-09T10:04:00+01:00")]  # running
    )
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    # not merged: different seeded disciplines are different sessions
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 2


async def test_same_source_near_duplicate_stays_separate(db_session):
    """Two Technogym machine sessions five minutes apart (superset circuit)
    are two workouts — candidates already linked to the incoming source are
    excluded from reconciliation."""
    user = await make_user(db_session)
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    client = technogym_client_with(
        [
            treadmill_workout("tg-circuit-a", "2025-03-09T10:00:00+01:00"),
            treadmill_workout("tg-circuit-b", "2025-03-09T10:05:00+01:00"),
        ]
    )
    await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 2
    links = (await db_session.scalars(select(ActivitySourceLink))).all()
    assert {l.external_id for l in links} == {"tg-circuit-a", "tg-circuit-b"}


# --------------------------------------------------------------- merge rules


async def test_populated_field_never_overwritten_with_null(db_session):
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9004",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        avg_hr=150,
        max_hr=168,
        calories=610,
        avg_power=None,
    )
    # Technogym payload WITHOUT calories/max_hr — must not NULL them out.
    client = technogym_client_with(
        [
            treadmill_workout(
                "tg-sparse",
                "2025-03-09T10:04:00+01:00",
                calories=None,
                maxHeartRate=None,
                avgPowerWatts=None,
            )
        ]
    )
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    activities = (await db_session.scalars(select(Activity))).all()
    assert len(activities) == 1  # still merged, no duplicate
    merged = activities[0]
    assert merged.calories == 610
    assert merged.max_hr == 168
    assert merged.avg_hr == 150
    assert merged.avg_power is None  # neither source had one


async def test_preferred_source_wins_field_conflict(db_session):
    """Conflict on a §12-preferred field: the preferred source's value wins
    even when the existing row is populated."""
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9005",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        avg_power=180.0,  # Garmin wrist estimate
    )
    client = technogym_client_with(
        [treadmill_workout("tg-power", "2025-03-09T10:04:00+01:00", avgPowerWatts=210.0)]
    )
    integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(integration)
    await db_session.commit()

    await run_technogym_sync(
        db_session, user, integration, client, now=SYNC_NOW, page_size=5, page_delay_s=0.0
    )
    merged = (await db_session.scalars(select(Activity))).one()
    assert float(merged.avg_power) == 210.0  # machine power beats the estimate


# ------------------------------------------------- symmetric direction (§12)


async def test_garmin_arrival_reconciles_into_same_window_technogym_entry(db_session):
    """§12 reads 'on ingesting an activity' — the same law runs when Garmin
    arrives over an existing Technogym row."""
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="technogym",
        external_id="tg-first",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        duration_s=3900,
        avg_power=210.0,
        distance_m=10250.0,
        avg_hr=None,  # machine grips failed
    )

    class GarminOverTg(FixtureGarminClient):
        def __init__(self) -> None:
            super().__init__()
            self._activities = [
                {
                    "activityId": 9006,
                    "startTimeGMT": "2025-03-09 09:05:00",
                    "duration": 3660.0,
                    "distance": 9900.0,
                    "activityType": {"typeKey": "treadmill_running"},
                    "averageHR": 151,
                    "maxHR": 169,
                    "calories": 615,
                    "manual": False,
                }
            ]

    integration = Integration(user_id=user.id, provider="garmin", status="active")
    db_session.add(integration)
    await db_session.commit()

    report = await run_garmin_sync(
        db_session,
        user,
        integration,
        GarminOverTg(),
        now=SYNC_NOW,
        page_size=5,
        page_delay_s=0.0,
        empty_gap_days=10,
    )
    assert report is not None

    activities = (await db_session.scalars(select(Activity))).all()
    assert len(activities) == 1  # reconciled, not duplicated
    merged = activities[0]
    links = (
        (
            await db_session.scalars(
                select(ActivitySourceLink).where(
                    ActivitySourceLink.activity_id == merged.id
                )
            )
        )
        .all()
    )
    assert {(l.source, l.external_id) for l in links} == {
        ("technogym", "tg-first"),
        ("garmin", "9006"),
    }
    assert merged.avg_hr == 151  # Garmin for HR — filled the gap
    assert float(merged.avg_power) == 210.0  # machine power survives the merge

    # distance: Garmin's GPS-derived 9900 does NOT stomp the existing
    # populated 10250 (first-come wins; TG's machine value already there).
    assert float(merged.distance_m) == 10250.0
    assert merged.calories == 615  # gap filled from Garmin


async def test_multi_source_activity_survives_resync_without_duplication(db_session):
    """After a reconcile-merge, re-running BOTH syncs must not split the row
    apart again — each source's upsert stays on its own link (§17)."""
    user = await make_user(db_session)
    await seed_source_activity(
        db_session,
        user.id,
        source="garmin",
        external_id="g-9007",
        discipline_name="running",
        start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
        avg_hr=150,
    )

    tg_integration = Integration(user_id=user.id, provider="technogym", status="active")
    db_session.add(tg_integration)
    await db_session.commit()
    await run_technogym_sync(
        db_session,
        user,
        tg_integration,
        technogym_client_with([treadmill_workout("tg-merge", "2025-03-09T10:04:00+01:00")]),
        now=SYNC_NOW,
        page_size=5,
        page_delay_s=0.0,
    )
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 1

    # Technogym re-sync: its own link routes the update in place.
    await run_technogym_sync(
        db_session,
        user,
        tg_integration,
        technogym_client_with([treadmill_workout("tg-merge", "2025-03-09T10:04:00+01:00")]),
        now=SYNC_NOW,
        page_size=5,
        page_delay_s=0.0,
    )
    assert await db_session.scalar(select(func.count()).select_from(Activity)) == 1
    links = (await db_session.scalars(select(ActivitySourceLink))).all()
    assert len(links) == 2  # garmin + technogym, never a third row
    # raw trail: one workout payload per TG pass (detail fetch returns empty
    # for this id — no fixture detail), growing by design (§17).
    assert await db_session.scalar(select(func.count()).select_from(RawIngest)) == 2
