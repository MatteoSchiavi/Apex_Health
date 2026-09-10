"""Telegram models (MASTER_SPEC §6.4).

Mapped by their owning phase (Phase 3): telegram_links now, telegram_messages
with the voice pipeline. The full schema is created by the Alembic migration
regardless.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TelegramLink(Base):
    """One row per user who has linked a Telegram chat (§6.4).

    Still exactly right under polling mode — this table is about WHO is
    talking to the bot, not about how the bot receives messages (§10.1).
    """

    __tablename__ = "telegram_links"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
