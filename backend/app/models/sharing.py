"""Revocable read capabilities contain a frozen encrypted approved snapshot."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AthleteShare(Base):
    __tablename__ = 'athlete_shares'
    __table_args__ = (CheckConstraint("expires_at > created_at AND expires_at <= created_at + interval '30 days'", name='ck_share_expiry'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    selection: Mapped[dict] = mapped_column(JSONB)
    dependencies: Mapped[dict] = mapped_column(JSONB)
    snapshot_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default='now()')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
