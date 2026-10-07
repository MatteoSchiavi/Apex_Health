"""Revocable HealthKit sync scope and durable delta state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('device_tokens', sa.Column('scope', sa.Text(), nullable=False, server_default='watch_read'))
    op.add_column('device_tokens', sa.Column('sync_checkpoint', sa.Integer(), nullable=False, server_default='0'))
    op.create_check_constraint('ck_device_token_scope', 'device_tokens', "scope IN ('watch_read', 'healthkit_sync')")
    op.create_table('healthkit_pairings',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.Text(), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)))
    op.create_index('ix_healthkit_pairings_user_id', 'healthkit_pairings', ['user_id'])
    op.create_table('healthkit_samples',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('uuid', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('payload', postgresql.JSONB()),
        sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False))
    op.execute("CREATE INDEX ix_healthkit_active_local_day ON healthkit_samples (user_id, (payload->>'local_date')) WHERE NOT deleted")
    op.execute("CREATE INDEX ix_healthkit_active_sleep_day ON healthkit_samples (user_id, (payload->>'end_local_date')) WHERE NOT deleted AND payload->>'type'='HKCategoryTypeIdentifierSleepAnalysis'")
    op.create_table('healthkit_batches',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('device_id', sa.BigInteger(), sa.ForeignKey('device_tokens.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_hash', sa.Text(), nullable=False),
        sa.Column('checkpoint', sa.Integer(), nullable=False),
        sa.Column('receipt', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('device_id', 'batch_id'))
    op.create_index('ix_healthkit_batches_device_id', 'healthkit_batches', ['device_id'])


def downgrade():
    op.drop_table('healthkit_batches')
    op.drop_table('healthkit_samples')
    op.drop_table('healthkit_pairings')
    op.drop_constraint('ck_device_token_scope', 'device_tokens')
    op.drop_column('device_tokens', 'sync_checkpoint')
    op.drop_column('device_tokens', 'scope')
