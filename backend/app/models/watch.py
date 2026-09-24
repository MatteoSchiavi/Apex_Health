"""Watch-domain models (MASTER_SPEC §23 Phase 10).

device_tokens is a §24-style judgment call (documented in the phase notes
and README): the spec's schema (§6.4) has no credential type a Connect IQ
device can present — cookie jars do not exist on the watch, and
Communications.makeWebRequest's practical auth is a header. Tokens are
peppered-hash like sessions (a DB leak must not yield usable credentials),
revocation is soft and timestamped, and each token belongs to exactly one
user — the glance can therefore only ever see that user's data.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="watch")
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # F-19 audit: absolute expiry — device tokens previously had no expiry
    # (revocation was manual only). 365-day default set at mint time; the
    # watch auth path rejects tokens past this column regardless of activity.
    absolute_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
