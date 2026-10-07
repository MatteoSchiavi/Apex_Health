"""Backfill known embedding owners without destroying unknown legacy vectors."""
from alembic import op
import sqlalchemy as sa
revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('embeddings', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_embedding_owner', 'embeddings', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.execute("UPDATE embeddings e SET user_id=j.user_id FROM journal_entries j JOIN users u ON u.id=j.user_id WHERE e.source_table='journal_entries' AND e.source_id=j.id")
    op.execute("UPDATE embeddings e SET user_id=r.user_id FROM ai_reports r JOIN users u ON u.id=r.user_id WHERE e.source_table='ai_reports' AND e.source_id=r.id")
    op.create_index('ix_embeddings_user_id', 'embeddings', ['user_id'])


def downgrade():
    op.drop_index('ix_embeddings_user_id', table_name='embeddings')
    op.drop_constraint('fk_embedding_owner', 'embeddings')
    op.drop_column('embeddings', 'user_id')
