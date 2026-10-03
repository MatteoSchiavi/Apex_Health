"""Verify an encrypted database backup in a uniquely named scratch database.

The source is read-only: this tool never seeds health records or deletes an
existing database. Pause writers while running it so source/target counts and
ciphertext comparisons describe the same state. The scratch database is
removed in a finally block; the encrypted archive remains as evidence.

Usage (from backend/):
    BACKUP_ENCRYPTION_KEY=<key> uv run python tools/restore_drill.py
"""

import asyncio
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.backups import create_backup, iter_backup
from app.core.config import get_settings
from tools.restore_backup import restore_sql


def database_url(settings, database=None):
    url = make_url(settings.database_url).set(drivername="postgresql")
    if database is not None:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


async def snapshot(dsn: str) -> dict:
    """Stream sorted rows through a checksum; no clinical data is printed."""
    conn = await asyncpg.connect(dsn)
    try:
        result = {}
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
            )
            for row in tables:
                table = row["table_name"].replace('"', '""')
                digest = hashlib.sha256()
                count = 0
                async for record in conn.cursor(
                    f'SELECT row_to_json(t)::text AS value FROM "{table}" t ORDER BY value'
                ):
                    data = record["value"].encode()
                    digest.update(len(data).to_bytes(8, "big"))
                    digest.update(data)
                    count += 1
                result[row["table_name"]] = (count, digest.hexdigest())
        return result
    finally:
        await conn.close()


async def create_scratch_database(settings, name):
    admin = await asyncpg.connect(database_url(settings, "postgres"))
    try:
        # CREATE without DROP: an unlikely name collision fails safely.
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()


async def drop_scratch_database(settings, name):
    admin = await asyncpg.connect(database_url(settings, "postgres"))
    try:
        await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        await admin.close()


async def main() -> int:
    settings = get_settings()
    if not settings.backup_encryption_key:
        print("drill aborted: BACKUP_ENCRYPTION_KEY is unset")
        return 2
    source = database_url(settings)
    before = await snapshot(source)
    meta = await asyncio.to_thread(
        create_backup, backup_encryption_key=settings.backup_encryption_key,
        database_url=settings.database_url, backup_dir=settings.backup_dir,
        pg_dump_bin=settings.pg_dump_bin,
    )
    name = f"apex_restore_{uuid4().hex}"
    await create_scratch_database(settings, name)
    try:
        target = database_url(settings, name)
        conn = await asyncpg.connect(target)
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            await conn.close()
        sql = iter_backup(meta["path"], settings.backup_encryption_key)
        await asyncio.to_thread(restore_sql, sql, target, psql_bin=settings.psql_bin)
        restored = await snapshot(target)
        after = await snapshot(source)
        if before != after:
            print("RESTORE DRILL: INCONCLUSIVE — source changed during the drill; pause writers and repeat")
            return 1
        differences = [table for table in sorted(set(before) | set(restored))
                       if before.get(table) != restored.get(table)]
        if differences:
            print("RESTORE DRILL: FAILED — mismatching tables: " + ", ".join(differences))
            return 1
        print(f"RESTORE DRILL: PASSED — counts and row checksums match for {len(before)} tables, including ciphertext")
        print(f"encrypted artifact: {meta['path']}; sha256: {meta['sha256']}")
        return 0
    finally:
        await drop_scratch_database(settings, name)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
