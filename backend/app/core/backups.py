"""Encrypted database backups (MASTER_SPEC §22.7, §19).

Pipeline per the spec: nightly `pg_dump`, encrypted with `BACKUP_ENCRYPTION_KEY`,
retained 14 daily + 6 monthly archives; offsite copy goes to Backblaze B2
(the upload lives in app/connectors/b2.py — this module owns the local artifact).

Order matters for privacy: the dump is encrypted BEFORE it touches the backup
directory — the only plaintext bytes ever exist in the pg_dump subprocess pipe.
The artifact is Fernet-encrypted gzip of plain-SQL output (--format=plain,
--no-owner --no-privileges) so a restore needs nothing but psql and the key:

    decrypt -> gunzip -> psql   (see backend/tools/restore_backup.py)

A first-of-month backup is classified as the MONTHLY archive (kept up to 6,
independent of the daily pool) — a documented judgment call on "Retain
14 daily + 6 monthly": first-of-month copies are the long-tail archive,
excluded from the daily rotation so month boundaries survive it.
"""

import hashlib
import re
import subprocess
import os
import tempfile
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.postgres_cli import postgres_environment
from app.core.backup_archive import ArchiveCorruptError, CHUNK, read_archive, write_archive


class BackupError(Exception):
    """Raised when a backup cannot be produced (missing key, failed pg_dump)."""


class BackupCorruptError(Exception):
    """Raised when an artifact cannot be decrypted/validated (wrong key, truncation)."""


FILENAME_RE = re.compile(
    r"^hcc-(?P<stamp>\d{8}-\d{6})\.(?P<kind>daily|monthly)\.sql\.gz\.enc$"
)


def _fernet(backup_encryption_key: str) -> Fernet:
    import base64
    import hashlib as _hashlib

    if not backup_encryption_key:
        raise BackupError(
            "BACKUP_ENCRYPTION_KEY is unset — refusing to produce an "
            "unencrypted dump of health data (§22.7)"
        )
    digest = _hashlib.sha256(backup_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def backup_filename(stamp: datetime) -> str:
    """hcc-YYYYMMDD-HHMMSS.{kind}.sql.gz.enc — the first of the month is the monthly archive."""
    kind = "monthly" if stamp.day == 1 else "daily"
    return f"hcc-{stamp.strftime('%Y%m%d-%H%M%S')}.{kind}.sql.gz.enc"


def run_pg_dump(pg_dump_bin: str, database_url: str) -> bytes:
    """Plain-SQL dump straight from the subprocess pipe (never written to disk).

    database_url is the SQLAlchemy asyncpg URL — pg_dump needs a libpq URL,
    so the scheme is rewritten (postgresql+asyncpg:// -> postgresql://).
    """
    return b"".join(iter_pg_dump(pg_dump_bin, database_url))


def iter_pg_dump(pg_dump_bin: str, database_url: str) -> Iterator[bytes]:
    try:
        proc = subprocess.Popen(
            [pg_dump_bin, "--format=plain", "--no-owner", "--no-privileges"],
            env=postgres_environment(database_url),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise BackupError(f"pg_dump binary not found: {pg_dump_bin!r}") from exc
    timer = threading.Timer(600, proc.kill)
    timer.daemon = True
    timer.start()
    try:
        with proc.stdout:
            while chunk := proc.stdout.read(CHUNK):
                yield chunk
        if proc.wait() != 0:
            raise BackupError("pg_dump failed or timed out; check database connectivity and permissions")
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def create_backup(
    *,
    backup_encryption_key: str,
    database_url: str,
    backup_dir: str,
    pg_dump_bin: str = "pg_dump",
    now: datetime | None = None,
) -> dict:
    """pg_dump -> gzip -> Fernet encrypt -> atomic write into backup_dir.

    Returns metadata {path, size, sha256, kind} for logging/audit.
    """
    fernet = _fernet(backup_encryption_key)
    now = now or datetime.now(timezone.utc)

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = backup_filename(now)
    final = target_dir / name
    fd, tmp_name = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=target_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as archive:
            chunks = iter_pg_dump(pg_dump_bin, database_url)
            first = next(chunks, b"")
            if not first.strip():
                chunks.close()
                raise BackupError("pg_dump produced 0 bytes — refusing to archive it")
            from itertools import chain
            try:
                write_archive(chain([first], chunks), archive, fernet)
            finally:
                chunks.close()
            archive.flush()
            os.fsync(archive.fileno())
        # Publish without overwriting another backup from the same second.
        os.link(tmp, final)
        directory_fd = os.open(target_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError:
        raise BackupError("A backup already exists for this timestamp; no archive was overwritten") from None
    finally:
        tmp.unlink(missing_ok=True)

    digest = hashlib.sha256()
    with final.open("rb") as artifact:
        while chunk := artifact.read(CHUNK):
            digest.update(chunk)
    return {
        "path": str(final),
        "size": final.stat().st_size,
        "sha256": digest.hexdigest(),
        "kind": "monthly" if now.day == 1 else "daily",
    }


def read_backup(path: str, backup_encryption_key: str) -> bytes:
    """Decrypt + gunzip an artifact back to plain SQL (restore path / drill)."""
    return b"".join(iter_backup(path, backup_encryption_key))


def iter_backup(path: str, backup_encryption_key: str) -> Iterator[bytes]:
    try:
        with Path(path).open("rb") as artifact:
            yield from read_archive(artifact, _fernet(backup_encryption_key))
    except (OSError, ArchiveCorruptError) as exc:
        raise BackupCorruptError("Cannot read backup: wrong key or corrupt artifact") from exc


def classify(backup_dir: str) -> tuple[list[Path], list[Path]]:
    """Split existing artifacts into (daily, monthly), both newest-first."""
    dailies: list[Path] = []
    monthlies: list[Path] = []
    for p in sorted(Path(backup_dir).glob("hcc-*.sql.gz.enc"), reverse=True):
        m = FILENAME_RE.match(p.name)
        if not m:
            continue
        (monthlies if m.group("kind") == "monthly" else dailies).append(p)
    return dailies, monthlies


def prune_backups(backup_dir: str, retain_daily: int = 14, retain_monthly: int = 6) -> list[str]:
    """Enforce 'Retain 14 daily + 6 monthly archives' (§22.7). Idempotent.

    Returns the deleted paths. Daily pool = non-first-of-month artifacts,
    newest 14 kept; monthly pool = first-of-month artifacts, newest 6 kept.
    """
    if retain_daily < 0 or retain_monthly < 0:
        raise ValueError("Backup retention counts must be nonnegative")
    dailies, monthlies = classify(backup_dir)
    doomed = dailies[retain_daily:] + monthlies[retain_monthly:]
    removed = []
    for p in doomed:
        p.unlink()
        removed.append(p.name)
    return removed
