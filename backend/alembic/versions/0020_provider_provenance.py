"""Forward provider provenance; legacy attribution is intentionally unknown."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sleep_sessions', sa.Column('origin', sa.Text(), nullable=True))
    op.add_column('sleep_sessions', sa.Column('source_metrics', postgresql.JSONB(), nullable=True))
    op.add_column('hrv_readings', sa.Column('origin', sa.Text(), nullable=True))
    op.add_column('hrv_readings', sa.Column('method', sa.Text(), nullable=True))
    op.create_index('idx_hrv_origin_method_time', 'hrv_readings', ['user_id', 'origin', 'method', 'timestamp'])


def downgrade():
    op.drop_index('idx_hrv_origin_method_time', table_name='hrv_readings')
    op.drop_column('hrv_readings', 'method')
    op.drop_column('hrv_readings', 'origin')
    op.drop_column('sleep_sessions', 'origin')
    op.drop_column('sleep_sessions', 'source_metrics')
