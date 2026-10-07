"""Minimal first-party alpha instrumentation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('alpha_events',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_index('idx_alpha_events_time_event', 'alpha_events', ['created_at', 'event'])
    op.create_index('idx_alpha_events_user_time', 'alpha_events', ['user_id', 'created_at'])


def downgrade():
    op.drop_table('alpha_events')
