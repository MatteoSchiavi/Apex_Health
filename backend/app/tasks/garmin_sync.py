"""Garmin sync task (§19: every 6 hours) and per-user driver (§21 escalation).

The scheduled run iterates every active garmin integration. Clients are built
from stored (encrypted) credentials; users whose credentials are absent are
skipped with a warning — connecting a real account is the owner's manual step
(§23 Phase 1 acceptance), never an automated one.

F-03 audit: the loop body is wrapped per-user so one user's unexpected
exception cannot abort the remaining users' syncs. Each user is also
available as a standalone per-user task (``garmin.sync_user``) so retries,
visibility and escalation are per-user by construction.
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


async def _sync_one_user(
    session,
    settings,
    integration: Integration,
    user: User,
) -> dict:
    """Sync ONE user — never raises; failures land in the result dict.

    F-03 audit: this is the per-user isolation boundary. The caller can
    iterate every integration and one user's failure no longer aborts the
    rest of the batch.
    """
    credentials = None
    if integration.credentials_encrypted:
        try:
            credentials = decrypt_json(integration.credentials_encrypted)
        except EncryptionError as exc:
            logger.error(
                "garmin sync: credentials for integration %s undecryptable: %s",
                integration.id, exc,
            )
            return {"status": "skipped", "reason": "undecryptable credentials"}
    try:
        client = build_live_client(credentials)
    except GarminAuthError as exc:
        logger.warning(
            "garmin sync: skipping user %s (no usable credentials): %s",
            user.id, exc,
        )
        return {"status": "skipped", "reason": str(exc)}
    try:
        report = await run_user_sync_with_escalation(
            session,
            user,
            integration,
            client,
            page_size=settings.garmin_activity_page_size,
            page_delay_s=settings.garmin_page_delay_seconds,
            empty_gap_days=settings.garmin_backfill_empty_gap_days,
        )
    except Exception as exc:  # F-03: isolate per user — log and continue.
        logger.exception("garmin sync crashed for user %s: %s", user.id, exc)
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    if report is None:
        return {"status": "failed"}
    return {
        "status": "ok",
        "mode": report.mode,
        "raw_stored": report.raw_rows_stored,
        "unprocessed": report.raw_rows_unprocessed,
    }


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
            # F-03: per-user isolation — one user's failure cannot abort
            # the remaining users' syncs.
            results[str(user.id)] = await _sync_one_user(session, settings, integration, user)
    return results


@celery_app.task(name="garmin.sync_all")
def sync_all_garmin() -> dict:
    return asyncio.run(_sync_all_active())


@celery_app.task(
    name="garmin.sync_user",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def sync_user_garmin(user_id: int) -> dict:
    """Per-user Garmin sync (F-03 + F-11 audit).

    One user, one integration, one sync pass. Used by:
    - ``POST /settings/integrations/garmin/sync`` (F-11: scoped to the
      connecting user, NOT a global fan-out).
    - The per-user retry path (autoretry with exponential backoff).
    """
    return asyncio.run(_sync_user_garmin(user_id))


async def _sync_user_garmin(user_id: int) -> dict:
    settings = get_settings()
    async with sessionmaker() as session:
        integration = await session.scalar(
            select(Integration).where(
                Integration.user_id == user_id,
                Integration.provider == "garmin",
                Integration.status == "active",
            )
        )
        if integration is None:
            return {"status": "skipped", "reason": "no active garmin integration"}
        user = await session.get(User, user_id)
        if user is None:
            return {"status": "skipped", "reason": "user not found"}
        return await _sync_one_user(session, settings, integration, user)
