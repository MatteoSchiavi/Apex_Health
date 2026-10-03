"""Check SQL and interrupted-stream rollback in a unique disposable target.

Reads configuration; never writes to the source database. Requires permission
to create/drop a scratch database on the configured PostgreSQL instance.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.backups import BackupCorruptError
from app.core.config import get_settings
from tools.restore_backup import restore_sql
from tools.restore_drill import create_scratch_database, database_url, drop_scratch_database


async def main():
    settings = get_settings()
    name = f"apex_restore_atomicity_{uuid4().hex}"
    await create_scratch_database(settings, name)
    try:
        target = database_url(settings, name)
        connection = await asyncpg.connect(target)
        try:
            await connection.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            def interrupted():
                yield b"CREATE TABLE public.rollback_probe (id integer);\n"
                raise BackupCorruptError("Simulated missing terminal frame")
            for payload, exception in [
                (b"CREATE TABLE public.rollback_probe (id integer); SELECT 1 / 0;", RuntimeError),
                (interrupted(), BackupCorruptError),
            ]:
                try:
                    await asyncio.to_thread(restore_sql, payload, target, psql_bin=settings.psql_bin)
                except exception:
                    pass
                else:
                    raise AssertionError("Invalid restore unexpectedly succeeded")
                assert await connection.fetchval("SELECT to_regclass('public.rollback_probe')") is None
            print("RESTORE ATOMICITY: PASSED — SQL errors and interrupted archives leave no partial tables")
        finally:
            await connection.close()
    finally:
        await drop_scratch_database(settings, name)


if __name__ == "__main__":
    asyncio.run(main())
