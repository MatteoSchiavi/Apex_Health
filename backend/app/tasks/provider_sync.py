"""Account-scoped durable sync jobs shared by the wearable connectors."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from importlib import import_module
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text, update

from app.core.config import get_settings
from app.core.db import engine, sessionmaker
from app.core.encryption import EncryptionError, decrypt_json, encrypt_json
from app.models.integration import Integration
from app.models.lab import FeedState
from app.models.user import AuthCredential, User
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async
from app.services.alpha_events import record_event
from app.connectors.escalation import sync_error_class as _sync_error_class

logger = logging.getLogger(__name__)


class SyncTaskError(Exception):
    """Sanitized failure that Celery can retry and expose as a failed job."""
    def __init__(self, message, *, error_class="unknown", failure_counted=False):
        super().__init__(message)
        self.error_class = error_class
        self.failure_counted = failure_counted


async def _record_sync_outcome(provider, user_id, *, error_class=None, status="ok", result=None,
                               failure_counted=False):
    # Connector checkpoint commits occur in a different session. Record the
    # outcome after they finish, and never turn telemetry failure into a retry.
    try:
        async with sessionmaker() as session:
            if await session.get(User, user_id) is None:
                return
            integration = await session.scalar(select(Integration).where(
                Integration.user_id == user_id, Integration.provider == provider).with_for_update())
            if status == "syncing":
                credential = await session.get(AuthCredential, user_id)
                if integration is None or integration.status != "active" or (credential is not None and credential.disabled):
                    return
            failure_count = 0
            if integration is not None:
                if error_class is not None and not failure_counted:
                    integration.consecutive_failures = min(32767, integration.consecutive_failures + 1)
                elif status in {"ok", "partial"} and error_class is None:
                    integration.consecutive_failures = 0
                failure_count = integration.consecutive_failures
            feed = await session.scalar(select(FeedState).where(
                FeedState.user_id == user_id, FeedState.provider == provider, FeedState.feed == "account_sync"))
            if feed is None:
                feed = FeedState(user_id=user_id, provider=provider, feed="account_sync", details={}, cursor={})
                session.add(feed)
            now = datetime.now(UTC)
            if status == "syncing" or feed.last_attempt_at is None or feed.availability != "pending_sync":
                feed.last_attempt_at = now
            feed.availability = ("fetch_failed" if error_class else "pending_sync" if status == "syncing"
                                 else "partial" if status == "partial" else "available")
            details = {"state": "failed" if error_class else status}
            if (feed.details or {}).get("alert_state") in {"failed", "auth_required", "partial"}:
                details["alert_state"] = feed.details["alert_state"]
            if error_class:
                details["error_class"] = error_class
            if status in {"ok", "partial"} and error_class is None:
                feed.last_success_at = now
                for key in ("streams_failed", "unprocessed"):
                    value = (result or {}).get(key, 0)
                    details[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
            feed.details = details
            if status == "syncing":
                await session.commit()
                return
            metadata = {"provider": provider}
            if error_class is not None:
                metadata["error_class"] = error_class
            event = "integration_sync_failure" if error_class else "integration_sync_partial" if status == "partial" else "integration_sync_success"
            record_event(session, user_id, event, metadata)
            await session.commit()
        from app.services.owner_notifications import connector_outcome_notification
        await connector_outcome_notification(provider, user_id,
            "failed" if error_class else "partial" if status == "partial" else "successful",
            error_class=error_class, failure_count=failure_count)
    except Exception:
        logger.warning("sync outcome event unavailable")


async def sync_account(provider: str, user_id: int) -> dict:
    # A session-level advisory lock survives connector checkpoint commits.
    # PostgreSQL releases it if the worker dies; no stale Redis lease remains.
    lock_id = int.from_bytes(hashlib.sha256(f"sync:{provider}:{user_id}".encode()).digest()[:8], "big", signed=True)
    async with engine.connect() as connection:
        if not await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}):
            return {"status": "skipped", "reason": "already_running"}
        try:
            await _record_sync_outcome(provider, user_id, status="syncing")
            try:
                result = await _sync_account(provider, user_id)
            except Exception as exc:
                code = _sync_error_class(exc)
                await _record_sync_outcome(provider, user_id, error_class=code,
                                           failure_counted=getattr(exc, "failure_counted", False))
                raise SyncTaskError("Provider sync failed; retry or review provider access", error_class=code) from None
            if result.get("status") != "skipped":
                await _record_sync_outcome(provider, user_id,
                                           status=result.get("status", "ok"), result=result)
            return result
        finally:
            try:
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
            except Exception:
                # A lost connection releases the session lock itself. An
                # unlock failure must not reclassify committed ingestion.
                await connection.invalidate()
                logger.warning("sync lock release unavailable")


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
        original_encrypted_credentials = integration.credentials_encrypted
        user = await session.get(User, user_id)
        if user is None:
            return {"status": "skipped", "reason": "Account no longer exists"}
        credential = await session.scalar(select(AuthCredential).where(AuthCredential.user_id == user_id))
        if credential is not None and credential.disabled:
            return {"status": "skipped", "reason": "Account disabled"}
        try:
            credentials = decrypt_json(integration.credentials_encrypted) if integration.credentials_encrypted else None
        except EncryptionError:
            raise SyncTaskError("Stored credentials could not be decrypted; reconnect the provider", error_class="authentication") from None
        if not credentials:
            # A friend's missing credential must never fall back to the
            # owner's global Garmin environment variables.
            raise SyncTaskError("No stored provider credentials; connect this account first", error_class="authentication")
        from app.features.engine import compute_missing_recorded_days, compute_user_range
        today = datetime.now(UTC).astimezone(ZoneInfo(user.timezone)).date()
        # Resume durable historical invalidations before a potentially long
        # upstream walk; never rely on an in-process list surviving a restart.
        await compute_missing_recorded_days(session, user, today - timedelta(days=365), today)
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
                        Integration.id == integration_id, Integration.user_id == user_id,
                        Integration.status == "active",
                        Integration.credentials_encrypted == original_encrypted_credentials,
                    ).values(credentials_encrypted=encrypt_json(refreshed_credentials)))
                    await session.commit()
            finally:
                close = getattr(client, "aclose", None)
                if close is not None:
                    await close()
        # Nightly calculations run before most athletes wake up. Refresh
        # today's row after ingestion as well, so newly fetched sleep/HRV and
        # activities are reflected without borrowing yesterday's scores.
        # A later backfill failure must not hide already committed checkpoints.
        today = datetime.now(UTC).astimezone(ZoneInfo(user.timezone)).date()
        await compute_missing_recorded_days(session, user, today - timedelta(days=365), today)
        await compute_user_range(session, user, today - timedelta(days=28), today)
        if report is None:
            code = getattr(integration, "_sync_failure_code", None) or "transport"
            raise SyncTaskError("Provider sync failed; retrying may recover it", error_class=code,
                                failure_counted=bool(getattr(integration, "_sync_failure_code", None)))
        return {"status": "partial" if getattr(report, "raw_rows_unprocessed", 0) or getattr(report, "streams_failed", 0) else "ok",
                "mode": report.mode, "raw_stored": report.raw_rows_stored,
                "streams_failed": getattr(report, "streams_failed", 0),
                "unprocessed": getattr(report, "raw_rows_unprocessed", 0)}


async def enqueue_active(provider: str) -> dict:
    async with sessionmaker() as session:
        users = (await session.scalars(select(Integration.user_id)
            .outerjoin(AuthCredential, AuthCredential.user_id == Integration.user_id).where(
            Integration.provider == provider, Integration.status == "active",
            or_(AuthCredential.user_id.is_(None), AuthCredential.disabled.is_(False)),
        ))).all()
    return {str(user_id): {"task_id": celery_app.send_task(
        f"{provider}.sync_user", args=[user_id],
    ).id} for user_id in users}


def register_tasks(provider: str):
    @celery_app.task(name=f"{provider}.sync_all")
    def sync_all():
        return run_async(enqueue_active(provider))

    @celery_app.task(name=f"{provider}.sync_user", autoretry_for=(SyncTaskError,),
                     retry_backoff=60, retry_backoff_max=600, retry_jitter=True, max_retries=3,
                     throws=(SyncTaskError,))
    def sync_user(user_id: int):
        try:
            return run_async(sync_account(provider, user_id))
        except Exception as exc:
            if not isinstance(exc, SyncTaskError):
                try:
                    run_async(_record_sync_outcome(provider, user_id, error_class=_sync_error_class(exc)))
                except Exception:
                    pass
                raise SyncTaskError("Provider sync failed; retry or review provider access", error_class=_sync_error_class(exc)) from None
            raise
    return sync_all, sync_user
