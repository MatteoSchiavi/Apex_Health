"""Scope provider identifiers to their account and enforce link ownership.

Existing links retain their IDs and activities; ownership is backfilled from
the canonical activity. Downgrade refuses to discard valid cross-user links.
"""

from alembic import op
from sqlalchemy import text

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE activity_source_links ADD COLUMN user_id BIGINT")
    op.execute("""
        UPDATE activity_source_links AS link SET user_id = activity.user_id
        FROM activities AS activity WHERE activity.id = link.activity_id
    """)
    op.execute("ALTER TABLE activity_source_links ALTER COLUMN user_id SET NOT NULL")
    op.create_unique_constraint("uq_activity_id_user", "activities", ["id", "user_id"])
    op.create_foreign_key(
        "fk_source_link_activity_owner", "activity_source_links", "activities",
        ["activity_id", "user_id"], ["id", "user_id"],
    )
    op.drop_constraint("activity_source_links_activity_id_fkey", "activity_source_links", type_="foreignkey")
    op.drop_constraint("activity_source_links_source_external_id_key", "activity_source_links", type_="unique")
    op.drop_index("idx_asl_source_ext", table_name="activity_source_links")
    op.create_unique_constraint(
        "uq_source_link_user_external", "activity_source_links", ["user_id", "source", "external_id"],
    )


def downgrade() -> None:
    # Check before changing schema. A rollback must never delete user data.
    if op.get_bind().scalar(text("""
        SELECT EXISTS (
            SELECT 1 FROM activity_source_links GROUP BY source, external_id
            HAVING count(*) > 1
        )
    """)):
        raise RuntimeError("Cannot downgrade: provider IDs are shared by multiple accounts; no data was removed.")
    op.create_unique_constraint(
        "activity_source_links_source_external_id_key", "activity_source_links", ["source", "external_id"],
    )
    op.create_index("idx_asl_source_ext", "activity_source_links", ["source", "external_id"])
    op.create_foreign_key(
        "activity_source_links_activity_id_fkey", "activity_source_links", "activities", ["activity_id"], ["id"],
    )
    op.drop_constraint("uq_source_link_user_external", "activity_source_links", type_="unique")
    op.drop_constraint("fk_source_link_activity_owner", "activity_source_links", type_="foreignkey")
    op.drop_constraint("uq_activity_id_user", "activities", type_="unique")
    op.drop_column("activity_source_links", "user_id")
