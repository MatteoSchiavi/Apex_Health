"""Reviewed plan extraction versions and shared planned/recorded session identities."""
from datetime import datetime
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, LargeBinary, Text, DateTime, UniqueConstraint, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class PlanDocumentDraft(Base):
    __tablename__ = "plan_document_drafts"
    __table_args__ = (
        UniqueConstraint("document_id", "version"), UniqueConstraint("template_id", "version"),
        CheckConstraint("(document_id IS NOT NULL AND document_revision IS NOT NULL AND template_id IS NULL AND template_revision IS NULL) OR (document_id IS NULL AND document_revision IS NULL AND template_id IS NOT NULL AND template_revision IS NOT NULL)", name="ck_plan_draft_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("lab_documents.id", ondelete="CASCADE"))
    document_revision: Mapped[int | None] = mapped_column(Integer)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_training_templates.id", ondelete="CASCADE"))
    template_revision: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    structure_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft")
    extraction_method: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class AthleteImportDraft(Base):
    __tablename__ = "athlete_import_drafts"
    __table_args__ = (UniqueConstraint("document_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("lab_documents.id", ondelete="CASCADE"))
    document_revision: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    proposal_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    source_text_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text)
    receipts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class WeeklyTrainingTemplate(Base):
    __tablename__ = "weekly_training_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("lab_documents.id", ondelete="SET NULL"))
    source_document_revision: Mapped[int | None] = mapped_column(Integer)
    import_draft_id: Mapped[int | None] = mapped_column(ForeignKey("athlete_import_drafts.id", ondelete="SET NULL"), unique=True)
    structure_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ActivityPlanLink(Base):
    __tablename__ = "activity_plan_links"
    __table_args__ = (ForeignKeyConstraint(["activity_id", "user_id"], ["activities.id", "activities.user_id"], ondelete="CASCADE"),)
    activity_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    planned_session_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id", ondelete="CASCADE"), unique=True)
    method: Mapped[str] = mapped_column(Text, default="user_confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class SessionCheckin(Base):
    __tablename__ = "athlete_session_checkins"
    __table_args__ = (UniqueConstraint("user_id", "activity_id"), UniqueConstraint("user_id", "planned_session_id"),
        ForeignKeyConstraint(["activity_id", "user_id"], ["activities.id", "activities.user_id"], ondelete="CASCADE"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[int | None] = mapped_column()
    planned_session_id: Mapped[int | None] = mapped_column(ForeignKey("planned_sessions.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text)
    rpe: Mapped[int | None] = mapped_column(Integer)
    pain: Mapped[bool | None] = mapped_column(Boolean)
    felt_unwell: Mapped[bool | None] = mapped_column(Boolean)
    fatigue: Mapped[int | None] = mapped_column(Integer)
    soreness: Mapped[int | None] = mapped_column(Integer)
    workout_quality: Mapped[int | None] = mapped_column(Integer)
    modification_reason: Mapped[str] = mapped_column(Text,default='',server_default='')
    terrain_notes: Mapped[str] = mapped_column(Text,default='',server_default='')
    note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
