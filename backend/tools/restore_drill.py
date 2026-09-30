"""The restore drill (MASTER_SPEC §22.7, §23 Phase 8 AC).

"Backups: ... Test an actual restore once — an untested backup is a hope,
not a backup." This tool IS the test, rerunnable any time (the owner should
run it on the real host too):

  1. Seed the source database with a marker dataset through REAL app code:
     the owner account, an activity, a sleep_sessions row (hypertable —
     exercises the TimescaleDB catalog round-trip), a journal entry, and a
     lab panel whose notes are Fernet-encrypted at the application layer
     (§17) — encrypted payloads must survive byte-for-byte.
  2. Snapshot row counts of every public table + alembic_version.
  3. Produce the nightly backup through the REAL pipeline (create_backup:
     pg_dump -> gzip -> Fernet(BACKUP_ENCRYPTION_KEY) -> artifact).
  4. Restore the artifact into a scratch database (hcc_restore_drill) via
     tools/restore_backup (decrypt -> gunzip -> psql, ON_ERROR_STOP, with
     TimescaleDB's pre/post restore wrapper).
  5. Snapshot the target, compare table-by-table, verify the lab notes
     decrypt to the original plaintext with the APP key.
  6. Drop the scratch database; the artifact stays as evidence.

Usage (from backend/):
    BACKUP_ENCRYPTION_KEY=<key> uv run python tools/restore_drill.py

Exit code 0 = drill PASSED.
"""

import asyncio
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import asyncpg
from sqlalchemy import func, select, text

# `uv run python tools/restore_drill.py` puts tools/ (not backend/) on sys.path;
# app.* imports need the backend dir explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.service import ensure_owner  # noqa: E402
from app.core.backups import create_backup  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import sessionmaker  # noqa: E402
from app.medical.labs import decrypt_notes, encrypt_notes  # noqa: E402
from app.models.activity import Activity  # noqa: E402
from app.models.journal import JournalEntry  # noqa: E402
from app.models.medical import LabPanel  # noqa: E402
from app.models.user import AuthCredential, User  # noqa: E402
from app.models.wellness import SleepSession  # noqa: E402
from tools.restore_backup import decrypt_to_sql, restore_sql  # noqa: E402

DRILL_DB = "hcc_restore_drill"
MARKER_NOTES = "drill-marker: restore must round-trip this encrypted note (§17)"
BANNER = "=" * 72


def section(title: str) -> None:
    print(f"\n{BANNER}\n{title}\n{BANNER}")


async def snapshot(dsn: str) -> dict[str, int]:
    """Row counts for every public table (the DB is small — count(*) is fine)."""
    conn = await asyncpg.connect(dsn)
    try:
        out: dict[str, int] = {}
        for t in await public_tables(conn):
            out[t] = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()
    out["alembic_version"] = int(version)
    return out


async def public_tables(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    return [r["table_name"] for r in rows]


async def seed_marker_data() -> tuple[int, str]:
    """Ensure owner + marker rows exist through the ORM. Returns (user_id, notes)."""
    async with sessionmaker() as session:
        await ensure_owner(session)
        cred = await session.scalar(
            select(AuthCredential).where(AuthCredential.role == "owner")
        )
        user = await session.get(User, cred.user_id)
        user_id = user.id

        # Idempotent marker: one row per (user, marker source) — re-running the
        # drill never double-seeds (§17 spirit).
        exists = await session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(JournalEntry.user_id == user_id, JournalEntry.tags == ["drill"])
        )
        if not exists:
            running_id = await session.scalar(
                select(text("id")).select_from(text("disciplines")).where(text("name = 'running'"))
            )
            session.add(
                Activity(
                    user_id=user_id,
                    discipline_id=running_id,
                    start_time=datetime(2026, 9, 10, 7, 30, tzinfo=UTC),
                    start_tz_offset_minutes=120,
                    local_date=date(2026, 9, 10),
                    duration_s=3600,
                    distance_m=10000.0,
                    avg_hr=150,
                )
            )
            # sleep_sessions is a TimescaleDB hypertable — its chunk catalog
            # rows are the hard part of any restore; the drill deliberately
            # includes one.
            session.add(
                SleepSession(
                    user_id=user_id,
                    local_date=date(2026, 9, 10),
                    start_time=datetime(2026, 9, 9, 23, 10, tzinfo=UTC),
                    end_time=datetime(2026, 9, 10, 6, 40, tzinfo=UTC),
                    total_sleep_s=26400,
                    sleep_score=88.0,
                )
            )
            session.add(
                JournalEntry(
                    user_id=user_id,
                    date=date(2026, 9, 10),
                    mood_score=7.5,
                    energy_score=8.0,
                    free_text_notes="restore drill marker entry",
                    tags=["drill"],  # marker is the tag; source must satisfy the CHECK
                    source="web",
                )
            )
            session.add(
                LabPanel(
                    user_id=user_id,
                    date=date(2026, 9, 1),
                    panel_type="blood_donation",
                    ferritin_ng_ml=42.0,
                    notes_ciphertext=encrypt_notes(MARKER_NOTES),
                    source="restore_drill",
                )
            )
            await session.commit()
    return user_id, MARKER_NOTES


