"""Semantic search over embeddings (§8.3 search_context) + write-time helper.

Corpus this round: journal_entries and ai_reports — the athlete's own words
and generated reports (§6.2 pins the model; the spec leaves the corpus open,
so Phase 5 embeds at natural write time: journal confirm, report generation).

Per-user scoping checks both the embedding's recorded owner and the source
row's owner. Legacy rows with unknown ownership remain quarantined.
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
    user_id: int,
    source_table: str,
    source_id: int,
    vector: list[float],
    content_snippet: str | None,
) -> None:
    """Store one verified, owned embedding per supported source row.

    The source row is authoritative: callers cannot assign a different owner.
    Re-embedding an owned source replaces its vector (idempotent, §17).
    """
    source_models = {
        "journal_entries": JournalEntry,
        "ai_reports": AiReport,
    }
    source_model = source_models.get(source_table)
    if source_model is None:
        raise ValueError(f"Unsupported embedding source table: {source_table}")

    source_owner = await session.scalar(
        select(source_model.user_id).where(source_model.id == source_id)
    )
    if source_owner is None:
        raise ValueError(f"Embedding source does not exist: {source_table}:{source_id}")
    if source_owner != user_id:
        raise ValueError("Embedding owner does not match source owner")

    existing = (
        await session.scalars(
            select(Embedding).where(
                Embedding.source_table == source_table, Embedding.source_id == source_id
            )
        )
    ).first()
    if existing is not None:
        if existing.user_id not in (None, source_owner):
            raise ValueError("Existing embedding owner does not match source owner")
        # A NULL legacy row can be safely claimed only after resolving and
        # checking its current source owner above.
        existing.user_id = source_owner
        existing.embedding = vector
        existing.content_snippet = content_snippet
        return
    session.add(
        Embedding(
            user_id=source_owner,
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
    """pgvector cosine search (§8.3), scoped to both recorded and source
    ownership. Returns [{source_table, source_id, snippet, distance}]."""
    journal_ids = select(JournalEntry.id).where(JournalEntry.user_id == user_id)
    # Legacy reports may contain restricted provider derivatives. They are not
    # eligible merely because an embedding already exists.
    report_ids = select(AiReport.id).where(
        AiReport.user_id == user_id,
        AiReport.source_feature_ids.contains(["policy:ai_eligible_v1"]),
    )

    rows = (
        await session.execute(
            select(
                Embedding.source_table,
                Embedding.source_id,
                Embedding.content_snippet,
                Embedding.embedding.cosine_distance(query_vector).label("distance"),
            )
            .where(
                (Embedding.user_id == user_id)
                & (
                    (
                        (Embedding.source_table == "journal_entries")
                        & Embedding.source_id.in_(journal_ids)
                    )
                    | (
                        (Embedding.source_table == "ai_reports")
                        & Embedding.source_id.in_(report_ids)
                    )
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
        user_id=user_id,
        source_table="journal_entries",
        source_id=entry_id,
        vector=result.vectors[0],
        content_snippet=_snippet(text),
    )
    return result
