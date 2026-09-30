"""Wellness models (MASTER_SPEC §6.4): sleep_sessions, hrv_readings,
stress_readings, daily_biometrics.

sleep_sessions / hrv_readings / stress_readings are TimescaleDB hypertables
(migration-owned); daily_grain daily_biometrics is a plain (user_id, date)
table — §6.4 hypertable criterion.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SleepSession(Base):
    __tablename__ = "sleep_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # §17: calendar date of end_time (wake-up) in the user's local time.
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_sleep_s: Mapped[int | None] = mapped_column(nullable=True)
    deep_s: Mapped[int | None] = mapped_column(nullable=True)
    light_s: Mapped[int | None] = mapped_column(nullable=True)
    rem_s: Mapped[int | None] = mapped_column(nullable=True)
    awake_s: Mapped[int | None] = mapped_column(nullable=True)
    sleep_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    respiration_avg: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    spo2_avg: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    restlessness: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class HrvReading(Base):
    __tablename__ = "hrv_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        "timestamp", DateTime(timezone=True), primary_key=True
    )
    hrv_ms: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    reading_type: Mapped[str] = mapped_column(Text, nullable=False)
    rolling_baseline_ms: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class StressReading(Base):
    __tablename__ = "stress_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        "timestamp", DateTime(timezone=True), primary_key=True
    )
    stress_level: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    body_battery: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class DailyBiometric(Base):
    __tablename__ = "daily_biometrics"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    # §17: the user's LOCAL date, never UTC.
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    resting_hr: Mapped[int | None] = mapped_column(nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    vo2max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    steps: Mapped[int | None] = mapped_column(nullable=True)
    floors: Mapped[int | None] = mapped_column(nullable=True)
    spo2_avg: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    hydration_ml: Mapped[int | None] = mapped_column(nullable=True)
    # Provider-specific quantities that must NOT be folded into the unit-
    # compatible columns above (Whoop Recovery %, day Strain, skin temp...).
    # Keyed {"whoop": {...}, ...} — migration 0006.
    source_metrics: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
