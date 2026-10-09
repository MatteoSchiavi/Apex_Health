"""Reviewed encrypted plan drafts, protected multi-session baselines and check-ins."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("plan_document_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("lab_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("structure_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "version"))
    op.create_index("ix_plan_document_drafts_user_id", "plan_document_drafts", ["user_id"])
    for column in [
        sa.Column("source_document_id", sa.BigInteger(), sa.ForeignKey("lab_documents.id", ondelete="SET NULL")),
        sa.Column("source_document_revision", sa.Integer()),
        sa.Column("extraction_id", sa.Integer(), sa.ForeignKey("plan_document_drafts.id", ondelete="SET NULL")),
        sa.Column("title", sa.Text()), sa.Column("end_date", sa.Date()),
        sa.Column("activated_on", sa.Date()), sa.Column("superseded_on", sa.Date()),
        sa.Column("protected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1")]:
        op.add_column("training_plans", column)
    for column in [sa.Column("protected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("start_time", sa.Time()), sa.Column("target_distance_m", sa.Numeric()),
        sa.Column("intensity_targets", JSONB(), nullable=False, server_default="{}")]:
        op.add_column("planned_sessions", column)
    op.create_table("activity_plan_links",
        sa.Column("activity_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_session_id", sa.BigInteger(), sa.ForeignKey("planned_sessions.id", ondelete="CASCADE"), unique=True),
        sa.Column("method", sa.Text(), nullable=False, server_default="user_confirmed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["activity_id", "user_id"], ["activities.id", "activities.user_id"], ondelete="CASCADE"))
    op.create_index("ix_activity_plan_links_user_id", "activity_plan_links", ["user_id"])
    op.create_table("athlete_session_checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", sa.BigInteger()),
        sa.Column("planned_session_id", sa.BigInteger(), sa.ForeignKey("planned_sessions.id", ondelete="CASCADE")),
        sa.Column("status", sa.Text(), nullable=False), sa.Column("rpe", sa.Integer()),
        sa.Column("pain", sa.Boolean()), sa.Column("felt_unwell", sa.Boolean()),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["activity_id", "user_id"], ["activities.id", "activities.user_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "activity_id"), sa.UniqueConstraint("user_id", "planned_session_id"),
        sa.CheckConstraint("activity_id IS NOT NULL OR planned_session_id IS NOT NULL"),
        sa.CheckConstraint("status IN ('completed', 'partial', 'skipped')"),
        sa.CheckConstraint("rpe BETWEEN 0 AND 10"))
    op.create_index("ix_athlete_session_checkins_user_id", "athlete_session_checkins", ["user_id"])


def downgrade():
    op.drop_table("athlete_session_checkins")
    op.drop_table("activity_plan_links")
    for key in ("protected", "start_time", "target_distance_m", "intensity_targets"):
        op.drop_column("planned_sessions", key)
    for key in ("source_document_id", "source_document_revision", "extraction_id", "title", "end_date", "activated_on", "superseded_on", "protected", "revision"):
        op.drop_column("training_plans", key)
    op.drop_table("plan_document_drafts")
