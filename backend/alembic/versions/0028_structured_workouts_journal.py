"""Canonical session workout versions and optional subjective journal detail."""
from alembic import op
import sqlalchemy as sa
revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('structured_workout_versions',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('planned_session_id',sa.BigInteger(),sa.ForeignKey('planned_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('structure_ciphertext',sa.LargeBinary(),nullable=False),
        sa.Column('payload_hash',sa.Text(),nullable=False),sa.Column('source',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
        sa.UniqueConstraint('planned_session_id','revision'))
    op.create_index('ix_structured_workout_versions_user_id','structured_workout_versions',['user_id'])
    op.create_index('ix_structured_workout_versions_planned_session_id','structured_workout_versions',['planned_session_id'])
    op.create_table('structured_workout_drafts',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.BigInteger(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('planned_session_id',sa.BigInteger(),sa.ForeignKey('planned_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('plan_revision',sa.Integer(),nullable=False),sa.Column('workout_revision',sa.Integer(),nullable=False),
        sa.Column('structure_ciphertext',sa.LargeBinary(),nullable=False),sa.Column('payload_hash',sa.Text(),nullable=False),
        sa.Column('status',sa.Text(),nullable=False),
        sa.Column('version_id',sa.Integer(),sa.ForeignKey('structured_workout_versions.id',ondelete='SET NULL')),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')))
    op.create_index('ix_structured_workout_drafts_user_id','structured_workout_drafts',['user_id'])
    op.create_index('ix_structured_workout_drafts_planned_session_id','structured_workout_drafts',['planned_session_id'])
    for name in ('fatigue','soreness','workout_quality'):
        op.add_column('athlete_session_checkins',sa.Column(name,sa.Integer(),nullable=True))
        op.create_check_constraint('ck_checkin_'+name,'athlete_session_checkins',f'{name} IS NULL OR ({name} BETWEEN 0 AND 10)')
    for name in ('modification_reason','terrain_notes'):
        op.add_column('athlete_session_checkins',sa.Column(name,sa.Text(),nullable=False,server_default=''))


def downgrade():
    for name in ('modification_reason','terrain_notes'):
        op.drop_column('athlete_session_checkins',name)
    for name in ('fatigue','soreness','workout_quality'):
        op.drop_constraint('ck_checkin_'+name,'athlete_session_checkins',type_='check')
        op.drop_column('athlete_session_checkins',name)
    op.drop_table('structured_workout_drafts')
    op.drop_table('structured_workout_versions')
