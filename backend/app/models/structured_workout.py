"""Versioned workout instructions attached to the canonical planned-session identity."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class StructuredWorkoutVersion(Base):
    __tablename__ = 'structured_workout_versions'
    __table_args__ = (UniqueConstraint('planned_session_id','revision'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    planned_session_id: Mapped[int] = mapped_column(ForeignKey('planned_sessions.id',ondelete='CASCADE'),index=True)
    revision: Mapped[int] = mapped_column(Integer)
    structure_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default='now()')


class StructuredWorkoutDraft(Base):
    __tablename__ = 'structured_workout_drafts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    planned_session_id: Mapped[int] = mapped_column(ForeignKey('planned_sessions.id',ondelete='CASCADE'),index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    workout_revision: Mapped[int] = mapped_column(Integer)
    structure_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text,default='draft')
    version_id: Mapped[int | None] = mapped_column(ForeignKey('structured_workout_versions.id',ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default='now()')
