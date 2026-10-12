"""Explicit revocable read-only athlete snapshots; no social or AI grants."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('athlete_shares',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False, unique=True),
        sa.Column('selection', JSONB(), nullable=False),
        sa.Column('dependencies', JSONB(), nullable=False),
        sa.Column('snapshot_ciphertext', sa.LargeBinary()),
        sa.Column('payload_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('erased_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at AND expires_at <= created_at + interval '30 days'", name='ck_share_expiry'))
    op.create_index('ix_athlete_shares_user_id', 'athlete_shares', ['user_id'])
    op.create_index('ix_athlete_shares_expires_at', 'athlete_shares', ['expires_at'])


def downgrade():
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM athlete_shares) THEN RAISE EXCEPTION 'Review and erase share grants before an explicitly approved downgrade'; END IF; END $$")
    op.drop_table('athlete_shares')
