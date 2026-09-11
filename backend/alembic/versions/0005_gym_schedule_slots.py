"""gym_schedule_slots — the user's RECURRING weekly gym schedule (Phase 10 v2,
the rethought watch app).

Why this table exists: training_plans/planned_sessions (§6.4) model a
WEEK-SCOPED plan — AI-proposed or manual, one specific week at a time. A gym
ROUTINE ("Mon 18:00 Push, Wed 18:00 Pull, Fri 18:00 Legs") is a standing
weekly template that must survive week rollover without anybody re-entering
it. The watch app (Phase 10 v2) reads this template for any date that has no
date-specific planned session: planned sessions OVERRIDE the recurring slot
on their dates, so the AI plan and the routine compose instead of duplicating
(documented judgment call — §6.4 has no recurring-schedule concept).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE gym_schedule_slots (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id),
            weekday     SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),  -- 0=Mon .. 6=Sun
            start_time  TIME NOT NULL,
            title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 60),
            description TEXT,                                               -- exercises / notes
            active      BOOLEAN NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX ix_gym_schedule_slots_user_weekday
            ON gym_schedule_slots (user_id, weekday) WHERE active;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE gym_schedule_slots;")
