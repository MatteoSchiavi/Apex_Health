"""Generic §21 sync-failure escalation, shared by every connector.

A failing sync increments `integrations.consecutive_failures`; every third
consecutive failure fires a `sync_failure` alert (warning) instead of failing
silently. Success resets the counter. Raises nothing — the caller gets the
sync's report, or None on failure.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any
import httpx

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration
from app.models.user import User
from app.core.encryption import EncryptionError

logger = logging.getLogger("connectors.escalation")

SYNC_ERROR_CLASSES = frozenset({"authentication", "permission", "transport", "normalization", "timeout", "unknown"})


def sync_error_class(exc: Exception) -> str:
    """Classify without persisting exception messages, arguments or credentials."""
    code = getattr(exc, "error_class", None)
    if isinstance(code, str) and code in SYNC_ERROR_CLASSES:
        return code
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, EncryptionError) or "auth" in type(exc).__name__.lower():
        return "authentication"
    if isinstance(exc, httpx.HTTPStatusError):
        return "authentication" if exc.response.status_code == 401 else "permission" if exc.response.status_code == 403 else "transport"
    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
        return "transport"
    return "unknown"


async def run_sync_with_escalation(
    session: AsyncSession,
    user: User,
    integration: Integration,
    sync_fn: Callable[..., Awaitable[Any]],
    *args: Any,
    source_label: str,
    **kwargs: Any,
) -> Any | None:
    """Run one sync pass with §21 bookkeeping. `source_label` names the
    provider in the alert message (e.g. "Garmin", "Technogym")."""
    integration_id, user_id = integration.id, user.id
    integration._sync_failure_code = None
    try:
        report = await sync_fn(session, user, integration, *args, **kwargs)
    except Exception as exc:
        # SQL failures leave the session unusable until rollback. Checkpoints
        # already committed by the connector survive; unfinished writes do not.
        await session.rollback()
        failures = await session.scalar(
            update(Integration).where(Integration.id == integration_id)
            .values(consecutive_failures=Integration.consecutive_failures + 1)
            .returning(Integration.consecutive_failures)
        )
        if failures and failures % 3 == 0:
            from app.models.alert import Alert

            session.add(
                Alert(
                    user_id=user_id,
                    type="sync_failure",
                    severity="warning",
                    message=(
                        f"{source_label} sync failed "
                        f"{failures} consecutive times. Retry or reconnect the provider."
                    ),
                )
            )
        await session.commit()
        await session.refresh(integration)
        await session.refresh(user)
        # Direct callers retain the existing None contract. The account task
        # can recover this bounded signal without exposing the raw exception.
        integration._sync_failure_code = sync_error_class(exc)
        logger.warning(
            "%s sync failed for user %s (consecutive=%s, error=%s)",
            source_label,
            user_id,
            failures,
            integration._sync_failure_code,
            extra={"event_code": "connector_failed", "error_code": integration._sync_failure_code},
        )
        return None
    integration.consecutive_failures = 0
    # Successful recovery resolves this provider's previous operational alerts.
    # A different connector's alerts and user journal entries remain intact.
    from app.models.alert import Alert
    await session.execute(update(Alert).where(
        Alert.user_id == user_id, Alert.type == "sync_failure",
        Alert.acknowledged.is_(False), Alert.message.startswith(f"{source_label} sync failed "),
    ).values(acknowledged=True))
    await session.commit()
    return report
