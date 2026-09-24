"""Physiological CHECK constraints (P-02) + missing hot-path indexes (F-08/D-05)
+ session absolute lifetime (F-21) + device-token absolute expiry (F-19)
+ activity_streams composite index (D-05) + raw_ingest unprocessed partial
index (D-05) + daily_biometrics user/date index (D-05) + workout_sessions
user/scheduled_date index (D-06) + sessions token_hash/expires_at indexes
(F-08/D-05).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# P-02: physiological plausibility CHECK constraints. Each is NULL-tolerant
# (NULL stays valid — only non-NULL implausible values are rejected). The
# ranges mirror app/connectors/validation.py exactly.
_CHECKS: list[tuple[str, str, str]] = [
    # (table, constraint_name, condition)
    ("hrv_readings", "ck_hrv_readings_hrv_ms_plausible",
     "hrv_ms BETWEEN 2 AND 400"),
    ("daily_biometrics", "ck_daily_biometrics_resting_hr_plausible",
     "resting_hr IS NULL OR resting_hr BETWEEN 25 AND 120"),
    ("daily_biometrics", "ck_daily_biometrics_spo2_avg_plausible",
     "spo2_avg IS NULL OR spo2_avg BETWEEN 70 AND 100"),
    ("daily_biometrics", "ck_daily_biometrics_weight_kg_plausible",
     "weight_kg IS NULL OR weight_kg BETWEEN 25 AND 400"),
    ("daily_biometrics", "ck_daily_biometrics_body_fat_pct_plausible",
     "body_fat_pct IS NULL OR body_fat_pct BETWEEN 3 AND 65"),
    ("sleep_sessions", "ck_sleep_sessions_spo2_avg_plausible",
     "spo2_avg IS NULL OR spo2_avg BETWEEN 70 AND 100"),
    ("sleep_sessions", "ck_sleep_sessions_sleep_score_plausible",
     "sleep_score IS NULL OR sleep_score BETWEEN 0 AND 100"),
    ("sleep_sessions", "ck_sleep_sessions_respiration_avg_plausible",
     "respiration_avg IS NULL OR respiration_avg BETWEEN 5 AND 60"),
    ("stress_readings", "ck_stress_readings_stress_level_plausible",
     "stress_level IS NULL OR stress_level BETWEEN 0 AND 100"),
    ("stress_readings", "ck_stress_readings_body_battery_plausible",
     "body_battery IS NULL OR body_battery BETWEEN 0 AND 100"),
]


def upgrade() -> None:
    # --- P-02 CHECK constraints ----------------------------------------------
    for table, name, condition in _CHECKS:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})"
        )

    # --- F-08 / D-05: hot-path indexes (CREATE INDEX CONCURRENTLY cannot run
    # inside a transaction — alembic op.execute wraps each in its own
    # autocommit when using these raw SQL strings).
    # The hottest query in the app is sessions.token_hash lookup on every
    # authenticated request. Without an index it is a full scan.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash "
        "ON sessions(token_hash)"
    )
    # Session purge task (F-08) needs expires_at indexed.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at "
        "ON sessions(expires_at)"
    )
    # daily_biometrics had NO user_id index at all — every biometric read
    # scaled linearly with the table.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bio_user_date "
        "ON daily_biometrics(user_id, local_date DESC)"
    )
    # workout_sessions gym-advisor query (D-06) was unbounded.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ws_user_sched "
        "ON workout_sessions(user_id, scheduled_date DESC)"
    )
    # activity_streams lookups by (user_id, activity_id, stream_type) — D-05.
    # Note: activity_streams PK is (activity_id, t_offset_s); add a
    # user-scoped composite for device-merge / reconciliation paths.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_streams_activity "
        "ON activity_streams(activity_id)"
    )
    # Partial index on unprocessed raw_ingest — normalize_pending rescans
    # this set on every checkpoint (D-03 / F-09).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_unproc "
        "ON raw_ingest(user_id, source, id) WHERE processed = false"
    )
    # activity_source_links existence check (F-09): composite on
    # (source, external_id) — already unique per spec but ensure the index
    # exists for batched lookups.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_asl_source_ext "
        "ON activity_source_links(source, external_id)"
    )
    # hrv_readings user+timestamp window scans (engine nightly, D-07).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hrv_user_ts "
        "ON hrv_readings(user_id, timestamp DESC)"
    )
    # sleep_sessions user+local_date (engine + dashboard).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sleep_user_date "
        "ON sleep_sessions(user_id, local_date DESC)"
    )
    # stress_readings user+timestamp window scans.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stress_user_ts "
        "ON stress_readings(user_id, timestamp DESC)"
    )

    # --- F-21: absolute session lifetime column -----------------------------
    # Sliding expiry alone leaves a stolen session valid forever if used
    # ≥1×/half-TTL. absolute_expires_at caps the total lifetime (30d default).
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS absolute_expires_at "
        "TIMESTAMPTZ"
    )
    # Backfill existing rows: their absolute expiry is now + 30d (the new
    # default) — anything older will be purged by the nightly task.
    op.execute(
        "UPDATE sessions SET absolute_expires_at = "
        "COALESCE(absolute_expires_at, created_at + interval '30 days')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_absolute_expires "
        "ON sessions(absolute_expires_at) WHERE absolute_expires_at IS NOT NULL"
    )

    # --- F-19: device-token absolute expiry ---------------------------------
    # Device tokens had no expiry; revocation was manual only.
    op.execute(
        "ALTER TABLE device_tokens ADD COLUMN IF NOT EXISTS absolute_expires_at "
        "TIMESTAMPTZ"
    )
    # Existing tokens get a 1-year absolute expiry from creation (generous
    # grandfathering; new tokens get the configured default at mint time).
    op.execute(
        "UPDATE device_tokens SET absolute_expires_at = "
        "COALESCE(absolute_expires_at, created_at + interval '365 days')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_device_tokens_user "
        "ON device_tokens(user_id, revoked_at)"
    )


def downgrade() -> None:
    # Drop indexes (constraints are dropped per-table below).
    for idx in (
        "idx_device_tokens_user",
        "idx_sessions_absolute_expires",
        "idx_stress_user_ts",
        "idx_sleep_user_date",
        "idx_hrv_user_ts",
        "idx_asl_source_ext",
        "idx_raw_unproc",
        "idx_streams_activity",
        "idx_ws_user_sched",
        "idx_bio_user_date",
        "idx_sessions_expires_at",
        "idx_sessions_token_hash",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx}")

    # Drop CHECK constraints.
    for _table, name, _condition in _CHECKS:
        op.execute(f"ALTER TABLE {_table} DROP CONSTRAINT IF EXISTS {name}")

    # Drop F-21 / F-19 columns.
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS absolute_expires_at")
    op.execute("ALTER TABLE device_tokens DROP COLUMN IF EXISTS absolute_expires_at")
