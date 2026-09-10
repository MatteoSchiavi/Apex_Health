"""Seed data — feature_weights v1 (MASTER_SPEC §6.4, §23 Phase 2).

v1 blend weights for every weighted composite feature (§7). Blend weights live
here, never hardcoded in the engine (§17); formula-internal constants (e.g.
the ±25% HRV swing that saturates a component) are part of the functional form
and live in code, pinned by the golden-dataset regression tests.

effective_from is the epoch, not now(): the §6.4 selection rule picks the
latest effective_from <= computation date D, so an epoch-stamped v1 makes
historical dates (before the system existed) scoreable and reproducible. A
future tuning pass inserts a new version with a real effective_from — past
dates keep reproducing under the weights that were active then.

Also sets the validated FTP model for road_cycling (§17: FTP estimation uses
a validated protocol only; disciplines.ftp_model_type declares which). Other
disciplines stay NULL — no estimation rather than an ad hoc regression.

Idempotent: ON CONFLICT guards on (feature_name, component_name, version).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EPOCH = "1970-01-01T00:00:00+00:00"

# (feature_name, component_name, weight) — v1, sums to 1.0 per feature.
# illness_risk_score.journal_soreness_fatigue is seeded now (it is part of the
# feature definition, §7) but contributes nothing until the journal module
# lands; the engine renormalizes over available components and the affected
# days carry data_completeness='partial'.
_SEED_WEIGHTS_V1: list[tuple[str, str, str]] = [
    ("recovery_score", "hrv_deviation", "0.35"),
    ("recovery_score", "resting_hr_deviation", "0.25"),
    ("recovery_score", "sleep_quality", "0.25"),
    ("recovery_score", "prior_day_strain", "0.15"),
    ("readiness_score", "recovery", "0.45"),
    ("readiness_score", "sleep_architecture", "0.25"),
    ("readiness_score", "acwr", "0.30"),
    ("sleep_architecture_score", "rem_pct", "0.40"),
    ("sleep_architecture_score", "deep_pct", "0.35"),
    ("sleep_architecture_score", "efficiency", "0.25"),
    ("illness_risk_score", "hrv_drop", "0.40"),
    ("illness_risk_score", "resting_hr_elevation", "0.30"),
    ("illness_risk_score", "respiration_elevation", "0.20"),
    ("illness_risk_score", "journal_soreness_fatigue", "0.10"),
    ("injury_risk_score", "acwr_spike", "0.70"),
    ("injury_risk_score", "load_spike", "0.30"),
]


def upgrade() -> None:
    for feature_name, component_name, weight in _SEED_WEIGHTS_V1:
        op.execute(
            "INSERT INTO feature_weights "
            "(feature_name, component_name, weight, version, effective_from) "
            "SELECT "
            f"'{feature_name}', '{component_name}', {weight}, 1, "
            f"'{_EPOCH}'::timestamptz "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM feature_weights WHERE"
            f"  feature_name = '{feature_name}'"
            f"  AND component_name = '{component_name}'"
            "   AND version = 1"
            ");"
        )
    # §17: FTP from a validated protocol only. The 20-minute protocol
    # (FTP = 0.95 x best 20-min mean power) is the model for road cycling;
    # disciplines without a declared model get no FTP estimate at all.
    op.execute(
        "UPDATE disciplines SET ftp_model_type = 'twenty_min_protocol' "
        "WHERE name = 'road_cycling' AND ftp_model_type IS NULL;"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM feature_weights WHERE version = 1 AND ("
        + " OR ".join(
            f"feature_name = '{feature_name}'"
            for feature_name, _, _ in _SEED_WEIGHTS_V1
        )
        + ");"
    )
    op.execute(
        "UPDATE disciplines SET ftp_model_type = NULL "
        "WHERE name = 'road_cycling' AND ftp_model_type = 'twenty_min_protocol';"
    )
