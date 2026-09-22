"""Multi-device + coach + social layer.

Owner decision (2026-09 session): Whoop becomes a first-class primary device
alongside Garmin, so the `integrations.provider` CHECK gains 'whoop'
('strava' was already allowed by 0001). Canonical tables gain a
`source_metrics` JSONB column so provider-specific quantities that MUST NOT
be merged into Garmin-comparable columns (Whoop Strain 0-21 vs TRIMP-style
training_load, Whoop Recovery %, zone durations) travel alongside the
canonical data without corrupting cross-device features (§17 annotation law:
same metric name == same unit and semantics, always).

New capability tables (owner feature batch):
- user_events          — the calendar: races, trips, ski weeks, ...
- user_context_docs    — per-user AI context documents (profile, goals,
                         injuries, equipment, preferences, season plan)
- gym_exercises        — exercise catalog (muscle group, movement pattern,
                         impact level) seeded idempotently
- gym_day_plans / gym_day_exercises / gym_set_logs — the concrete gym day:
                         exercises, sets/reps/rest, and the in-gym set log
                         that powers the "next exercise + rest timer" surface
- session_feedback     — post-session feedback (RPE, soreness areas, injury
                         flags) that steers the adaptive gym engine
- challenges / challenge_members — friendly multi-user challenges

All new TIMESTAMPTZ columns per the day-boundary TZ law (§17).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEED_EXERCISES = [
    # name, muscle_group, movement_pattern, impact_level, equipment
    ("Back Squat", "legs", "squat", "low", "barbell"),
    ("Front Squat", "legs", "squat", "low", "barbell"),
    ("Goblet Squat", "legs", "squat", "low", "kettlebell"),
    ("Deadlift", "legs", "hinge", "medium", "barbell"),
    ("Romanian Deadlift", "legs", "hinge", "low", "barbell"),
    ("Hip Thrust", "legs", "hinge", "low", "barbell"),
    ("Leg Press", "legs", "squat", "low", "machine"),
    ("Bulgarian Split Squat", "legs", "lunge", "low", "dumbbell"),
    ("Walking Lunge", "legs", "lunge", "medium", "bodyweight"),
    ("Leg Curl", "legs", "hinge", "low", "machine"),
    ("Calf Raise", "legs", "isolation", "low", "machine"),
    ("Box Jump", "legs", "plyo", "high", "box"),
    ("Jump Squat", "legs", "plyo", "high", "bodyweight"),
    ("Bench Press", "push", "push_h", "low", "barbell"),
    ("Incline Bench Press", "push", "push_h", "low", "barbell"),
    ("Overhead Press", "push", "push_v", "low", "barbell"),
    ("Push-Up", "push", "push_h", "low", "bodyweight"),
    ("Dips", "push", "push_v", "medium", "bodyweight"),
    ("Lateral Raise", "push", "isolation", "low", "dumbbell"),
    ("Triceps Pushdown", "push", "isolation", "low", "machine"),
    ("Pull-Up", "pull", "pull_v", "medium", "bodyweight"),
    ("Lat Pulldown", "pull", "pull_v", "low", "machine"),
    ("Bent-Over Row", "pull", "pull_h", "medium", "barbell"),
    ("Seated Cable Row", "pull", "pull_h", "low", "machine"),
    ("Face Pull", "pull", "pull_h", "low", "machine"),
    ("Biceps Curl", "pull", "isolation", "low", "dumbbell"),
    ("Plank", "core", "core_anti", "low", "bodyweight"),
    ("Hanging Leg Raise", "core", "core_flex", "medium", "bodyweight"),
    ("Pallof Press", "core", "core_anti", "low", "cable"),
    ("Dead Bug", "core", "core_anti", "low", "bodyweight"),
    ("Kettlebell Swing", "full_body", "hinge_explosive", "medium", "kettlebell"),
    ("Farmer's Carry", "full_body", "carry", "low", "dumbbell"),
    ("Burpee", "full_body", "full_body_explosive", "high", "bodyweight"),
    ("Clean and Press", "full_body", "full_body_explosive", "medium", "barbell"),
]


def upgrade() -> None:
    # --- Whoop as a first-class provider -----------------------------------
    op.execute(
        "ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check"
    )
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram','whoop'))"
    )

    # --- provider-specific metrics ride along canonical rows ---------------
    # (Whoop Strain/Recovery/zone minutes are NOT unit-compatible with the
    # canonical training_load / feature-engine inputs — see module docstring.)
    op.execute("ALTER TABLE activities ADD COLUMN source_metrics JSONB")
    op.execute("ALTER TABLE daily_biometrics ADD COLUMN source_metrics JSONB")

    # Non-Garmin sources can produce activities with no resolvable discipline
    # (unknown Whoop sport names, unmapped Strava sport types, CSV rows) —
    # 0001's NOT NULL assumed a single-Garmin world. NULL stays a documented
    # state the reconciler/agent can resolve later; never invent (§17).
    op.execute("ALTER TABLE activities ALTER COLUMN discipline_id DROP NOT NULL")

    # --- calendar -----------------------------------------------------------
    op.execute("""
        CREATE TABLE user_events (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id),
            title       TEXT NOT NULL,
            kind        TEXT NOT NULL CHECK (kind IN (
                            'race','run','ride','ski','enduro','sailing',
                            'competition','trip','training_camp','gym','other')),
            starts_at   TIMESTAMPTZ NOT NULL,
            ends_at     TIMESTAMPTZ,
            priority    SMALLINT NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
            taper_days  SMALLINT NOT NULL DEFAULT 3 CHECK (taper_days BETWEEN 0 AND 21),
            notes       TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX ix_user_events_user_starts "
        "ON user_events (user_id, starts_at)"
    )

    # --- AI context documents ----------------------------------------------
    op.execute("""
        CREATE TABLE user_context_docs (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id),
            doc_kind    TEXT NOT NULL CHECK (doc_kind IN (
                            'profile','goals','injuries','equipment',
                            'preferences','season_plan')),
            content     TEXT NOT NULL,
            updated_by  TEXT NOT NULL DEFAULT 'user',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, doc_kind)
        );
    """)

    # --- gym exercise catalog ------------------------------------------------
    op.execute("""
        CREATE TABLE gym_exercises (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            muscle_group    TEXT NOT NULL CHECK (muscle_group IN (
                                'legs','push','pull','core','full_body')),
            movement_pattern TEXT NOT NULL,
            impact_level    TEXT NOT NULL DEFAULT 'low' CHECK (
                                impact_level IN ('low','medium','high')),
            equipment       TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    rows = ",\n    ".join(
        "('{name}', '{group}', '{pattern}', '{impact}', '{equip}')".format(
            name=name.replace("'", "''"),
            group=group,
            pattern=pattern,
            impact=impact,
            equip=equip.replace("'", "''"),
        )
        for name, group, pattern, impact, equip in _SEED_EXERCISES
    )
    op.execute(f"""
        INSERT INTO gym_exercises (name, muscle_group, movement_pattern, impact_level, equipment)
        VALUES
    {rows}
        ON CONFLICT (name) DO NOTHING;
    """)

    # --- gym day plans + set logs -------------------------------------------
    op.execute("""
        CREATE TABLE gym_day_plans (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id         BIGINT NOT NULL REFERENCES users(id),
            date            DATE NOT NULL,
            title           TEXT NOT NULL,
            source          TEXT NOT NULL DEFAULT 'manual' CHECK (
                                source IN ('ai','manual','template')),
            status          TEXT NOT NULL DEFAULT 'draft' CHECK (
                                status IN ('draft','confirmed','done')),
            adjustment_note TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, date)
        );
    """)
    op.execute("""
        CREATE TABLE gym_day_exercises (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            gym_day_plan_id     BIGINT NOT NULL REFERENCES gym_day_plans(id) ON DELETE CASCADE,
            exercise_id         BIGINT NOT NULL REFERENCES gym_exercises(id),
            position            SMALLINT NOT NULL,
            sets                SMALLINT NOT NULL CHECK (sets BETWEEN 1 AND 15),
            reps_min            SMALLINT NOT NULL,
            reps_max            SMALLINT,
            rest_seconds        INTEGER NOT NULL DEFAULT 90,
            notes               TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX ix_gym_day_exercises_plan "
        "ON gym_day_exercises (gym_day_plan_id, position)"
    )
    op.execute("""
        CREATE TABLE gym_set_logs (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id             BIGINT NOT NULL REFERENCES users(id),
            gym_day_exercise_id BIGINT NOT NULL REFERENCES gym_day_exercises(id) ON DELETE CASCADE,
            set_number          SMALLINT NOT NULL,
            reps_done           SMALLINT NOT NULL,
            weight_kg           NUMERIC,
            done_at             TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX ix_gym_set_logs_user_time "
        "ON gym_set_logs (user_id, done_at)"
    )

    # --- session feedback -----------------------------------------------------
    op.execute("""
        CREATE TABLE session_feedback (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id       BIGINT NOT NULL REFERENCES users(id),
            date          DATE NOT NULL,
            activity_kind TEXT NOT NULL,
            rpe           SMALLINT CHECK (rpe BETWEEN 1 AND 10),
            soreness      JSONB,
            injury_flag   BOOLEAN NOT NULL DEFAULT false,
            notes         TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX ix_session_feedback_user_date "
        "ON session_feedback (user_id, date DESC)"
    )

    # --- challenges -----------------------------------------------------------
    op.execute("""
        CREATE TABLE challenges (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name        TEXT NOT NULL,
            metric      TEXT NOT NULL CHECK (metric IN (
                            'activities_count','steps','distance_m',
                            'intensity_minutes','sleep_score_avg',
                            'training_load_sum','5k_time_s')),
            period      TEXT NOT NULL DEFAULT 'all_time' CHECK (period IN (
                            'all_time','weekly','monthly','custom')),
            starts_at   TIMESTAMPTZ,
            ends_at     TIMESTAMPTZ,
            created_by  BIGINT NOT NULL REFERENCES users(id),
            is_active   BOOLEAN NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE TABLE challenge_members (
            challenge_id    BIGINT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
            user_id         BIGINT NOT NULL REFERENCES users(id),
            joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (challenge_id, user_id)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS challenge_members")
    op.execute("DROP TABLE IF EXISTS challenges")
    op.execute("DROP TABLE IF EXISTS session_feedback")
    op.execute("DROP TABLE IF EXISTS gym_set_logs")
    op.execute("DROP TABLE IF EXISTS gym_day_exercises")
    op.execute("DROP TABLE IF EXISTS gym_day_plans")
    op.execute("DROP TABLE IF EXISTS gym_exercises")
    op.execute("DROP TABLE IF EXISTS user_context_docs")
    op.execute("DROP INDEX IF EXISTS ix_user_events_user_starts")
    op.execute("DROP TABLE IF EXISTS user_events")
    op.execute("ALTER TABLE daily_biometrics DROP COLUMN IF EXISTS source_metrics")
    op.execute("ALTER TABLE activities DROP COLUMN IF EXISTS source_metrics")
    op.execute("DELETE FROM activities WHERE discipline_id IS NULL")
    op.execute("ALTER TABLE activities ALTER COLUMN discipline_id SET NOT NULL")
    op.execute(
        "ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check"
    )
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram'))"
    )
