"""Owner operations contain no health records or authentication secrets."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Feedback(Base):
    __tablename__ = "feedbacks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

class OwnerNotification(Base):
    __tablename__ = "owner_notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    event_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    feedback_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("feedbacks.id"), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
