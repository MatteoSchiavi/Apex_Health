"""Strava sync task (§19 cadence: every 6 hours, rate-limit-aware pacing)."""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.strava.client import build_live_client
from app.connectors.strava.sync import run_user_sync_with_escalation
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json, encrypt_json, EncryptionError
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.strava_sync")


async def _sync_all_active() -> dict:
    settings = get_settings()
    results: dict[str, dict] = {}
    async with sessionmaker() as session:
        integrations = (
            (
                await session.scalars(
                    select(Integration).where(
                        Integration.provider == "strava",
                        Integration.status == "active",
                    )
                )
            )
            .all()
        )
        for integration in integrations:
            user = await session.get(User, integration.user_id)
            if user is None:
                logger.warning("strava sync: integration %s has no user", integration.id)
                continue
            credentials = None
            if integration.credentials_encrypted:
                try:
                    credentials = decrypt_json(integration.credentials_encrypted)
                except EncryptionError as exc:
                    logger.error(
                        "strava sync: credentials for integration %s undecryptable: %s",
                        integration.id, exc,
                    )
            try:
                client = build_live_client(credentials)
            except Exception as exc:
                logger.warning(
                    "strava sync: skipping user %s (no usable credentials): %s",
                    user.id, exc,
                )
                results[str(user.id)] = {"status": "skipped", "reason": str(exc)}
                continue
            report = await run_user_sync_with_escalation(
                session,
                user,
                integration,
                client,
                page_delay_s=settings.strava_page_delay_seconds,
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
            if client.tokens_out is not None:
                integration.credentials_encrypted = encrypt_json(
                    client.tokens_out.as_credentials()
                )
                await session.commit()
    return results


@celery_app.task(name="strava.sync_all")
def sync_all_strava() -> dict:
    return asyncio.run(_sync_all_active())
