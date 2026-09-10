"""Garmin sync task (§19: every 6 hours) and per-user driver (§21 escalation).

The scheduled run iterates every active garmin integration. Clients are built
from stored (encrypted) credentials; users whose credentials are absent are
skipped with a warning — connecting a real account is the owner's manual step
(§23 Phase 1 acceptance), never an automated one.
"""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.garmin.client import GarminAuthError, build_live_client
from app.connectors.garmin.sync import run_user_sync_with_escalation
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json, EncryptionError
from app.models.integration import Integration
from app.models.user import AuthCredential, User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.garmin_sync")


async def _sync_all_active() -> dict:
    settings = get_settings()
    results: dict[str, dict] = {}
    async with sessionmaker() as session:
        integrations = (
            (
                await session.scalars(
                    select(Integration).where(
                        Integration.provider == "garmin",
                        Integration.status == "active",
                    )
                )
            )
            .all()
        )
        for integration in integrations:
            user = await session.get(User, integration.user_id)
            if user is None:
                logger.warning("garmin sync: integration %s has no user", integration.id)
                continue
            credentials = None
            if integration.credentials_encrypted:
                try:
                    credentials = decrypt_json(integration.credentials_encrypted)
                except EncryptionError as exc:
                    logger.error(
                        "garmin sync: credentials for integration %s undecryptable: %s",
                        integration.id,
                        exc,
                    )
            try:
                client = build_live_client(credentials)
            except GarminAuthError as exc:
                logger.warning(
                    "garmin sync: skipping user %s (no usable credentials): %s",
                    user.id,
                    exc,
                )
                results[str(user.id)] = {"status": "skipped", "reason": str(exc)}
                continue
            report = await run_user_sync_with_escalation(
                session,
                user,
                integration,
                client,
                page_size=settings.garmin_activity_page_size,
                page_delay_s=settings.garmin_page_delay_seconds,
                empty_gap_days=settings.garmin_backfill_empty_gap_days,
            )
            results[str(user.id)] = (
                {
                    "status": "ok",
                    "mode": report.mode,
                    "raw_stored": report.raw_rows_stored,
                    "unprocessed": report.raw_rows_unprocessed,
                }
                if report is not None
                else {"status": "failed"}
            )
    return results


@celery_app.task(name="garmin.sync_all")
def sync_all_garmin() -> dict:
    return asyncio.run(_sync_all_active())
