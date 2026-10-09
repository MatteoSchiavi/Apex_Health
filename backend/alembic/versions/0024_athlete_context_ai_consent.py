"""Optional athlete priorities, voluntary consent and atomic AI budget reservations."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("athlete_profiles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("training_focus", JSONB(), nullable=False, server_default="[]"),
        sa.Column("context", JSONB(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("jsonb_typeof(training_focus) = 'array' AND jsonb_array_length(training_focus) <= 3"),
        sa.CheckConstraint("revision > 0"))
    op.create_table("ai_consents",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("provider_identity", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)))
    op.create_table("ai_budget_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(), nullable=False),
        sa.Column("actual_usd", sa.Numeric()),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("actual_tokens", sa.Integer()),
        sa.Column("state", sa.Text(), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("category IN ('onboarding_extraction', 'standard_chat', 'strategic_coaching', 'periodic_reports')"),
        sa.CheckConstraint("state IN ('reserved', 'reconciled', 'uncertain')"))
    op.create_index("ix_ai_budget_reservations_user_id", "ai_budget_reservations", ["user_id"])
    op.create_index("ix_ai_budget_reservations_day", "ai_budget_reservations", ["day"])


def downgrade():
    op.drop_table("ai_budget_reservations")
    op.drop_table("ai_consents")
    op.drop_table("athlete_profiles")
