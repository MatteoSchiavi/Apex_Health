"""Identity & auth models (MASTER_SPEC §6.4 — users, auth_credentials, sessions).

Remaining §6.4 tables are mapped by their owning phases (integrations in
Phase 1, telegram_links in Phase 3, invites with onboarding work); the full
schema itself is created by the Alembic migration regardless.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    weight_goal_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="Europe/Rome", server_default="Europe/Rome"
    )
    # UI preferences (migration 0007) — live on the account so the choice
    # follows the user across browsers/devices. The SPA mirrors them in
    # localStorage for instant first paint before the profile loads.
    locale: Mapped[str] = mapped_column(
        Text, nullable=False, default="en", server_default="en"
    )  # 'en' | 'it'
    theme: Mapped[str] = mapped_column(
        Text, nullable=False, default="dark", server_default="dark"
    )  # 'dark' | 'light'
    units: Mapped[str] = mapped_column(
        Text, nullable=False, default="metric", server_default="metric"
    )  # 'metric' | 'imperial'
    # Device priority law: the MAIN device integration. NULL = first
    # connected wins (legacy). services/device_merge.py owns the rule.
    # NOTE: deliberately NO database-level FK to integrations — see migration
    # 0007 for the topology reasoning (a users→integrations FK reverses the
    # TRUNCATE ... CASCADE topology the test helpers rely on).
    main_integration_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class AuthCredential(Base):
    __tablename__ = "auth_credentials"

    # F-07 audit: ForeignKey added so ORM↔DDL parity holds and a future
    # `alembic revision --autogenerate` does not emit DROP CONSTRAINT.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, default="friend", server_default="friend"
    )
    ai_access_tier: Mapped[str] = mapped_column(
        Text, nullable=False, default="cheap_only", server_default="cheap_only"
    )
    share_segments: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    failed_login_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # F-07 audit: ForeignKey + index added so ORM↔DDL parity holds and the
    # hot-path token-hash lookup is index-backed in autogenerate too.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # F-21 audit: absolute maximum lifetime — sliding expiry alone leaves a
    # stolen session valid forever if used ≥1×/half-TTL. This column caps the
    # total lifetime (default 30d, set at creation).
    absolute_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Invite(Base):
    """Invitation capability token (§6.4 invites, §15 onboarding).

    The code IS the credential: whoever holds a live code may create one
    friend account. `used_by` marks redemption; redemption is atomic
    (row-locked claim in app.auth.invites.redeem_invite).
    """

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # F-07 audit: ForeignKey added for ORM↔DDL parity.
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    used_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
