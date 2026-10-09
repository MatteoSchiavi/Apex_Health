"""Training plan models (MASTER_SPEC §6.4, Phase 5): training_plans,
planned_sessions.

Mapped in Phase 5 — the agent's write tools (§8.3 propose_training_plan)
create these as DRAFTS (§8.5): confirmation happens in the application, never
inside the agent loop. Tables exist since migration 0001.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, Text, Boolean, Time, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    discipline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)  # ai|manual
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )  # draft|confirmed|active|completed
    source_ai_report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("lab_documents.id", ondelete="SET NULL"))
    source_document_revision: Mapped[int | None] = mapped_column(Integer)
    extraction_id: Mapped[int | None] = mapped_column(ForeignKey("plan_document_drafts.id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[date | None] = mapped_column(Date)
    activated_on: Mapped[date | None] = mapped_column(Date)
    superseded_on: Mapped[date | None] = mapped_column(Date)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class PlannedSession(Base):
    __tablename__ = "planned_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    training_plan_id: Mapped[int] = mapped_column(ForeignKey("training_plans.id"), nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    start_time: Mapped[time | None] = mapped_column(Time)
    target_distance_m: Mapped[Decimal | None] = mapped_column(Numeric)
    intensity_targets: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    date: Mapped[date] = mapped_column(Date, nullable=False)
    discipline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_load: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    technogym_program_id: Mapped[str | None] = mapped_column(Text, nullable=True)
