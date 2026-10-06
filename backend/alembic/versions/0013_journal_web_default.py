"""Make new journal entries default to the web source after removing Telegram."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE journal_entries ALTER COLUMN source SET DEFAULT 'web'")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE journal_entries ALTER COLUMN source SET DEFAULT 'telegram_text'"
    )
