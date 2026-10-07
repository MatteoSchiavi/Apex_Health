"""Declare the method and units of comparable rolling load windows.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('daily_features', sa.Column('load_metadata', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('daily_features', 'load_metadata')
