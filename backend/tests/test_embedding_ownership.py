"""Embedding ownership checks and legacy-row quarantine behavior."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models.ai import AiReport, Embedding
from app.models.journal import JournalEntry
from app.models.user import AuthCredential, User
from app.queries.search import search_context, store_embedding


VECTOR = [0.1] * 1536


async def _owner_id(session) -> int:
    return await session.scalar(
        select(AuthCredential.user_id).where(AuthCredential.role == "owner")
    )


async def _new_user(session, name: str) -> int:
    user = User(name=name)
    session.add(user)
    await session.flush()
    return user.id


async def _journal(session, user_id: int, note: str) -> JournalEntry:
    entry = JournalEntry(user_id=user_id, date=date.today(), free_text_notes=note)
    session.add(entry)
    await session.flush()
    return entry


@pytest.mark.asyncio
async def test_search_requires_matching_embedding_and_source_owner(db_session):
    owner_id = await _owner_id(db_session)
    foreign_id = await _new_user(db_session, "embedding ownership test")
    own_source = await _journal(db_session, owner_id, "owner source")
    foreign_source = await _journal(db_session, foreign_id, "foreign source")

    db_session.add_all(
        [
            Embedding(
                user_id=owner_id,
                source_table="journal_entries",
                source_id=own_source.id,
                embedding=VECTOR,
                content_snippet="visible owner vector",
            ),
            # The embedding claims the foreign user's identity, but the
            # source belongs to owner_id.
            Embedding(
                user_id=foreign_id,
                source_table="journal_entries",
                source_id=own_source.id,
                embedding=VECTOR,
                content_snippet="forged foreign embedding owner",
            ),
            # The embedding claims owner_id, but its source belongs elsewhere.
            Embedding(
                user_id=owner_id,
                source_table="journal_entries",
                source_id=foreign_source.id,
                embedding=VECTOR,
                content_snippet="forged owner embedding",
            ),
            # Unknown legacy ownership is quarantined even if source owner is
            # known.
            Embedding(
                user_id=None,
                source_table="journal_entries",
                source_id=own_source.id,
                embedding=VECTOR,
                content_snippet="unknown legacy owner",
            ),
        ]
    )
    await db_session.flush()

    owner_results = await search_context(db_session, owner_id, VECTOR)
    foreign_results = await search_context(db_session, foreign_id, VECTOR)

    owner_snippets = [result["snippet"] for result in owner_results]
    assert "visible owner vector" in owner_snippets
    assert "forged foreign embedding owner" not in owner_snippets
    assert "forged owner embedding" not in owner_snippets
    assert "unknown legacy owner" not in owner_snippets
    assert foreign_results == []


@pytest.mark.asyncio
async def test_store_embedding_verifies_source_owner_and_existing_owner(db_session):
    owner_id = await _owner_id(db_session)
    foreign_id = await _new_user(db_session, "embedding write test")
    source = await _journal(db_session, owner_id, "owner source")

    with pytest.raises(ValueError, match="does not exist"):
        await store_embedding(
            db_session,
            user_id=owner_id,
            source_table="journal_entries",
            source_id=source.id + 10_000_000,
            vector=VECTOR,
            content_snippet="missing source",
        )

    with pytest.raises(ValueError, match="does not match"):
        await store_embedding(
            db_session,
            user_id=foreign_id,
            source_table="journal_entries",
            source_id=source.id,
            vector=VECTOR,
            content_snippet="foreign caller",
        )

    forged = Embedding(
        user_id=foreign_id,
        source_table="journal_entries",
        source_id=source.id,
        embedding=VECTOR,
        content_snippet="forged preexisting owner",
    )
    db_session.add(forged)
    await db_session.flush()
    with pytest.raises(ValueError, match="Existing embedding owner"):
        await store_embedding(
            db_session,
            user_id=owner_id,
            source_table="journal_entries",
            source_id=source.id,
            vector=VECTOR,
            content_snippet="replace",
        )


@pytest.mark.asyncio
async def test_owned_write_is_idempotent_and_claims_verified_legacy_row(db_session):
    owner_id = await _owner_id(db_session)
    source = await _journal(db_session, owner_id, "owner source")

    await store_embedding(
        db_session,
        user_id=owner_id,
        source_table="journal_entries",
        source_id=source.id,
        vector=VECTOR,
        content_snippet="first",
    )
    first = await db_session.scalar(
        select(Embedding).where(
            Embedding.source_table == "journal_entries",
            Embedding.source_id == source.id,
        )
    )
    first_id = first.id

    await store_embedding(
        db_session,
        user_id=owner_id,
        source_table="journal_entries",
        source_id=source.id,
        vector=VECTOR,
        content_snippet="updated",
    )
    rows = (
        await db_session.scalars(
            select(Embedding).where(
                Embedding.source_table == "journal_entries",
                Embedding.source_id == source.id,
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].id == first_id
    assert rows[0].user_id == owner_id
    assert rows[0].content_snippet == "updated"

    # A verified owner may safely claim a legacy NULL row when re-embedding.
    legacy_source = await _journal(db_session, owner_id, "legacy source")
    legacy = Embedding(
        user_id=None,
        source_table="journal_entries",
        source_id=legacy_source.id,
        embedding=VECTOR,
        content_snippet="legacy",
    )
    db_session.add(legacy)
    await db_session.flush()
    await store_embedding(
        db_session,
        user_id=owner_id,
        source_table="journal_entries",
        source_id=legacy_source.id,
        vector=VECTOR,
        content_snippet="claimed after verification",
    )
    assert legacy.user_id == owner_id


@pytest.mark.asyncio
async def test_report_search_keeps_ai_eligibility_policy(db_session):
    owner_id = await _owner_id(db_session)
    eligible = AiReport(
        user_id=owner_id,
        report_type="daily",
        period_start=date.today(),
        period_end=date.today(),
        content_md="eligible report",
        source_feature_ids=["policy:ai_eligible_v1"],
    )
    restricted = AiReport(
        user_id=owner_id,
        report_type="daily",
        period_start=date.today(),
        period_end=date.today(),
        content_md="restricted report",
        source_feature_ids=["provider:restricted"],
    )
    db_session.add_all([eligible, restricted])
    await db_session.flush()
    db_session.add_all(
        [
            Embedding(
                user_id=owner_id,
                source_table="ai_reports",
                source_id=eligible.id,
                embedding=VECTOR,
                content_snippet="eligible report",
            ),
            Embedding(
                user_id=owner_id,
                source_table="ai_reports",
                source_id=restricted.id,
                embedding=VECTOR,
                content_snippet="restricted report",
            ),
        ]
    )
    await db_session.flush()

    results = await search_context(db_session, owner_id, VECTOR)

    assert "eligible report" in [result["snippet"] for result in results]
    assert "restricted report" not in [result["snippet"] for result in results]
