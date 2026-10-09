"""Connect optional profile targets to the existing calendar spine."""
from alembic import op
import sqlalchemy as sa
revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("user_events", sa.Column("profile_focus", sa.Text(), nullable=True))
    op.add_column("user_events", sa.Column("date_only", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_unique_constraint("uq_user_events_profile_focus", "user_events", ["user_id", "profile_focus"])
    op.create_check_constraint("ck_user_events_profile_focus", "user_events", "profile_focus IS NULL OR profile_focus IN ('gym','running','cycling')")

def downgrade():
    op.drop_constraint("ck_user_events_profile_focus", "user_events")
    op.drop_constraint("uq_user_events_profile_focus", "user_events")
    op.drop_column("user_events", "date_only")
    op.drop_column("user_events", "profile_focus")
