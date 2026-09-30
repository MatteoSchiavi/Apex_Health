"""Seed data — disciplines (MASTER_SPEC §6.1).

"disciplines is populated via an Alembic data migration" — never invented ad
hoc at runtime (§17). Categories use the spec's obvious mapping: pedaled/run
sports are endurance, gym work is strength, everything else technical.
Idempotent: ON CONFLICT (name) DO NOTHING.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_DISCIPLINES = [
    ("enduro", "endurance"),
    ("road_cycling", "endurance"),
    ("skiing", "technical"),
    ("sailing", "technical"),
    ("kitesurf", "technical"),
    ("windsurf", "technical"),
    ("tennis", "technical"),
    ("wakeboard", "technical"),
    ("snowboard", "technical"),
    ("surf", "technical"),
    ("sim_racing", "technical"),
    ("running", "endurance"),
    ("strength", "strength"),
    ("gym_general", "strength"),
]


def upgrade() -> None:
    # Per-row inserts keep the SQL trivially reviewable and idempotent.
    for name, category in _SEED_DISCIPLINES:
        op.execute(
            "INSERT INTO disciplines (name, category) VALUES "
            f"('{name}', '{category}') "
            "ON CONFLICT (name) DO NOTHING;"
        )


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name, _ in _SEED_DISCIPLINES)
    op.execute(f"DELETE FROM disciplines WHERE name IN ({names});")