async def reset_scratch_database(settings) -> None:
    """DROP + CREATE the scratch DB, pre-create the extensions the dump expects."""
    base = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    admin_dsn = base.rsplit("/", 1)[0] + "/postgres"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{DRILL_DB}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{DRILL_DB}"')
    finally:
        await admin.close()

    scratch_dsn = base.rsplit("/", 1)[0] + f"/{DRILL_DB}"
    conn = await asyncpg.connect(scratch_dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()
    return scratch_dsn


async def drop_scratch_database(settings) -> None:
    base = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    admin_dsn = base.rsplit("/", 1)[0] + "/postgres"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{DRILL_DB}" WITH (FORCE)')
    finally:
        await admin.close()


async def main() -> int:
    settings = get_settings()
    if not settings.backup_encryption_key:
        print(
            "drill aborted: BACKUP_ENCRYPTION_KEY is unset — set it in the "
            "environment (the drill restores with the same key it backed up with)"
        )
        return 2

    libpq_base = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    section("1. Seed marker data (owner, activity, hypertable row, journal, encrypted lab)")
    user_id, marker_notes = await seed_marker_data()
    print(f"owner user_id={user_id}; marker rows ensured (idempotent)")

    section("2. Snapshot the SOURCE database")
    src = await snapshot(libpq_base)
    for t in sorted(src):
        print(f"  {t:32} {src[t]:>8}")

    section("3. Produce the nightly backup (REAL pipeline: pg_dump->gzip->Fernet)")
    meta = create_backup(
        backup_encryption_key=settings.backup_encryption_key,
        database_url=settings.database_url,
        backup_dir=settings.backup_dir,
        pg_dump_bin=settings.pg_dump_bin,
    )
    print(f"  artifact : {meta['path']}")
    print(f"  size     : {meta['size']} bytes")
    print(f"  sha256   : {meta['sha256']}")
    print(f"  kind     : {meta['kind']}")

    section("4. Restore into a scratch database (decrypt -> gunzip -> psql)")
    scratch_dsn = await reset_scratch_database(settings)
    sql = decrypt_to_sql(meta["path"], settings.backup_encryption_key)
    print(f"  decrypted dump: {len(sql)} bytes of SQL")
    await asyncio.to_thread(
        restore_sql, sql, scratch_dsn, psql_bin=settings.psql_bin, timescaledb=True
    )  # restore_sql is sync-subprocess; thread keeps the loop responsive
    print(f"  restored into {DRILL_DB} (TimescaleDB pre/post wrapper applied)")

    section("5. Compare TARGET vs SOURCE, table by table")
    dst = await snapshot(scratch_dsn)
    mismatches = [(t, src.get(t), dst.get(t)) for t in sorted(set(src) | set(dst)) if src.get(t) != dst.get(t)]
    if mismatches:
        print("  MISMATCHES:")
        for t, a, b in mismatches:
            print(f"    {t:32} source={a} target={b}")
    else:
        print(f"  all {len(src)} tables match (incl. alembic_version = {src['alembic_version']})")

    # §17: the encrypted-at-rest payload must decrypt with the APP key in the
    # restored database — the backup key never touches row ciphertext.
    conn = await asyncpg.connect(scratch_dsn)
    try:
        restored_ct = await conn.fetchval(
            "SELECT notes FROM lab_panels WHERE source = 'restore_drill' LIMIT 1"
        )
    finally:
        await conn.close()

    class _P:  # minimal stand-in for decrypt_notes' ORM attribute access
        notes_ciphertext = restored_ct

    restored_notes = decrypt_notes(_P())
    crypto_ok = restored_notes == marker_notes
    print(f"  encrypted lab notes round-trip (§17): {'OK' if crypto_ok else 'FAILED'}")

    section("6. Cleanup + verdict")
    await drop_scratch_database(settings)
    print(f"  scratch database {DRILL_DB} dropped; artifact kept as evidence")

    ok = not mismatches and crypto_ok
    print(f"\n  RESTORE DRILL: {'PASSED' if ok else 'FAILED'}")
    print("  DISCLAIMER: this ran on the direct (non-Docker) dev stack; Docker")
    print("  parity (compose bring-up) remains unproven in this environment.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
