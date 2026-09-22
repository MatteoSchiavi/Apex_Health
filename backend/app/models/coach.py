"""Coach capability models: calendar events, AI context docs, feedback.

Owner feature batch (2026-09): the events calendar is the spine of the
context-aware gym engine — the advisor tapers sessions toward upcoming
events, and the agent harness injects both events and the user's context
documents (profile, goals, injuries, ...) into its snapshots while keeping
token cost bounded.
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserEvent(Base):
    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_user_events_user_starts", "user_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # race | run | ride | ski | enduro | sailing | competition | trip |
    # training_camp | gym | other
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 1 = high (taper around it), 2 = normal, 3 = low
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default="2"
    )
    taper_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=3, server_default="3"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class UserContextDoc(Base):
    """One self-contained markdown document per (user, doc_kind).

    The AI harness reads these as compact context (token budget applies at
    assembly time, not storage time). `updated_by` records whether the last
    write was the user or the agent."""

    __tablename__ = "user_context_docs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # profile | goals | injuries | equipment | preferences | season_plan
    doc_kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(
        Text, nullable=False, default="user", server_default="user"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class SessionFeedback(Base):
    """Post-session feedback (any sport) that steers the adaptive gym engine.

    `soreness` is a JSONB list of body areas, e.g. ["knees","lower_back"] —
    the advisor maps areas to movement patterns to go easy on."""

    __tablename__ = "session_feedback"
    __table_args__ = (
        Index("ix_session_feedback_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    activity_kind: Mapped[str] = mapped_column(Text, nullable=False)
    rpe: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    soreness: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    injury_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
