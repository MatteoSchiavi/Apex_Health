"""Neutral heuristic names and exact forward calculation provenance.

Historical values are retained; historical provenance remains unavailable.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('daily_features', 'illness_risk_score', new_column_name='systemic_stress_signal')
    op.alter_column('daily_features', 'injury_risk_score', new_column_name='load_spike_indicator')
    op.execute("UPDATE feature_weights SET feature_name='systemic_stress_signal' WHERE feature_name='illness_risk_score'")
    op.execute("UPDATE feature_weights SET feature_name='load_spike_indicator' WHERE feature_name='injury_risk_score'")
    op.add_column('daily_features', sa.Column('calculation_provenance', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('daily_features', 'calculation_provenance')
    op.execute("UPDATE feature_weights SET feature_name='illness_risk_score' WHERE feature_name='systemic_stress_signal'")
    op.execute("UPDATE feature_weights SET feature_name='injury_risk_score' WHERE feature_name='load_spike_indicator'")
    op.alter_column('daily_features', 'systemic_stress_signal', new_column_name='illness_risk_score')
    op.alter_column('daily_features', 'load_spike_indicator', new_column_name='injury_risk_score')
