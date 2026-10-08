"""Generic §21 sync-failure escalation, shared by every connector.

A failing sync increments `integrations.consecutive_failures`; every third
consecutive failure fires a `sync_failure` alert (warning) instead of failing
silently. Success resets the counter. Raises nothing — the caller gets the
sync's report, or None on failure.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import Integration
from app.models.user import User

logger = logging.getLogger("connectors.escalation")


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
        logger.error(
            "%s sync failed for user %s (consecutive=%s, error=%s)",
            source_label,
            user_id,
            failures,
            type(exc).__name__,
            extra={"event_code": "connector_failed", "error_code": type(exc).__name__},
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
