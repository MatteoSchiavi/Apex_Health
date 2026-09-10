"""Golden-dataset regression tests (MASTER_SPEC §23 Phase 2: "Feature engine
+ golden-dataset regression tests").

The golden world (tests/fixtures/golden/golden_dataset.json, authored by
scripts/make_golden_fixture.py outside the repo) is 35 days of synthetic
history for a Europe/Rome athlete spanning the 2025-03-30 spring-forward,
with EVERY expected value hand-computed from the formulas documented in
app/features — loads and ratios exactly, composites to 1e-3. Any change to
the engine's functional form that moves a number fails here loudly.

The suite also pins the three non-negotiable laws:
- §17 day-boundary: a 00:30 local session (23:30Z) lands on the LOCAL date.
- §17 one load metric for both ACWR windows (the chronic column is the same
  daily TRIMP series summed over 28 days, weekly-averaged).
- §6.4 selection rule: v2 weights effective 2025-04-01 change April's
  recompute but March stays reproducible under v1.
"""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.engine import compute_user_day, compute_user_range
from app.models.features import DailyFeature, DisciplineFeature
from tests.helpers.golden import seed_golden_world

# fields whose expected values are hand-derived rationals (tight tolerance)
COMPOSITE_FIELDS = {
    "recovery_score",
    "readiness_score",
    "illness_risk_score",
    "injury_risk_score",
    "sleep_architecture_score",
    "cross_discipline_fatigue_index",
}
RAT_TOL = 2e-6
COMPOSITE_TOL = 1e-3


@pytest_asyncio.fixture
async def golden_world(db_session: AsyncSession):
    user, fixture = await seed_golden_world(db_session)
    return user, fixture


async def run_range(session, user, start_iso, end_iso):
    return await compute_user_range(
        session, user, date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    )


