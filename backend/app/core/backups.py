"""Encrypted database backups (MASTER_SPEC §22.7, §19).

Pipeline per the spec: nightly `pg_dump`, encrypted with `BACKUP_ENCRYPTION_KEY`,
retained 14 daily + 6 monthly archives; offsite copy goes to Backblaze B2
(the upload lives in app/integrations/b2.py — this module owns the local artifact).

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

import gzip
import hashlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.encryption import EncryptionError


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
    libpq_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        proc = subprocess.run(
            [pg_dump_bin, "--format=plain", "--no-owner", "--no-privileges", libpq_url],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise BackupError(f"pg_dump binary not found: {pg_dump_bin!r}") from exc
    except subprocess.CalledProcessError as exc:
        # stderr may embed the connection string — keep the message, drop nothing
        # the operator needs, but never log credentials: strip any URL in it.
        tail = exc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        tail = [line.replace(libpq_url, "<db-url-redacted>") for line in tail]
        raise BackupError(f"pg_dump failed: {' | '.join(tail)}") from exc
    return proc.stdout


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

    plaintext_dump = run_pg_dump(pg_dump_bin, database_url)
    if not plaintext_dump.strip():
        raise BackupError("pg_dump produced 0 bytes — refusing to archive it")

    compressed = gzip.compress(plaintext_dump, compresslevel=6)
    ciphertext = fernet.encrypt(compressed)

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = backup_filename(now)
    final = target_dir / name
    tmp = target_dir / f".{name}.tmp"
    tmp.write_bytes(ciphertext)
    tmp.replace(final)  # atomic — a crash mid-write never leaves a partial archive

    return {
        "path": str(final),
        "size": len(ciphertext),
        "sha256": hashlib.sha256(ciphertext).hexdigest(),
        "kind": "monthly" if now.day == 1 else "daily",
    }


def read_backup(path: str, backup_encryption_key: str) -> bytes:
    """Decrypt + gunzip an artifact back to plain SQL (restore path / drill)."""
    try:
        ciphertext = Path(path).read_bytes()
    except OSError as exc:
        raise BackupCorruptError(f"cannot read backup: {path}") from exc
    try:
        compressed = _fernet(backup_encryption_key).decrypt(ciphertext)
    except (InvalidToken, EncryptionError) as exc:
        raise BackupCorruptError(
            "decryption failed: wrong BACKUP_ENCRYPTION_KEY or corrupt artifact"
        ) from exc
    return gzip.decompress(compressed)


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
    dailies, monthlies = classify(backup_dir)
    doomed = dailies[retain_daily:] + monthlies[retain_monthly:]
    removed = []
    for p in doomed:
        p.unlink()
        removed.append(p.name)
    return removed
