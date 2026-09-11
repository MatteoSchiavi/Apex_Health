"""Restore an encrypted backup artifact into a target database (§22.7).

The other half of the backup pipeline — "an untested backup is a hope, not
a backup" (§22.7): this tool is what the restore drill actually runs.

Pipeline: read artifact -> Fernet-decrypt (BACKUP_ENCRYPTION_KEY) -> gunzip
-> psql into the TARGET DSN with ON_ERROR_STOP (fail loudly, never half-
restore quietly). The artifact is a plain-SQL pg_dump, so the restore path
needs nothing but psql and the key — no pg_restore catalogs.

TimescaleDB note: hypertable DDL in the dump is plain SQL over the
timescaledb extension. Per TimescaleDB's documented restore procedure, the
tool wraps the psql run in timescaledb_pre_restore()/timescaledb_post_restore()
when --timescaledb is passed — the extension must already exist in the
target (the drill pre-creates it; our own dumps include CREATE EXTENSION
statements too, but pre-creating is the robust path).

Usage:
    python tools/restore_backup.py <artifact.sql.gz.enc> \
        --target-dsn postgresql://hcc@localhost:5433/hcc_restore_drill \
        [--timescaledb] [--backup-key <key>]

BACKUP_ENCRYPTION_KEY comes from the environment unless --backup-key is
given; the key is never echoed, never logged.
"""

import argparse
import gzip
import os
import subprocess
import sys
from pathlib import Path

from app.core.backups import BackupCorruptError, _fernet
from app.core.config import get_settings


def decrypt_to_sql(artifact_path: str, backup_key: str) -> bytes:
    """Fernet-decrypt + gunzip the artifact back to plain SQL text."""
    ciphertext = Path(artifact_path).read_bytes()
    try:
        compressed = _fernet(backup_key).decrypt(ciphertext)
    except Exception as exc:  # noqa: BLE001 — InvalidToken; message stays honest
        raise BackupCorruptError(
            f"decryption failed for {artifact_path}: wrong key or corrupt artifact"
        ) from exc
    return gzip.decompress(compressed)


def restore_sql(sql: bytes, target_dsn: str, *, psql_bin: str = "psql", timescaledb: bool = True) -> None:
    """Pipe plain SQL into psql against target_dsn, failing on the first error.

    timescaledb=True follows TimescaleDB's documented plain-SQL restore
    procedure: `SELECT timescaledb_pre_restore();` -> dump -> `SELECT
    timescaledb_post_restore();`, each as its OWN psql session (the wrapper
    calls must not share a transaction with the restore body). The SQL is
    passed on stdin — never a temp file with plaintext health data on disk.
    """
    def _psql(payload: bytes) -> None:
        proc = subprocess.run(
            [psql_bin, target_dsn, "--set", "ON_ERROR_STOP=1", "--quiet"],
            input=payload,
            capture_output=True,
            timeout=1800,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "replace").strip()
            # The DSN may embed credentials — redact before printing anything.
            stderr = stderr.replace(target_dsn, "<target-dsn-redacted>")
            raise RuntimeError(f"restore failed (psql exit {proc.returncode}):\n{stderr}")

    if timescaledb:
        _psql(b"SELECT timescaledb_pre_restore();")
    _psql(sql)
    if timescaledb:
        _psql(b"SELECT timescaledb_post_restore();")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="path to the encrypted artifact (*.sql.gz.enc)")
    parser.add_argument("--target-dsn", required=True, help="libpq DSN of the TARGET database")
    parser.add_argument(
        "--backup-key",
        default=None,
        help="override; default reads BACKUP_ENCRYPTION_KEY from the environment",
    )
    parser.add_argument(
        "--no-timescaledb",
        action="store_true",
        help="skip the timescaledb pre/post restore wrapper (non-timeseries targets)",
    )
    parser.add_argument("--psql-bin", default=None, help="psql binary path (default: settings)")
    args = parser.parse_args(argv)

    backup_key = args.backup_key or os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    if not backup_key:
        print("restore aborted: no BACKUP_ENCRYPTION_KEY (env) and no --backup-key", file=sys.stderr)
        return 2

    settings = get_settings()
    psql_bin = args.psql_bin or settings.psql_bin

    try:
        sql = decrypt_to_sql(args.artifact, backup_key)
    except BackupCorruptError as exc:
        print(f"restore aborted: {exc}", file=sys.stderr)
        return 2

    restore_sql(
        sql,
        args.target_dsn,
        psql_bin=psql_bin,
        timescaledb=not args.no_timescaledb,
    )
    print(f"restore complete: {args.artifact} -> {args.target_dsn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
