"""Semantic search over embeddings (§8.3 search_context) + write-time helper.

Corpus this round: journal_entries and ai_reports — the athlete's own words
and generated reports (§6.2 pins the model; the spec leaves the corpus open,
so Phase 5 embeds at natural write time: journal confirm, report generation).

Per-user scoping: §6.4's embeddings table carries no user_id, so the search
joins to the source row and filters on ITS user_id — owner and (future,
§15) friends never see each other's vectors.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiReport, Embedding
from app.models.journal import JournalEntry


def _snippet(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text[:limit]


async def store_embedding(
    session: AsyncSession,
    *,
    source_table: str,
    source_id: int,
    vector: list[float],
    content_snippet: str | None,
) -> None:
    """One embedding row per source row — upsert semantics: re-embedding a
    source replaces its vector (idempotent, §17)."""
    existing = (
        await session.scalars(
            select(Embedding).where(
                Embedding.source_table == source_table, Embedding.source_id == source_id
            )
        )
    ).first()
    if existing is not None:
        existing.embedding = vector
        existing.content_snippet = content_snippet
        return
    session.add(
        Embedding(
            source_table=source_table,
            source_id=source_id,
            embedding=vector,
            content_snippet=content_snippet,
        )
    )


async def search_context(
    session: AsyncSession,
    user_id: int,
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """pgvector cosine search (§8.3), scoped to the caller via the source
    rows. Returns [{source_table, source_id, snippet, distance}]."""
    journal_ids = select(JournalEntry.id).where(JournalEntry.user_id == user_id)
    report_ids = select(AiReport.id).where(AiReport.user_id == user_id)

    rows = (
        await session.execute(
            select(
                Embedding.source_table,
                Embedding.source_id,
                Embedding.content_snippet,
                Embedding.embedding.cosine_distance(query_vector).label("distance"),
            )
            .where(
                (
                    (Embedding.source_table == "journal_entries")
                    & Embedding.source_id.in_(journal_ids)
                )
                | (
                    (Embedding.source_table == "ai_reports")
                    & Embedding.source_id.in_(report_ids)
                )
            )
            .order_by("distance")
            .limit(top_k)
        )
    ).all()
    return [
        {
            "source_table": source_table,
            "source_id": source_id,
            "snippet": snippet,
            "distance": round(float(distance), 4),
        }
        for source_table, source_id, snippet, distance in rows
    ]


async def embed_journal_entry(
    session: AsyncSession,
    embedding_client,
    user_id: int,
    entry_id: int,
    text: str,
):
    """Write-time embedding for one journal entry: store the vector and
    return the EmbeddingResult (the caller writes the token_usage row —
    §8.6 — so the model name rides along)."""
    result = await embedding_client.embed([text])
    await store_embedding(
        session,
        source_table="journal_entries",
        source_id=entry_id,
        vector=result.vectors[0],
        content_snippet=_snippet(text),
    )
    return result
