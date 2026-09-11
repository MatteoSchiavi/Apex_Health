"""Gym schedule model (Phase 10 v2): the RECURRING weekly routine.

Distinct from TrainingPlan/PlannedSession (§6.4), which are week-scoped and
date-anchored: a gym routine is a standing weekly template. The watch and
/gym surfaces resolve a date by taking date-specific planned sessions
(confirmed/active plans) FIRST, then falling back to the recurring slot(s)
for that weekday — see app/queries/gym.py resolve_day.
"""

from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    SmallInteger,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GymScheduleSlot(Base):
    __tablename__ = "gym_schedule_slots"
    __table_args__ = (
        Index(
            "ix_gym_schedule_slots_user_weekday",
            "user_id",
            "weekday",
            unique=False,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Mon..6=Sun
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
