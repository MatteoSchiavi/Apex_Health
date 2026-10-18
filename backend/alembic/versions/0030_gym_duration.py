"""Keep timed gym holds separate from repetitions and lifted volume."""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("gym_day_plans_status_check", "gym_day_plans", type_="check")
    op.create_check_constraint("gym_day_plans_status_check", "gym_day_plans",
        "status IN ('draft','confirmed','active','done')")
    op.add_column("gym_day_exercises", sa.Column("duration_min_s", sa.Integer(), nullable=True))
    op.add_column("gym_day_exercises", sa.Column("duration_max_s", sa.Integer(), nullable=True))
    op.alter_column("gym_day_exercises", "reps_min", existing_type=sa.SmallInteger(), nullable=True)
    op.add_column("gym_set_logs", sa.Column("duration_s", sa.Integer(), nullable=True))
    op.alter_column("gym_set_logs", "reps_done", existing_type=sa.SmallInteger(), nullable=True)
    # Historical records have no reliable unit provenance. Preserve them exactly.
    op.create_check_constraint("ck_gym_duration_target", "gym_day_exercises",
        "(duration_min_s IS NULL AND duration_max_s IS NULL AND reps_min IS NOT NULL) OR "
        "(duration_min_s IS NOT NULL AND duration_min_s > 0 AND duration_min_s <= 86400 AND reps_min IS NULL AND reps_max IS NULL "
        "AND (duration_max_s IS NULL OR (duration_max_s >= duration_min_s AND duration_max_s <= 86400)))")
    op.create_check_constraint("ck_gym_set_measurement", "gym_set_logs",
        "(duration_s IS NULL AND reps_done IS NOT NULL) OR "
        "(duration_s IS NOT NULL AND duration_s > 0 AND duration_s <= 86400 AND reps_done IS NULL)")


def downgrade():
    # Do not silently turn seconds into repetitions or discard recorded holds.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM gym_set_logs WHERE duration_s IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM gym_day_exercises WHERE duration_min_s IS NOT NULL) "
        "THEN RAISE EXCEPTION 'Timed gym records require an explicit export and review before downgrade'; END IF; END $$")
    # Older code derives progress from logs while the plan stays confirmed.
    op.execute("UPDATE gym_day_plans SET status='confirmed' WHERE status='active'")
    op.drop_constraint("gym_day_plans_status_check", "gym_day_plans", type_="check")
    op.create_check_constraint("gym_day_plans_status_check", "gym_day_plans",
        "status IN ('draft','confirmed','done')")
    op.drop_constraint("ck_gym_set_measurement", "gym_set_logs", type_="check")
    op.drop_constraint("ck_gym_duration_target", "gym_day_exercises", type_="check")
    op.alter_column("gym_set_logs", "reps_done", existing_type=sa.SmallInteger(), nullable=False)
    op.drop_column("gym_set_logs", "duration_s")
    op.alter_column("gym_day_exercises", "reps_min", existing_type=sa.SmallInteger(), nullable=False)
    op.drop_column("gym_day_exercises", "duration_max_s")
    op.drop_column("gym_day_exercises", "duration_min_s")
