"""Nightly feature-engine task acceptance (§23 Phase 2: "nightly task
populates daily_features/discipline_features respecting the day-boundary
rule") and the §6.4 manual correction path."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.engine import compute_user_range
from app.models.features import DailyFeature
from app.models.user import User
from app.tasks.feature_engine import (
    NIGHTLY_LOCAL_HOUR,
    _nightly,
    _recompute,
    is_nightly_local_time,
)
from tests.helpers.golden import seed_golden_world

# 2025-04-12T01:00Z == 03:00 CEST in Rome (DST active) == previous local day 04-11
ROME_NIGHTLY_NOW = datetime(2025, 4, 12, 1, 0, tzinfo=UTC)


def test_dispatch_guard_windows():
    """Only local hour 3 dispatches; half-hour timezones hit the window at
    their own 03:xx; other hours never do."""
    rome = ZoneInfo("Europe/Rome")
    # 03:30 Rome = 01:30Z (CEST)
    assert is_nightly_local_time(datetime(2025, 4, 12, 1, 30, tzinfo=UTC), rome)
    assert not is_nightly_local_time(datetime(2025, 4, 12, 0, 59, tzinfo=UTC), rome)
    assert not is_nightly_local_time(datetime(2025, 4, 12, 2, 1, tzinfo=UTC), rome)
    # Kolkata (+05:30): 03:30 IST == 22:00Z the previous day
    kolkata = ZoneInfo("Asia/Kolkata")
    assert is_nightly_local_time(datetime(2025, 4, 11, 22, 0, tzinfo=UTC), kolkata)
    assert not is_nightly_local_time(datetime(2025, 4, 11, 21, 0, tzinfo=UTC), kolkata)
    assert NIGHTLY_LOCAL_HOUR == 3  # §19


async def fetch_daily(session: AsyncSession, user_id: int, day: date) -> DailyFeature | None:
    """Read a daily_features row fresh from the DB.

    populate_existing matters: the sessions use expire_on_commit=False, so a
    plain get()/select would hand back identity-mapped instances without
    refreshing them (stale reads after the task's own session wrote, or a
    greenlet error after expire_all)."""
    return (
        await session.scalars(
            select(DailyFeature)
            .where(DailyFeature.user_id == user_id, DailyFeature.date == day)
            .execution_options(populate_existing=True)
        )
    ).first()


async def test_nightly_computes_prior_local_day(db_session: AsyncSession):
    """A dispatch at 03:00 Rome computes YESTERDAY's local date (04-11) with
    the golden values — through the real task path."""
    user, fixture = await seed_golden_world(db_session)
    result = await _nightly(ROME_NIGHTLY_NOW.isoformat())

    # other users (e.g. the bootstrapped owner) legitimately appear when
    # their 03:00 window matches — the golden user must be among them
    assert result[str(user.id)] == "2025-04-11"
    row = await fetch_daily(db_session, user.id, date(2025, 4, 11))
    assert row is not None
    assert float(row.recovery_score) == pytest.approx(
        golden_value(fixture, "2025-04-11", "recovery_score"), abs=1e-3
    )
    assert float(row.acwr) == pytest.approx(
        golden_value(fixture, "2025-04-11", "acwr"), abs=2e-6
    )
    assert row.data_completeness == "full"


def golden_value(fixture, day: str, field: str) -> float:
    return float(fixture["expected"]["daily_rows"][day][field])


async def test_nightly_respects_per_user_local_time(db_session: AsyncSession):
    """Only users whose LOCAL time is 03:00 get computed; a user in a
    timezone where it is not 03:00 is skipped by the same dispatch."""
    user, _ = await seed_golden_world(db_session)
    night_owl = User(
        name="auckland-athlete",
        dob=date(1992, 1, 2),
        timezone="Pacific/Auckland",
    )
    db_session.add(night_owl)
    await db_session.commit()

    # 01:00Z = 03:00 Rome but 13:00 Auckland
    result = await _nightly(ROME_NIGHTLY_NOW.isoformat())
    assert str(user.id) in result
    assert str(night_owl.id) not in result

    auckland_row = await fetch_daily(db_session, night_owl.id, date(2025, 4, 11))
    assert auckland_row is None


async def test_nightly_is_idempotent(db_session: AsyncSession):
    """Running the nightly twice (DST fall-back double tick, manual retry)
    must not duplicate or drift (§17)."""
    user, _ = await seed_golden_world(db_session)
    first = await _nightly(ROME_NIGHTLY_NOW.isoformat())
    row_one = await db_session.get(DailyFeature, {"user_id": user.id, "date": date(2025, 4, 11)})
    # capture primitives: fetch_daily refreshes the SAME identity-mapped
    # instance, so the comparison must be against saved values
    recovery_before, acwr_before = row_one.recovery_score, row_one.acwr
    second = await _nightly(ROME_NIGHTLY_NOW.isoformat())

    assert first[str(user.id)] == second[str(user.id)] == "2025-04-11"
    row_two = await fetch_daily(db_session, user.id, date(2025, 4, 11))
    assert float(row_two.recovery_score) == float(recovery_before)
    assert float(row_two.acwr) == float(acwr_before)

    count = len((await db_session.scalars(select(DailyFeature))).all())
    assert count == 1


async def test_recompute_range_restores_corrected_values(db_session: AsyncSession):
    """§6.4 correction path: corrupt a stored row, run recompute_range, the
    golden values come back (safe idempotent backfill)."""
    user, fixture = await seed_golden_world(db_session)
    await compute_user_range(db_session, user, date(2025, 3, 8), date(2025, 4, 11))

    await db_session.execute(
        text("UPDATE daily_features SET readiness_score = 1, acwr = 99 WHERE user_id = :u"),
        {"u": user.id},
    )
    await db_session.commit()

    report = await _recompute(user.id, "2025-03-08", "2025-04-11")
    assert report["days_computed"] == 35

    row = await fetch_daily(db_session, user.id, date(2025, 4, 11))
    assert float(row.readiness_score) == pytest.approx(
        golden_value(fixture, "2025-04-11", "readiness_score"), abs=1e-3
    )
    assert float(row.acwr) == pytest.approx(
        golden_value(fixture, "2025-04-11", "acwr"), abs=2e-6
    )


async def test_recompute_range_drops_rows_whose_data_vanished(db_session: AsyncSession):
    """If source data disappears for a day, the recompute deletes the stale
    feature row instead of silently keeping a fabricated score."""
    user, _ = await seed_golden_world(db_session)
    await compute_user_range(db_session, user, date(2025, 4, 10), date(2025, 4, 11))
    assert await db_session.get(DailyFeature, {"user_id": user.id, "date": date(2025, 4, 11)})

    # the user's wellness/activity data for 04-11 is removed (correction)
    await db_session.execute(
        text("DELETE FROM sleep_sessions WHERE local_date = '2025-04-11'")
    )
    await db_session.execute(
        text("DELETE FROM hrv_readings WHERE timestamp >= '2025-04-10T22:00:00Z' "
             "AND timestamp < '2025-04-11T22:00:00Z'")
    )
    await db_session.execute(
        text("DELETE FROM daily_biometrics WHERE date = '2025-04-11'")
    )
    await db_session.commit()

    await _recompute(user.id, "2025-04-11", "2025-04-11")
    assert await fetch_daily(db_session, user.id, date(2025, 4, 11)) is None


async def test_beat_schedule_registered():
    """The hourly dispatch must be on the beat (§19: 1x/day 03:00 user-local
    served from a single UTC schedule)."""
    from app.tasks.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["feature-engine-hourly-dispatch"]
    assert entry["task"] == "features.nightly"
    assert "app.tasks.feature_engine" in celery_app.conf.include
