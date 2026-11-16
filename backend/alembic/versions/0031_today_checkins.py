"""Durable on-open check-in quota, independent of report content retention."""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE today_checkins (
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        local_date DATE NOT NULL,
        slot TEXT NOT NULL CHECK (slot IN ('morning','afternoon')),
        timezone TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        content TEXT,
        source_revision TEXT,
        source_ids JSONB NOT NULL DEFAULT '[]',
        generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, local_date, slot)
    )""")


def downgrade():
    op.drop_table("today_checkins")
