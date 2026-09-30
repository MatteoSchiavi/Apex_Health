"""Training plan models (MASTER_SPEC §6.4, Phase 5): training_plans,
planned_sessions.

Mapped in Phase 5 — the agent's write tools (§8.3 propose_training_plan)
create these as DRAFTS (§8.5): confirmation happens via a Telegram inline
button, never inside the agent loop. Tables exist since migration 0001.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discipline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)  # ai|manual
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )  # draft|confirmed|active|completed
    source_ai_report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class PlannedSession(Base):
    __tablename__ = "planned_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    training_plan_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    discipline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_load: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    technogym_program_id: Mapped[str | None] = mapped_column(Text, nullable=True)
