"""Preserve imported HRV without inventing a measurement context."""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('hrv_readings_reading_type_check', 'hrv_readings', type_='check')
    op.create_check_constraint('hrv_readings_reading_type_check', 'hrv_readings',
        "reading_type IN ('overnight_avg', '5min', 'unspecified')")


def downgrade():
    # The old schema cannot represent these rows. Refuse rather than silently
    # deleting measurements or relabeling them as overnight/daytime readings.
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM hrv_readings WHERE reading_type='unspecified')")):
        raise RuntimeError('Cannot downgrade: unspecified HRV contexts require an explicit export/removal decision')
    op.drop_constraint('hrv_readings_reading_type_check', 'hrv_readings', type_='check')
    op.create_check_constraint('hrv_readings_reading_type_check', 'hrv_readings',
        "reading_type IN ('overnight_avg', '5min')")
