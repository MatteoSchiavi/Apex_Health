"""Owner administration, durable feedback and notification outbox."""
from alembic import op
import sqlalchemy as sa
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("auth_credentials", sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("auth_credentials", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("feedbacks", sa.Column("id",sa.BigInteger(),primary_key=True),sa.Column("user_id",sa.BigInteger(),sa.ForeignKey("users.id"),nullable=False),sa.Column("category",sa.Text(),nullable=False),sa.Column("message",sa.Text(),nullable=False),sa.Column("page_url",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("now()")))
    op.create_index("ix_feedbacks_user_id","feedbacks",["user_id"])
    op.create_table("owner_notifications",sa.Column("id",sa.BigInteger(),primary_key=True),sa.Column("event_key",sa.Text(),unique=True),sa.Column("feedback_id",sa.BigInteger(),sa.ForeignKey("feedbacks.id")),sa.Column("kind",sa.Text(),nullable=False),sa.Column("message",sa.Text(),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False,server_default="0"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("now()")),sa.Column("next_attempt_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("now()")),sa.Column("delivered_at",sa.DateTime(timezone=True)))
    op.create_index("ix_owner_notifications_feedback_id","owner_notifications",["feedback_id"])
    op.create_index("ix_owner_notifications_next_attempt_at","owner_notifications",["next_attempt_at"])

def downgrade():
    op.drop_table("owner_notifications")
    op.drop_table("feedbacks")
    op.drop_column("auth_credentials","last_login_at")
    op.drop_column("auth_credentials","disabled")
