"""Nightly database backup task (MASTER_SPEC §19: nightly 02:00, §22.7).

Wire-up: create_backup (pg_dump -> gzip -> encrypt -> file), then prune to
14 daily + 6 monthly, then push the artifact to B2 when credentials exist
(§22.7 offsite). Missing BACKUP_ENCRYPTION_KEY is an HONEST skip — logged,
never silently turning into an unencrypted dump.

Scheduling: beat fires at 02:00 UTC per the §19 table. The backup is
database-wide (no per-user local-time semantics like the feature engine),
so the single UTC schedule matches the spec row without the hourly-dispatch
pattern the user-local jobs need.
"""

import logging

from app.core.backups import BackupError, create_backup, prune_backups
from app.core.config import get_settings

logger = logging.getLogger("tasks.backups")


def run_nightly_backup(now=None) -> dict:
    """Shared implementation, testable without Celery. Returns task report."""
    settings = get_settings()

    if not settings.backup_encryption_key:
        logger.warning("backup skipped: BACKUP_ENCRYPTION_KEY unset (§22.7)")
        return {"status": "skipped", "reason": "BACKUP_ENCRYPTION_KEY unset"}

    try:
        meta = create_backup(
            backup_encryption_key=settings.backup_encryption_key,
            database_url=settings.database_url,
            backup_dir=settings.backup_dir,
            pg_dump_bin=settings.pg_dump_bin,
            now=now,
        )
    except BackupError as exc:
        # §21: operator-facing logs are distinct from user-facing alerts; a
        # failed backup is a logged operational error, not a user alert.
        logger.error("backup failed: %s", exc)
        return {"status": "error", "error": str(exc)}

    removed = prune_backups(
        settings.backup_dir,
        retain_daily=settings.backup_retain_daily,
        retain_monthly=settings.backup_retain_monthly,
    )
    logger.info(
        "backup created: %s (%d bytes, %s, pruned %d)",
        meta["path"],
        meta["size"],
        meta["kind"],
        len(removed),
    )
    report = {"status": "created", **meta, "pruned": removed}

    # Offsite copy (§22.7) — skip honestly when B2 is not configured.
    if settings.b2_application_key_id and settings.b2_application_key and settings.b2_bucket:
        from app.connectors.b2 import B2Uploader

        try:
            B2Uploader().upload(meta["path"])
            report["b2"] = "uploaded"
        except Exception as exc:  # noqa: BLE001 — offsite failure must not fail the local backup
            logger.error("backup b2 upload failed: %s", exc)
            report["b2"] = f"failed: {exc}"
    else:
        report["b2"] = "skipped (not configured)"
    return report


from app.tasks.celery_app import celery_app  # noqa: E402


@celery_app.task(name="backups.nightly")
def nightly_backup_task(now_iso: str | None = None) -> dict:
    """§19: nightly, 02:00 UTC. now_iso is a test seam (None -> real clock)."""
    from datetime import datetime, timezone

    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    return run_nightly_backup(now=now)
