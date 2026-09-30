"""Journal model (MASTER_SPEC §6.4 — journal_entries).

Mapped by its owning consumer: written by the Telegram voice pipeline on
draft confirmation (§10.2). source CHECK: ('web','telegram_voice','telegram_text').
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # §17: user's local date
    date: Mapped[date] = mapped_column(Date, nullable=False)
    mood_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    energy_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    motivation_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    soreness_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    stress_subjective: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    sleep_quality_subjective: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    free_text_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="telegram_text", server_default="telegram_text"
    )
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
