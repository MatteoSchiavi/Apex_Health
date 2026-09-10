"""Telegram models (MASTER_SPEC §6.4).

Mapped by their owning phase (Phase 3): telegram_links (link flow) and
telegram_messages (voice pipeline). The full schema is created by the
Alembic migration regardless.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
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


class TelegramMessage(Base):
    """Voice-note draft lifecycle (§10.2): pending -> confirmed | rejected.

    The draft is NEVER auto-committed — journal_entries rows are written only
    on the explicit ✅ Save callback; ✏️ Edit rejects this row and a new
    pending draft is created from the corrections.
    """

    __tablename__ = "telegram_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    voice_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    linked_journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
