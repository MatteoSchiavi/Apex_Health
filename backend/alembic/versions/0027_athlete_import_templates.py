"""Separate encrypted import review from canonical profiles and weekly templates."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lab_documents", sa.Column("coach_eligible", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("athlete_import_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("lab_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("proposal_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("source_text_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("receipts", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "version"))
    op.create_index("ix_athlete_import_drafts_user_id", "athlete_import_drafts", ["user_id"])
    op.create_table("weekly_training_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", sa.BigInteger(), sa.ForeignKey("lab_documents.id", ondelete="SET NULL")),
        sa.Column("source_document_revision", sa.Integer()),
        sa.Column("import_draft_id", sa.Integer(), sa.ForeignKey("athlete_import_drafts.id", ondelete="SET NULL"), unique=True),
        sa.Column("structure_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_weekly_training_templates_user_id", "weekly_training_templates", ["user_id"])
    op.alter_column("plan_document_drafts", "document_id", nullable=True)
    op.alter_column("plan_document_drafts", "document_revision", nullable=True)
    op.add_column("plan_document_drafts", sa.Column("template_id", sa.Integer(), sa.ForeignKey("weekly_training_templates.id", ondelete="CASCADE")))
    op.add_column("plan_document_drafts", sa.Column("template_revision", sa.Integer()))
    op.create_unique_constraint("uq_plan_drafts_template_version", "plan_document_drafts", ["template_id", "version"])
    op.create_check_constraint("ck_plan_draft_source", "plan_document_drafts", "(document_id IS NOT NULL AND document_revision IS NOT NULL AND template_id IS NULL AND template_revision IS NULL) OR (document_id IS NULL AND document_revision IS NULL AND template_id IS NOT NULL AND template_revision IS NOT NULL)")
    op.add_column("training_plans", sa.Column("source_template_id", sa.Integer(), sa.ForeignKey("weekly_training_templates.id", ondelete="SET NULL")))


def downgrade():
    # Forward application only: a downgrade with template-backed history would
    # otherwise require deleting reviewed data. Refuse rather than discard it.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM plan_document_drafts WHERE template_id IS NOT NULL) OR EXISTS (SELECT 1 FROM athlete_import_drafts) OR EXISTS (SELECT 1 FROM weekly_training_templates) THEN RAISE EXCEPTION 'Archive import/template records before an explicitly reviewed downgrade'; END IF; END $$")
    op.drop_column("training_plans", "source_template_id")
    op.drop_constraint("ck_plan_draft_source", "plan_document_drafts")
    op.drop_constraint("uq_plan_drafts_template_version", "plan_document_drafts")
    op.drop_column("plan_document_drafts", "template_revision")
    op.drop_column("plan_document_drafts", "template_id")
    op.alter_column("plan_document_drafts", "document_id", nullable=False)
    op.alter_column("plan_document_drafts", "document_revision", nullable=False)
    op.drop_table("weekly_training_templates")
    op.drop_table("athlete_import_drafts")
    op.drop_column("lab_documents", "coach_eligible")
