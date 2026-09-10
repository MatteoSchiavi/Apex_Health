"""Journal reads (§8.2 shared query layer, added in Phase 5) — serves §8.3's
get_journal_entries tool."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import JournalEntry


async def get_journal_entries(
    session: AsyncSession,
    user_id: int,
    start_date: date,
    end_date: date,
    tags: list[str] | None = None,
) -> list[dict]:
    """Entries over [start_date, end_date] (§17 local dates), optionally
    filtered by tag overlap."""
    conditions = [
        JournalEntry.user_id == user_id,
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
    ]
    if tags:
        conditions.append(JournalEntry.tags.overlap(tags))
    rows = (
        await session.scalars(
            select(JournalEntry)
            .where(*conditions)
            .order_by(JournalEntry.date, JournalEntry.id)
        )
    ).all()
    return [
        {
            "id": e.id,
            "date": e.date.isoformat(),
            "mood_score": float(e.mood_score) if e.mood_score is not None else None,
            "energy_score": float(e.energy_score) if e.energy_score is not None else None,
            "soreness_score": float(e.soreness_score) if e.soreness_score is not None else None,
            "stress_subjective": float(e.stress_subjective) if e.stress_subjective is not None else None,
            "notes": e.free_text_notes,
            "tags": e.tags or [],
            "source": e.source,
        }
        for e in rows
    ]
