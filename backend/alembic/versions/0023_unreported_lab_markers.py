"""Preserve reported intervals when a laboratory measurement is absent.

No values are synthesized and no existing measured values are rewritten.
Downgrade refuses while null measurements exist instead of deleting them or
inventing readings to satisfy the old NOT NULL constraint.
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("lab_metrics", "value", existing_type=sa.Numeric(), nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM lab_metrics WHERE value IS NULL)")).scalar():
        raise RuntimeError("Cannot downgrade: unreported lab measurements exist. Preserve/export and explicitly resolve these records before restoring NOT NULL; no measurements were deleted or invented.")
    op.alter_column("lab_metrics", "value", existing_type=sa.Numeric(), nullable=False)
