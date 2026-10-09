"""Account context, explicit AI authorization and pre-call budget ledger."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    training_focus: Mapped[list] = mapped_column(JSONB, default=list)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AiConsent(Base):
    __tablename__ = "ai_consents"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    provider_identity: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiBudgetReservation(Base):
    __tablename__ = "ai_budget_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(Text)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric)
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric)
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    actual_tokens: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text, default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