async def daily_rows(session, user_id) -> dict[date, DailyFeature]:
    # populate_existing: the session uses expire_on_commit=False, so a plain
    # re-select would hand back identity-mapped objects with STALE attributes
    # after the engine's raw upserts — the exact lie a recompute test must
    # never tell.
    rows = await session.scalars(
        select(DailyFeature)
        .where(DailyFeature.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return {row.date: row for row in rows}


def assert_expected_row(row: DailyFeature, expected: dict, label: str) -> None:
    for field, want in expected.items():
        if want == "unasserted":
            continue
        got = getattr(row, field)
        if want is None:
            assert got is None, f"{label}.{field}: expected None, got {got}"
            continue
        if field == "data_completeness":
            assert got == want, f"{label}.{field}: {got} != {want}"
            continue
        got_f = float(got)
        tol = COMPOSITE_TOL if field in COMPOSITE_FIELDS else RAT_TOL
        assert got_f == pytest.approx(want, abs=tol), (
            f"{label}.{field}: {got_f} != {want}"
        )


async def test_golden_daily_rows(db_session, golden_world):
    """Every pinned date matches the hand-computed expectations."""
    user, fixture = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    rows = await daily_rows(db_session, user.id)
    expected = fixture["expected"]["daily_rows"]

    assert len(rows) == fixture["expected"]["daily_row_count"]
    for day_iso, expected_row in expected.items():
        day = date.fromisoformat(day_iso)
        assert day in rows, f"{day_iso}: no daily_features row"
        assert_expected_row(rows[day], expected_row, day_iso)


async def test_golden_discipline_rows(db_session, golden_world):
    """Discipline rows: per-day aggregation with hand-computed decoupling /
    EF / FTP; strength produces no row (no meaningful metric)."""
    user, fixture = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")

    rows = await db_session.scalars(
        select(DisciplineFeature).where(DisciplineFeature.user_id == user.id)
    )
    discipline_names = dict(
        (await db_session.execute(text("SELECT id, name FROM disciplines"))).all()
    )
    actual = {
        (discipline_names[row.discipline_id], row.date): row for row in rows
    }

    for expected_row in fixture["expected"]["discipline_rows"]:
        key = (
            expected_row["discipline"],
            date.fromisoformat(expected_row["date"]),
        )
        assert key in actual, f"{key}: missing discipline_features row"
        row = actual[key]
        for field in ("efficiency_factor", "aerobic_decoupling_pct", "estimated_ftp"):
            want = expected_row[field]
            if want == "unasserted":
                continue
            got = getattr(row, field)
            if want is None:
                assert got is None, f"{key}.{field}: expected None, got {got}"
            else:
                assert float(got) == pytest.approx(want, abs=RAT_TOL), (
                    f"{key}.{field}: {float(got)} != {want}"
                )

    for absent in fixture["expected"]["absent_discipline_rows"]:
        key = (absent["discipline"], date.fromisoformat(absent["date"]))
        assert key not in actual, f"{key}: expected no row (all metrics None)"


async def test_golden_sync_is_idempotent(db_session, golden_world):
    """§17: re-running the engine for the same range must not duplicate or
    drift — upserts by primary key, byte-stable values."""
    user, fixture = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    first = await daily_rows(db_session, user.id)

    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    second = await daily_rows(db_session, user.id)

    assert set(first) == set(second)
    for day, row in first.items():
        again = second[day]
        for field in (
            "recovery_score",
            "readiness_score",
            "acwr",
            "strain_score",
            "cross_discipline_fatigue_index",
            "data_completeness",
        ):
            assert getattr(again, field) == getattr(row, field), (
                f"drift on {day}.{field}"
            )

    disc_count_first = len(
        (await db_session.scalars(select(DisciplineFeature))).all()
    )
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    disc_count_second = len(
        (await db_session.scalars(select(DisciplineFeature))).all()
    )
    assert disc_count_first == disc_count_second


async def test_day_boundary_local_not_utc(db_session, golden_world):
    """§17: the 00:30 Rome session (2025-03-20T23:30Z) must land on local
    date 03-21 — its load contributes to 03-21's acute/chronic windows."""
    user, fixture = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    rows = await daily_rows(db_session, user.id)

    # acute7 at 03-21 includes the boundary session (90 of the 445)
    assert float(rows[date(2025, 3, 21)].training_load_acute) == pytest.approx(
        445.0, abs=RAT_TOL
    )
    # and 03-20's acute7 does NOT include it (95 from the FTP test only)
    assert float(rows[date(2025, 3, 20)].training_load_acute) == pytest.approx(
        355.0, abs=RAT_TOL
    )


async def test_acwr_single_load_metric_for_both_windows(db_session, golden_world):
    """§17: ACWR uses exactly one load metric — the chronic column must be
    the weekly-averaged sum of the same daily TRIMP series the acute column
    sums, for every day of the range."""
    user, _ = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    rows = await daily_rows(db_session, user.id)
    for row in rows.values():
        if row.acwr is None:
            assert float(row.training_load_chronic) == 0.0
            continue
        acute = float(row.training_load_acute)
        chronic_weekly = float(row.training_load_chronic)
        assert chronic_weekly > 0
        # rel 1e-6: the stored acwr is the raw ratio rounded to 6dp
        assert acute / chronic_weekly == pytest.approx(float(row.acwr), rel=1e-6)


async def test_weights_v2_recompute_respects_selection_rule(db_session, golden_world):
    """§6.4: a v2 recovery weight effective Rome-midnight 2025-04-01 changes
    April's values on recompute; March stays reproducible under v1."""
    user, fixture = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    before = await daily_rows(db_session, user.id)

    v2 = fixture["expected"]["v2_weights"]
    await db_session.execute(
        text(
            "INSERT INTO feature_weights "
            "(feature_name, component_name, weight, version, effective_from) "
            "SELECT 'recovery_score', :c, :w, 2, '2025-03-31T22:00:00Z'"
        ),
        [
            {"c": component, "w": Decimal(str(weight))}
            for component, weight in v2["rows"].items()
        ],
    )
    await db_session.commit()

    # recompute April only -> v2 applies
    await run_range(db_session, user, "2025-04-01", "2025-04-11")
    rows = await daily_rows(db_session, user.id)
    for day_iso, expected_fields in v2["recomputed_daily_rows"].items():
        assert_expected_row(
            rows[date.fromisoformat(day_iso)], expected_fields, day_iso
        )

    # March rows were not touched by the April recompute...
    march_day = date.fromisoformat(v2["pre_cutoff_unchanged"]["date"])
    assert float(before[march_day].recovery_score) == pytest.approx(
        v2["pre_cutoff_unchanged"]["recovery_score"], abs=COMPOSITE_TOL
    )
    assert float(rows[march_day].recovery_score) == float(
        before[march_day].recovery_score
    )

    # ...and recomputing March explicitly still reproduces v1 values
    await run_range(db_session, user, "2025-03-08", "2025-03-31")
    rows = await daily_rows(db_session, user.id)
    assert float(rows[march_day].recovery_score) == pytest.approx(
        v2["pre_cutoff_unchanged"]["recovery_score"], abs=COMPOSITE_TOL
    )


async def test_nightly_single_day_matches_range_recompute(db_session, golden_world):
    """The nightly path (compute_user_day for one day) and the range path
    must agree byte-for-byte on the same day."""
    user, _ = golden_world
    await run_range(db_session, user, "2025-03-08", "2025-04-11")
    recomputed = await compute_user_day(db_session, user, date(2025, 4, 4))
    rows = await daily_rows(db_session, user.id)
    stored = rows[date(2025, 4, 4)]
    for field in (
        "recovery_score",
        "readiness_score",
        "illness_risk_score",
        "acwr",
    ):
        assert float(getattr(stored, field)) == pytest.approx(
            recomputed["daily"][field], abs=2e-6
        )
    assert stored.data_completeness == recomputed["daily"]["data_completeness"]
