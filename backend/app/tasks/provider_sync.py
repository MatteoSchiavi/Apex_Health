"""Account-scoped durable sync jobs shared by the wearable connectors."""

import hashlib
import logging
from importlib import import_module
import httpx

from sqlalchemy import select, text, update

from app.core.config import get_settings
from app.core.db import engine, sessionmaker
from app.core.encryption import EncryptionError, decrypt_json, encrypt_json
from app.models.integration import Integration
from app.models.user import User
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async
from app.services.alpha_events import record_event

logger = logging.getLogger(__name__)


class SyncTaskError(Exception):
    """Sanitized failure that Celery can retry and expose as a failed job."""
    def __init__(self, message, *, error_class="unknown"):
        super().__init__(message)
        self.error_class = error_class


def _sync_error_class(exc):
    if isinstance(exc, SyncTaskError):
        return exc.error_class if exc.error_class in {
            "authentication", "permission", "transport", "normalization", "timeout", "unknown"
        } else "unknown"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, EncryptionError) or "auth" in type(exc).__name__.lower():
        return "authentication"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 401:
            return "authentication"
        if exc.response.status_code == 403:
            return "permission"
        return "transport"
    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
        return "transport"
    return "unknown"


async def _record_sync_outcome(provider, user_id, *, error_class=None):
    # Connector checkpoint commits occur in a different session. Record the
    # outcome after they finish, and never turn telemetry failure into a retry.
    try:
        async with sessionmaker() as session:
            if await session.get(User, user_id) is None:
                return
            metadata = {"provider": provider}
            if error_class is not None:
                metadata["error_class"] = error_class
            record_event(session, user_id, "integration_sync_failure" if error_class else "integration_sync_success", metadata)
            await session.commit()
    except Exception:
        logger.warning("sync outcome event unavailable")


async def sync_account(provider: str, user_id: int) -> dict:
    # A session-level advisory lock survives connector checkpoint commits.
    # PostgreSQL releases it if the worker dies; no stale Redis lease remains.
    lock_id = int.from_bytes(hashlib.sha256(f"sync:{provider}:{user_id}".encode()).digest()[:8], "big", signed=True)
    async with engine.connect() as connection:
        if not await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}):
            # Commit/rollback alone cannot release session advisory locks.
            raise SyncTaskError("This account already has a sync running")
        try:
            try:
                result = await _sync_account(provider, user_id)
            except Exception as exc:
                await _record_sync_outcome(provider, user_id, error_class=_sync_error_class(exc))
                raise
            if result.get("status") != "skipped":
                await _record_sync_outcome(provider, user_id,
                    error_class="normalization" if result.get("status") == "partial" else None)
            return result
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
            raise SyncTaskError("Stored credentials could not be decrypted; reconnect the provider", error_class="authentication") from None
        if not credentials:
            # A friend's missing credential must never fall back to the
            # owner's global Garmin environment variables.
            raise SyncTaskError("No stored provider credentials; connect this account first", error_class="authentication")
        connector = import_module(f"app.connectors.{provider}.client")
        try:
            client = connector.build_live_client(credentials)
        except Exception:
            raise SyncTaskError("Provider credentials are unusable; reconnect the provider", error_class="authentication") from None
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
            raise SyncTaskError("Provider sync failed; retrying may recover it", error_class="transport")
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
