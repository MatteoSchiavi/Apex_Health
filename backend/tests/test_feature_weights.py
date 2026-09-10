"""feature_weights seed + §6.4 selection-rule acceptance (Phase 2, commit A).

The rule under test: for a computation date D, the active weight row for a
(feature_name, component_name) pair is the one with the latest effective_from
<= the start of local day D. Historical dates must keep reproducing under the
weights that were active then.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.weights import cutoff_for_local_day, load_weights

ROME = ZoneInfo("Europe/Rome")

EXPECTED_V1 = {
    "recovery_score": {
        "hrv_deviation": "0.35",
        "resting_hr_deviation": "0.25",
        "sleep_quality": "0.25",
        "prior_day_strain": "0.15",
    },
    "readiness_score": {
        "recovery": "0.45",
        "sleep_architecture": "0.25",
        "acwr": "0.30",
    },
    "sleep_architecture_score": {
        "rem_pct": "0.40",
        "deep_pct": "0.35",
        "efficiency": "0.25",
    },
    "illness_risk_score": {
        "hrv_drop": "0.40",
        "resting_hr_elevation": "0.30",
        "respiration_elevation": "0.20",
        "journal_soreness_fatigue": "0.10",
    },
    "injury_risk_score": {
        "acwr_spike": "0.70",
        "load_spike": "0.30",
    },
}


async def test_v1_seed_rows(db_session: AsyncSession):
    """Migration 0003 seeds every weighted feature of §7 at version 1,
    effective from the epoch (so historical dates are scoreable)."""
    for feature_name, expected_components in EXPECTED_V1.items():
        got = await load_weights(
            db_session, feature_name, cutoff_for_local_day(date(2025, 3, 16), ROME)
        )
        assert got == {
            c: float(w) for c, w in expected_components.items()
        }, feature_name


async def test_v1_effective_from_is_epoch(db_session: AsyncSession):
    row = await db_session.execute(
        text(
            "SELECT MIN(effective_from), MAX(effective_from) "
            "FROM feature_weights WHERE version = 1"
        )
    )
    lo, hi = row.fetchone()
    assert lo == hi == datetime(1970, 1, 1, tzinfo=UTC)


async def test_selection_rule_latest_effective_from_wins(db_session: AsyncSession):
    """Insert v2 recovery weights effective Rome midnight 2025-04-01:
    March dates must keep reproducing under v1, April dates must use v2."""
    await db_session.execute(
        text(
            "INSERT INTO feature_weights "
            "(feature_name, component_name, weight, version, effective_from) VALUES "
            "('recovery_score', 'hrv_deviation', '0.90', 2, '2025-03-31T22:00:00Z'), "
            "('recovery_score', 'resting_hr_deviation', '0.05', 2, '2025-03-31T22:00:00Z'), "
            "('recovery_score', 'sleep_quality', '0.03', 2, '2025-03-31T22:00:00Z'), "
            "('recovery_score', 'prior_day_strain', '0.02', 2, '2025-03-31T22:00:00Z')"
        )
    )
    await db_session.commit()

    before = await load_weights(
        db_session, "recovery_score", cutoff_for_local_day(date(2025, 3, 31), ROME)
    )
    assert before["hrv_deviation"] == 0.35  # v1 — weights active then
    assert before["sleep_quality"] == 0.25

    after = await load_weights(
        db_session, "recovery_score", cutoff_for_local_day(date(2025, 4, 1), ROME)
    )
    assert after["hrv_deviation"] == 0.90  # v2
    assert after["prior_day_strain"] == 0.02

    untouched = await load_weights(
        db_session, "illness_risk_score", cutoff_for_local_day(date(2025, 4, 5), ROME)
    )
    assert untouched["hrv_drop"] == 0.40  # other features unaffected


async def test_future_only_weights_never_appear(db_session: AsyncSession):
    """A weight effective far in the future must not leak into earlier dates
    (the exact failure the §6.4 rule exists to prevent)."""
    await db_session.execute(
        text(
            "INSERT INTO feature_weights "
            "(feature_name, component_name, weight, version, effective_from) VALUES "
            "('readiness_score', 'recovery', '0.99', 2, '2030-01-01T00:00:00Z')"
        )
    )
    await db_session.commit()
    got = await load_weights(
        db_session, "readiness_score", cutoff_for_local_day(date(2025, 4, 11), ROME)
    )
    assert got["recovery"] == 0.45


async def test_road_cycling_ftp_model_declared(db_session: AsyncSession):
    """§17: FTP estimation only via a validated protocol. road_cycling declares
    the 20-minute protocol; every other discipline stays NULL (no estimate
    rather than an ad hoc regression)."""
    rows = await db_session.execute(
        text("SELECT name, ftp_model_type FROM disciplines")
    )
    models = dict(rows.fetchall())
    assert models["road_cycling"] == "twenty_min_protocol"
    assert all(v is None for k, v in models.items() if k != "road_cycling")


def test_cutoff_is_local_midnight_not_utc():
    """The cutoff must be derived in the user's timezone (§17), never naive
    UTC midnight — and it must track DST: Rome 2025-03-29 is still CET (+1),
    2025-03-31 is already CEST (+2, spring-forward was 2025-03-30)."""
    cet = cutoff_for_local_day(date(2025, 3, 29), ROME)
    assert cet.utcoffset().total_seconds() == 3600.0
    assert cet.astimezone(UTC) == datetime(2025, 3, 28, 23, 0, tzinfo=UTC)
    cest = cutoff_for_local_day(date(2025, 3, 31), ROME)
    assert cest.utcoffset().total_seconds() == 7200.0
    assert cest.astimezone(UTC) == datetime(2025, 3, 30, 22, 0, tzinfo=UTC)
