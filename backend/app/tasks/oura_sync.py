"""Oura sync task (§19 cadence: every 6 hours) — mirrors the Whoop task.

Iterates every active oura integration, builds a client from stored
(encrypted) OAuth tokens, skips users without credentials with a warning
(connecting the real account is a manual OAuth step — never automated),
and persists rotated OAuth tokens if the client refreshed mid-run.
"""

import asyncio
import logging

from sqlalchemy import select

from app.connectors.oura.client import OuraClient
from app.connectors.oura.sync import run_user_sync_with_oura
from app.core.db import sessionmaker
from app.core.encryption import decrypt_json, encrypt_json, EncryptionError
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app

logger = logging.getLogger("tasks.oura_sync")


def _build_live_client(credentials: dict) -> OuraClient:
    from app.connectors.oauth2 import OAuth2Error, OAuthTokens

    try:
        tokens = OAuthTokens.from_credentials(credentials)
    except OAuth2Error as exc:
        raise RuntimeError(f"stored Oura credentials unusable: {exc}") from exc
    return OuraClient(tokens)


async def _sync_all_active() -> dict:
    results: dict[str, dict] = {}
    async with sessionmaker() as session:
        integrations = (
            (
                await session.scalars(
                    select(Integration).where(
                        Integration.provider == "oura",
                        Integration.status == "active",
                    )
                )
            )
            .all()
        )
        for integration in integrations:
            user = await session.get(User, integration.user_id)
            if user is None:
                logger.warning("oura sync: integration %s has no user", integration.id)
                continue
            credentials = None
            if integration.credentials_encrypted:
                try:
                    credentials = decrypt_json(integration.credentials_encrypted)
                except EncryptionError as exc:
                    logger.error(
                        "oura sync: credentials for integration %s undecryptable: %s",
                        integration.id, exc,
                    )
            try:
                client = _build_live_client(credentials or {})
            except Exception as exc:
                logger.warning(
                    "oura sync: skipping user %s (no usable credentials): %s",
                    user.id, exc,
                )
                results[str(user.id)] = {"status": "skipped", "reason": str(exc)}
                continue
            report = await run_user_sync_with_oura(session, user, integration, client)
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


@celery_app.task(name="oura.sync_all")
def sync_all_oura() -> dict:
    return asyncio.run(_sync_all_active())
