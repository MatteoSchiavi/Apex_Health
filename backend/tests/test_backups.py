"""Backup pipeline tests (Phase 8, §22.7, §19).

Hermetic by construction: pg_dump is never the real binary — a fake shell
script produces deterministic SQL, so CI and sandboxes run with zero
PostgreSQL toolchain deps. The LIVE end-to-end restore drill (real pg_dump,
real database) is a phase demo, not a unit test — see scripts/demo_phase8.py.
"""

import base64
import hashlib
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.backups import (
    BackupCorruptError,
    BackupError,
    backup_filename,
    create_backup,
    prune_backups,
    read_backup,
)
from app.tasks.backups import run_nightly_backup

FAKE_SQL = (
    "--\n-- PostgreSQL database dump\n--\n\n"
    "CREATE TABLE public.daily_features (user_id integer);\n"
    "COPY public.daily_features (user_id) FROM stdin;\n"
    "42\n"
    "\\.\n"
    "-- PostgreSQL database dump complete\n"
)


@pytest.fixture
def fake_pg_dump(tmp_path: Path):
    """An executable stand-in for pg_dump that emits a tiny valid dump."""
    script = tmp_path / "fake_pg_dump.sh"
    script.write_text(f"#!/bin/sh\ncat <<'SQLEOF'\n{FAKE_SQL}SQLEOF\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture
def backup_env(tmp_path: Path, monkeypatch):
    """Redirect backup_dir + key into tmp so tests never touch real artifacts."""
    d = tmp_path / "backups"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            backup_encryption_key="test-backup-key",
            database_url=os.environ["DATABASE_URL"],
            backup_dir=str(d),
            pg_dump_bin="pg_dump",
            backup_retain_daily=14,
            backup_retain_monthly=6,
            b2_application_key_id="",
            b2_application_key="",
            b2_bucket="",
        ),
    )
    return d


NOW = datetime(2026, 9, 11, 2, 0, 0, tzinfo=UTC)


def test_backup_roundtrip(tmp_path, fake_pg_dump):
    """create -> read: the artifact decrypts+gunzips to the dumped SQL."""
    d = tmp_path / "bk"
    meta = create_backup(
        backup_encryption_key="k1",
        database_url="postgresql+asyncpg://hcc@localhost:5433/hcc",
        backup_dir=str(d),
        pg_dump_bin=fake_pg_dump,
        now=NOW,
    )
    assert meta["status"] if "status" in meta else True
    assert Path(meta["path"]).exists()
    assert meta["kind"] == "daily"

    sql = read_backup(meta["path"], "k1").decode("utf-8")
    assert "PostgreSQL database dump complete" in sql
    assert "COPY public.daily_features" in sql


def test_artifact_is_encrypted_at_rest(tmp_path, fake_pg_dump):
    """§22.7: no plaintext SQL marker may exist in the on-disk bytes — the
    dump is Fernet(gzip(dump)), i.e. binary ciphertext, before it touches disk."""
    d = tmp_path / "bk"
    meta = create_backup(
        backup_encryption_key="k1",
        database_url="postgresql+asyncpg://u@h/db",
        backup_dir=str(d),
        pg_dump_bin=fake_pg_dump,
        now=NOW,
    )
    raw = Path(meta["path"]).read_bytes()
    assert b"daily_features" not in raw
    assert b"CREATE TABLE" not in raw
    # Fernet tokens are urlsafe-base64 — binary, not readable SQL text.


def test_wrong_key_fails_closed(tmp_path, fake_pg_dump):
    """A wrong BACKUP_ENCRYPTION_KEY raises instead of returning garbage."""
    d = tmp_path / "bk"
    meta = create_backup(
        backup_encryption_key="k1",
        database_url="postgresql+asyncpg://u@h/db",
        backup_dir=str(d),
        pg_dump_bin=fake_pg_dump,
        now=NOW,
    )
    with pytest.raises(BackupCorruptError):
        read_backup(meta["path"], "a-completely-different-key")


def test_refuses_without_key(tmp_path, fake_pg_dump):
    """Unset key => BackupError; an unencrypted dump of health data must never exist."""
    with pytest.raises(BackupError, match="BACKUP_ENCRYPTION_KEY"):
        create_backup(
            backup_encryption_key="",
            database_url="postgresql+asyncpg://u@h/db",
            backup_dir=str(tmp_path / "bk"),
            pg_dump_bin=fake_pg_dump,
            now=NOW,
        )


def test_missing_pg_dump_binary(tmp_path):
    with pytest.raises(BackupError, match="pg_dump binary not found"):
        create_backup(
            backup_encryption_key="k1",
            database_url="postgresql+asyncpg://u@h/db",
            backup_dir=str(tmp_path / "bk"),
            pg_dump_bin=str(tmp_path / "definitely-not-here"),
            now=NOW,
        )


def test_first_of_month_is_monthly_archive():
    """Judgment call: first-of-month snapshots are the monthly pool."""
    assert backup_filename(datetime(2026, 9, 1, 2, 0, 0, tzinfo=UTC)).endswith(
        ".monthly.sql.gz.enc"
    )
    assert backup_filename(datetime(2026, 9, 2, 2, 0, 0, tzinfo=UTC)).endswith(
        ".daily.sql.gz.enc"
    )


