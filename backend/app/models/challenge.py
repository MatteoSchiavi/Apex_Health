"""Friendly multi-user challenges (owner feature batch, 2026-09).

Metrics are computed on the fly from canonical tables (app/queries/
rankings.py) — no materialized results table; at friends-scale the live
aggregation is cheap and always consistent with freshly synced data.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # activities_count | steps | distance_m | intensity_minutes |
    # sleep_score_avg | training_load_sum | 5k_time_s
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    # all_time | weekly | monthly | custom (starts_at/ends_at set)
    period: Mapped[str] = mapped_column(
        Text, nullable=False, default="all_time", server_default="all_time"
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class ChallengeMember(Base):
    __tablename__ = "challenge_members"

    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
