"""Feature-engine models (MASTER_SPEC §6.4): feature_weights, daily_features,
discipline_features.

feature_weights selection rule (§6.4): for a given (feature_name,
component_name) and computation date D, use the row with the latest
effective_from <= D. Historical daily_features stay reproducible with the
weights that were active then; a correction is fixing the weights row and
re-running the nightly task for the affected range (upsert by (user_id, date)
makes that a safe backfill).

daily_features.date / discipline_features.date are the USER'S LOCAL dates
(§17 day-boundary rule), never UTC.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeatureWeight(Base):
    __tablename__ = "feature_weights"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_name: Mapped[str] = mapped_column(Text, nullable=False)
    component_name: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DailyFeature(Base):
    __tablename__ = "daily_features"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)  # user's local date (§17)
    recovery_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    strain_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    readiness_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    training_load_acute: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    training_load_chronic: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    acwr: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    sleep_architecture_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    hrv_deviation_from_baseline: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    illness_risk_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    injury_risk_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    iron_status_flag: Mapped[str | None] = mapped_column(Text, nullable=True)
    cross_discipline_fatigue_index: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    data_completeness: Mapped[str] = mapped_column(
        Text, nullable=False, default="full", server_default="full"
    )


class DisciplineFeature(Base):
    __tablename__ = "discipline_features"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("disciplines.id"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)  # user's local date (§17)
    estimated_ftp: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    aerobic_decoupling_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    efficiency_factor: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
