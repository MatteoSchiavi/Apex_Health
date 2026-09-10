"""Technogym sync task (§19: every 6 hours) and per-user driver.

Mirrors the Garmin task: the scheduled run iterates every active technogym
integration, builds a client from stored (encrypted) OAuth tokens, skips
users without credentials with a warning (connecting the real account is the
owner's manual step, §11/§23 Phase 6 — never an automated one), and persists
rotated OAuth tokens if the client refreshed mid-run.
"""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.technogym.client import build_live_client
from app.connectors.technogym.sync import run_user_sync_with_escalation
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json, encrypt_json, EncryptionError
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.technogym_sync")


async def _sync_all_active() -> dict:
    settings = get_settings()
    results: dict[str, dict] = {}
    async with sessionmaker() as session:
        integrations = (
            (
                await session.scalars(
                    select(Integration).where(
                        Integration.provider == "technogym",
                        Integration.status == "active",
                    )
                )
            )
            .all()
        )
        for integration in integrations:
            user = await session.get(User, integration.user_id)
            if user is None:
                logger.warning(
                    "technogym sync: integration %s has no user", integration.id
                )
                continue
            credentials = None
            if integration.credentials_encrypted:
                try:
                    credentials = decrypt_json(integration.credentials_encrypted)
                except EncryptionError as exc:
                    logger.error(
                        "technogym sync: credentials for integration %s "
                        "undecryptable: %s",
                        integration.id,
                        exc,
                    )
            try:
                client = build_live_client(credentials)
            except Exception as exc:
                logger.warning(
                    "technogym sync: skipping user %s (no usable credentials): %s",
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
                page_size=settings.technogym_activity_page_size,
                page_delay_s=settings.technogym_page_delay_seconds,
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
            # OAuth rotation: persist strictly-newer tokens whenever the
            # client refreshed mid-run (outcome-independent).
            if client.tokens_out is not None:
                integration.credentials_encrypted = encrypt_json(
                    client.tokens_out.as_credentials()
                )
                await session.commit()
    return results


@celery_app.task(name="technogym.sync_all")
def sync_all_technogym() -> dict:
    return asyncio.run(_sync_all_active())
