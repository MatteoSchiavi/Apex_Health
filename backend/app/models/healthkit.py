"""Scoped pairing, immutable HealthKit UUIDs/tombstones and replay receipts."""
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID as PythonUUID
from app.models.base import Base


class HealthKitPairing(Base):
    __tablename__ = 'healthkit_pairings'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    code_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HealthKitSample(Base):
    __tablename__ = 'healthkit_samples'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    uuid: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HealthKitBatch(Base):
    __tablename__ = 'healthkit_batches'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey('device_tokens.id', ondelete='CASCADE'), index=True)
    batch_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True))
    content_hash: Mapped[str] = mapped_column(Text)
    checkpoint: Mapped[int] = mapped_column(Integer)
    receipt: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default='now()')
    __table_args__ = (UniqueConstraint('device_id', 'batch_id'),)