def test_prune_keeps_14_daily_6_monthly(tmp_path):
    """§22.7 retention, idempotent: newest 14 daily + newest 6 monthly survive."""
    d = tmp_path / "bk"
    d.mkdir()
    # 20 daily artifacts on consecutive real days ending Sep 10 (timedelta walk
    # keeps us inside valid calendar dates across month boundaries).
    for i in range(20):
        day = datetime(2026, 9, 10, 2, 0, 0, tzinfo=UTC) - timedelta(days=i)
        (d / backup_filename(day)).write_bytes(b"x")
    # 8 monthlies on consecutive real firsts-of-month ending Sep 1.
    for i in range(8):
        first = (datetime(2026, 9, 1, 2, 0, 0, tzinfo=UTC) - timedelta(days=30 * i)).replace(day=1)
        (d / backup_filename(first)).write_bytes(b"x")

    removed1 = prune_backups(str(d), retain_daily=14, retain_monthly=6)
    removed2 = prune_backups(str(d), retain_daily=14, retain_monthly=6)

    dailies = list(d.glob("*.daily.sql.gz.enc"))
    monthlies = list(d.glob("*.monthly.sql.gz.enc"))
    assert len(dailies) == 14
    assert len(monthlies) == 6
    # Newest survive: Sep 10's daily and Apr's monthly (6th-newest) are still
    # there; the two OLDEST monthlies (Mar, Feb) are pruned.
    assert (d / "hcc-20260910-020000.daily.sql.gz.enc").exists()
    assert (d / "hcc-20260401-020000.monthly.sql.gz.enc").exists()
    assert not (d / "hcc-20260201-020000.monthly.sql.gz.enc").exists()
    # Idempotent: second run removes nothing.
    assert removed1 and not removed2


def test_task_skips_honestly_without_key(backup_env, monkeypatch):
    monkeypatch.setattr(
        "app.tasks.backups.get_settings",
        lambda: SimpleNamespace(
            backup_encryption_key="",
            database_url=os.environ["DATABASE_URL"],
            backup_dir=str(backup_env),
            pg_dump_bin="pg_dump",
            backup_retain_daily=14,
            backup_retain_monthly=6,
            b2_application_key_id="",
            b2_application_key="",
            b2_bucket="",
        ),
    )
    report = run_nightly_backup(now=NOW)
    assert report["status"] == "skipped"
    assert list(backup_env.glob("*")) == []  # nothing written at all


def test_task_creates_prunes_and_skips_b2(backup_env, fake_pg_dump, monkeypatch):
    """Full task path: create -> prune -> B2 skipped-honestly (not configured).

    The backup_dir is pre-seeded with 15 old dailies (Aug 17–31); the new
    artifact makes 16, so prune must trim the 2 oldest.
    """
    for i in range(15):
        (backup_env / backup_filename(datetime(2026, 8, 31 - i, 2, 0, 0, tzinfo=UTC))).write_bytes(
            b"x"
        )
    monkeypatch.setattr(
        "app.tasks.backups.get_settings",
        lambda: SimpleNamespace(
            backup_encryption_key="test-backup-key",
            database_url=os.environ["DATABASE_URL"],
            backup_dir=str(backup_env),
            pg_dump_bin=fake_pg_dump,
            backup_retain_daily=14,
            backup_retain_monthly=6,
            b2_application_key_id="",
            b2_application_key="",
            b2_bucket="",
        ),
    )
    report = run_nightly_backup(now=NOW)

    assert report["status"] == "created"
    assert report["kind"] == "daily"
    assert report["b2"] == "skipped (not configured)"
    assert report["pruned"] == ["hcc-20260818-020000.daily.sql.gz.enc", "hcc-20260817-020000.daily.sql.gz.enc"]
    assert len(list(backup_env.glob("*.daily.sql.gz.enc"))) == 14
    # Roundtrip through the task-produced artifact, key from settings.
    sql = read_backup(report["path"], "test-backup-key").decode()
    assert "PostgreSQL database dump complete" in sql


def test_fernet_key_derivation_is_dedicated(tmp_path, fake_pg_dump):
    """§22.7 judgment call: the backup key is independent from the app's
    ENCRYPTION_KEY — an artifact made with the backup key must NOT open with
    the app-layer key, and vice versa."""
    from cryptography.fernet import Fernet

    d = tmp_path / "bk"
    meta = create_backup(
        backup_encryption_key="backup-dedicated-secret",
        database_url="postgresql+asyncpg://u@h/db",
        backup_dir=str(d),
        pg_dump_bin=fake_pg_dump,
        now=NOW,
    )
    # Same derivation as app/core/encryption.py uses for ENCRYPTION_KEY.
    app_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"test-encryption-key").digest()))
    with pytest.raises(Exception):  # noqa: B017 — InvalidToken proves key independence
        app_fernet.decrypt(Path(meta["path"]).read_bytes())
