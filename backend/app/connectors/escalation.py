"""Generic §21 sync-failure escalation, shared by every connector.

A failing sync increments `integrations.consecutive_failures`; every third
consecutive failure fires a `sync_failure` alert (warning) instead of failing
silently. Success resets the counter. Raises nothing — the caller gets the
sync's report, or None on failure.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

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
    try:
        report = await sync_fn(session, user, integration, *args, **kwargs)
    except Exception as exc:
        integration.consecutive_failures = (integration.consecutive_failures or 0) + 1
        if integration.consecutive_failures % 3 == 0:
            from app.models.alert import Alert

            session.add(
                Alert(
                    user_id=user.id,
                    type="sync_failure",
                    severity="warning",
                    message=(
                        f"{source_label} sync failed "
                        f"{integration.consecutive_failures} consecutive times: {exc}"
                    ),
                )
            )
        await session.commit()
        logger.error(
            "%s sync failed for user %s (consecutive=%s): %s",
            source_label,
            user.id,
            integration.consecutive_failures,
            exc,
        )
        return None
    integration.consecutive_failures = 0
    await session.commit()
    return report
