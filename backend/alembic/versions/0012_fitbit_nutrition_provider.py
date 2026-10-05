"""Permit the Fitbit nutrition OAuth integration without changing stored data."""

from alembic import op
from sqlalchemy import text

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check")
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram','whoop','oura','coros','fitbit'))"
    )


def downgrade() -> None:
    # Disconnected links still hold account-owned integration history. Refuse
    # rollback while any Fitbit rows remain; never erase them silently just
    # to satisfy the older provider constraint.
    count = op.get_bind().execute(
        text("SELECT count(*) FROM integrations WHERE provider='fitbit'")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Fitbit integration records remain; explicitly archive/remove them before downgrading to 0011"
        )
    op.execute("ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check")
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram','whoop','oura','coros'))"
    )
