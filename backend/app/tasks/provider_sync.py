"""Account-scoped durable sync jobs shared by the wearable connectors."""

import hashlib
from importlib import import_module

from sqlalchemy import select, text, update

from app.core.config import get_settings
from app.core.db import engine, sessionmaker
from app.core.encryption import EncryptionError, decrypt_json, encrypt_json
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async


class SyncTaskError(Exception):
    """Sanitized failure that Celery can retry and expose as a failed job."""


async def sync_account(provider: str, user_id: int) -> dict:
    # A session-level advisory lock survives connector checkpoint commits.
    # PostgreSQL releases it if the worker dies; no stale Redis lease remains.
    lock_id = int.from_bytes(hashlib.sha256(f"sync:{provider}:{user_id}".encode()).digest()[:8], "big", signed=True)
    async with engine.connect() as connection:
        if not await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}):
            # Commit/rollback alone cannot release session advisory locks.
            raise SyncTaskError("This account already has a sync running")
        try:
            return await _sync_account(provider, user_id)
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})


async def _sync_account(provider: str, user_id: int) -> dict:
    settings = get_settings()
    async with sessionmaker() as session:
        integration = await session.scalar(select(Integration).where(
            Integration.user_id == user_id, Integration.provider == provider,
            Integration.status == "active",
        ))
        if integration is None:
            return {"status": "skipped", "reason": "No active integration"}
        integration_id = integration.id
        user = await session.get(User, user_id)
        if user is None:
            return {"status": "skipped", "reason": "Account no longer exists"}
        try:
            credentials = decrypt_json(integration.credentials_encrypted) if integration.credentials_encrypted else None
        except EncryptionError:
            raise SyncTaskError("Stored credentials could not be decrypted; reconnect the provider") from None
        if not credentials:
            # A friend's missing credential must never fall back to the
            # owner's global Garmin environment variables.
            raise SyncTaskError("No stored provider credentials; connect this account first")
        connector = import_module(f"app.connectors.{provider}.client")
        try:
            client = connector.build_live_client(credentials)
        except Exception:
            raise SyncTaskError("Provider credentials are unusable; reconnect the provider") from None
        sync = import_module(f"app.connectors.{provider}.sync").run_user_sync_with_escalation
        kwargs = {}
        if provider in {"garmin", "technogym"}:
            kwargs.update(page_size=getattr(settings, f"{provider}_activity_page_size"), page_delay_s=getattr(settings, f"{provider}_page_delay_seconds"))
        if provider == "garmin":
            kwargs.update(empty_gap_days=settings.garmin_backfill_empty_gap_days, checkpoint=True)
        if provider == "strava":
            kwargs["page_delay_s"] = settings.strava_page_delay_seconds
        try:
            report = await sync(session, user, integration, client, **kwargs)
        finally:
            try:
                # Refreshed OAuth tokens must survive even when the subsequent
                # request fails, or the next attempt starts with invalid tokens.
                tokens = getattr(client, "tokens_out", None)
                refreshed_credentials = None
                if tokens is not None:
                    refreshed_credentials = tokens.as_credentials()
                if provider == "garmin" and hasattr(client, "dump_tokens"):
                    refreshed_credentials = client.dump_tokens()
                if refreshed_credentials is not None:
                    await session.execute(update(Integration).where(
                        Integration.id == integration_id, Integration.status == "active",
                    ).values(credentials_encrypted=encrypt_json(refreshed_credentials)))
                    await session.commit()
            finally:
                close = getattr(client, "aclose", None)
                if close is not None:
                    await close()
        if report is None:
            raise SyncTaskError("Provider sync failed; retrying may recover it")
        return {"status": "partial" if getattr(report, "raw_rows_unprocessed", 0) else "ok",
                "mode": report.mode, "raw_stored": report.raw_rows_stored,
                "unprocessed": getattr(report, "raw_rows_unprocessed", 0)}


async def enqueue_active(provider: str) -> dict:
    async with sessionmaker() as session:
        users = (await session.scalars(select(Integration.user_id).where(
            Integration.provider == provider, Integration.status == "active",
        ))).all()
    return {str(user_id): {"task_id": celery_app.send_task(
        f"{provider}.sync_user", args=[user_id],
    ).id} for user_id in users}


def register_tasks(provider: str):
    @celery_app.task(name=f"{provider}.sync_all")
    def sync_all():
        return run_async(enqueue_active(provider))

    @celery_app.task(name=f"{provider}.sync_user", autoretry_for=(SyncTaskError,),
                     retry_backoff=60, retry_backoff_max=600, retry_jitter=True, max_retries=3)
    def sync_user(user_id: int):
        try:
            return run_async(sync_account(provider, user_id))
        except Exception as exc:
            if not isinstance(exc, SyncTaskError) or sync_user.request.retries >= 3:
                from app.services.owner_notifications import critical_connector_error
                try:
                    run_async(critical_connector_error(provider, user_id))
                except Exception:
                    pass
            raise
    return sync_all, sync_user
