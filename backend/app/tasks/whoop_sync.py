"""Whoop sync task (§19 cadence: every 6 hours) and per-user driver.

Mirrors the Technogym task: the scheduled run iterates every active whoop
integration, builds a client from stored (encrypted) OAuth tokens, skips
users without credentials with a warning (connecting the real account is a
manual OAuth step — never an automated one), and persists rotated OAuth
tokens if the client refreshed mid-run.
"""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.whoop.client import build_live_client
from app.connectors.whoop.sync import run_user_sync_with_escalation
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json, encrypt_json, EncryptionError
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.whoop_sync")


async def _sync_all_active() -> dict:
    results: dict[str, dict] = {}
    async with sessionmaker() as session:
        integrations = (
            (
                await session.scalars(
                    select(Integration).where(
                        Integration.provider == "whoop",
                        Integration.status == "active",
                    )
                )
            )
            .all()
        )
        for integration in integrations:
            user = await session.get(User, integration.user_id)
            if user is None:
                logger.warning("whoop sync: integration %s has no user", integration.id)
                continue
            credentials = None
            if integration.credentials_encrypted:
                try:
                    credentials = decrypt_json(integration.credentials_encrypted)
                except EncryptionError as exc:
                    logger.error(
                        "whoop sync: credentials for integration %s undecryptable: %s",
                        integration.id, exc,
                    )
            try:
                client = build_live_client(credentials)
            except Exception as exc:
                logger.warning(
                    "whoop sync: skipping user %s (no usable credentials): %s",
                    user.id, exc,
                )
                results[str(user.id)] = {"status": "skipped", "reason": str(exc)}
                continue
            report = await run_user_sync_with_escalation(session, user, integration, client)
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


@celery_app.task(name="whoop.sync_all")
def sync_all_whoop() -> dict:
    return asyncio.run(_sync_all_active())
