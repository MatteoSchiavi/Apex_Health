"""Gear-domain models (MASTER_SPEC §6.4, §13): gear, gear_service_logs,
discipline_gear_defaults, activity_gear_links.

Usage counters (hours_since_service / km_since_service) are RECOMPUTED by the
nightly accumulation job (§13, §17 idempotency) — never incremented in place.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Gear(Base):
    __tablename__ = "gear"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gear_type: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_interval_hours: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    service_interval_km: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    hours_since_service: Mapped[Decimal] = mapped_column(
        Numeric, nullable=False, default=0, server_default="0"
    )
    km_since_service: Mapped[Decimal] = mapped_column(
        Numeric, nullable=False, default=0, server_default="0"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class GearServiceLog(Base):
    __tablename__ = "gear_service_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    gear_id: Mapped[int] = mapped_column(ForeignKey("gear.id"), nullable=False)
    service_type: Mapped[str] = mapped_column(Text, nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DisciplineGearDefault(Base):
    __tablename__ = "discipline_gear_defaults"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    discipline_id: Mapped[int] = mapped_column(ForeignKey("disciplines.id"), primary_key=True)
    gear_id: Mapped[int] = mapped_column(ForeignKey("gear.id"), nullable=False)


class ActivityGearLink(Base):
    __tablename__ = "activity_gear_links"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    gear_id: Mapped[int] = mapped_column(ForeignKey("gear.id"), primary_key=True)
