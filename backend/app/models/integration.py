"""Connector & ingestion models (MASTER_SPEC §6.4).

Mapped by their owning phase (Phase 1): integrations, raw_ingest. The full
schema is created by the Alembic migration regardless.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, LargeBinary, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # F-07 audit: ForeignKey + index added for ORM↔DDL parity.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    credentials_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class RawIngest(Base):
    """Raw payload store (§3): every external payload lands here BEFORE
    normalization — an upstream schema change breaks the parser, not history."""

    __tablename__ = "raw_ingest"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # F-07 audit: ForeignKey added for ORM↔DDL parity. Composite index below
    # backs the partial unprocessed-rows index from migration 0008.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload_type: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )


# Composite index for normalize_pending's per-user+source unprocessed scan.
Index(
    "idx_raw_user_source_unproc",
    RawIngest.user_id,
    RawIngest.source,
    RawIngest.id,
    postgresql_where=RawIngest.processed.is_(False),
)
