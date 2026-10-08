"""Account-scoped, redacted view of provider synchronization health."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import Integration
from app.models.lab import FeedState, Observation

STALE_AFTER_HOURS = 48
_STALE_AFTER = timedelta(hours=STALE_AFTER_HOURS)

# These are the providers currently driven by OAuth/device credentials in the
# connector/task layer. Presence means only that an encrypted blob is stored;
# this API deliberately never decrypts it or claims that it is still valid.
_CREDENTIAL_PROVIDERS = frozenset(
    {"garmin", "technogym", "strava", "whoop", "oura", "coros"}
)

_FEED_STATES = frozenset(
    {
        "available",
        "not_measured",
        "pending_sync",
        "partial",
        "complete",
        "fetch_failed",
        "stale",
        "not_supported",
        "not_exposed",
        "permission_denied",
    }
)


def _credentials_state(integration: Integration | None, provider: str) -> str:
    if integration is None:
        return "unknown"
    if integration.status == "revoked":
        return "reconnect_required"
    if integration.credentials_encrypted is not None:
        return "configured"
    if provider in _CREDENTIAL_PROVIDERS:
        return "reconnect_required"
    return "unknown"


def _state_from_feed(feed: FeedState, now: datetime) -> str:
    raw_state = feed.availability
    state = raw_state if raw_state in _FEED_STATES else "unknown"
    measured_at = feed.latest_measurement_at
    if (
        measured_at is not None
        and measured_at < now - _STALE_AFTER
        and state in {"available", "partial", "complete", "stale"}
    ):
        return "stale"
    return state


def _error_class(
    feed: FeedState | None,
    integration: Integration | None,
) -> str | None:
    """Map known persisted states to safe codes; never expose details/errors."""
    if feed is not None:
        if feed.availability == "fetch_failed":
            return "fetch_failed"
        if feed.availability == "partial":
            return "normalization_pending"
        # A provider-level failed attempt does not mean every independently
        # fetched metric failed. The account summary carries that error.
        if feed.availability in {"available", "complete", "not_measured"}:
            return None
    if integration is not None:
        if integration.status == "revoked":
            return "credentials_revoked"
        if integration.status == "error" or integration.consecutive_failures > 0:
            return "sync_failed"
    return None


def _retry_state(
    credentials_state: str,
    integration: Integration | None,
) -> str:
    if credentials_state == "reconnect_required":
        return "reconnect_required"
    if integration is not None and integration.consecutive_failures > 0:
        # Celery retry countdowns are not persisted in this schema. Do not
        # guess that a retry is queued from the failure counter alone.
        return "unknown"
    return "idle"


async def _latest_measurement(
    session: AsyncSession, user_id: int, provider: str
) -> datetime | None:
    observation_at = await session.scalar(
        select(func.max(Observation.measured_at)).where(
            Observation.user_id == user_id,
            Observation.origin == provider,
            Observation.current.is_(True),
        )
    )
    activity_at = await session.scalar(
        select(func.max(Activity.start_time))
        .join(ActivitySourceLink, ActivitySourceLink.activity_id == Activity.id)
        .where(
            Activity.user_id == user_id,
            ActivitySourceLink.user_id == user_id,
            ActivitySourceLink.source == provider,
        )
    )
    measurements = [value for value in (observation_at, activity_at) if value]
    return max(measurements) if measurements else None


def _base_feed(
    *,
    provider: str,
    feed_name: str,
    feed: FeedState | None,
    integration: Integration | None,
    now: datetime,
    latest_measurement_at: datetime | None = None,
) -> dict:
    credentials_state = _credentials_state(integration, provider)
    if feed is not None:
        measured_at = feed.latest_measurement_at
        state = _state_from_feed(feed, now)
        last_attempt_at = feed.last_attempt_at
        last_success_at = feed.last_success_at
    else:
        measured_at = latest_measurement_at
        if integration is None:
            state = "unknown"
        elif integration.status in {"revoked", "error"} or integration.consecutive_failures:
            state = "fetch_failed"
        elif measured_at is not None and measured_at < now - _STALE_AFTER:
            state = "stale"
        elif measured_at is not None or integration.last_synced_at is not None:
            state = "available"
        else:
            state = "unknown"
        # last_synced_at records successful completion, not an attempted
        # start. Do not manufacture an attempt timestamp for this synthetic row.
        last_attempt_at = None
        last_success_at = integration.last_synced_at if integration else None

    return {
        "provider": provider,
        "feed": feed_name,
        "state": state,
        "last_attempt_at": last_attempt_at,
        "last_success_at": last_success_at,
        "latest_measurement_at": measured_at,
        "stale_after_hours": STALE_AFTER_HOURS,
        "error_class": _error_class(feed, integration),
        "retry_state": _retry_state(credentials_state, integration),
        "has_checkpoint": bool(
            feed is not None and feed.cursor
        ),
        "failed_attempts": integration.consecutive_failures if integration else 0,
        "credentials_state": credentials_state,
    }


async def sync_health(
    session: AsyncSession, user_id: int, *, now: datetime | None = None
) -> dict[str, list[dict]]:
    """Return safe per-feed health, including integrations with no feed row.

    Feed rows, integrations, observations, and activities are all scoped to the
    caller's user id. Raw cursors/details and encrypted credentials are never
    serialized.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    integrations = (
        await session.scalars(
            select(Integration)
            .where(Integration.user_id == user_id)
            .order_by(Integration.provider)
        )
    ).all()
    integration_by_provider = {row.provider: row for row in integrations}
    feed_rows = (
        await session.scalars(
            select(FeedState)
            .where(FeedState.user_id == user_id)
            .order_by(FeedState.provider, FeedState.feed)
        )
    ).all()

    feeds: list[dict] = []
    providers_with_feed_rows: set[str] = set()
    for feed in feed_rows:
        providers_with_feed_rows.add(feed.provider)
        feeds.append(
            _base_feed(
                provider=feed.provider,
                feed_name=feed.feed,
                feed=feed,
                integration=integration_by_provider.get(feed.provider),
                now=now,
            )
        )

    # Integration-level sync is still useful when no metric feed has ever
    # emitted a FeedState (for example, activity-only providers). Use a stable
    # synthetic feed name and measured timestamps from owned observations or
    # canonical activities where those records exist.
    for provider, integration in integration_by_provider.items():
        if provider in providers_with_feed_rows:
            continue
        measured_at = await _latest_measurement(session, user_id, provider)
        feeds.append(
            _base_feed(
                provider=provider,
                feed_name="account_sync",
                feed=None,
                integration=integration,
                now=now,
                latest_measurement_at=measured_at,
            )
        )

    feeds.sort(key=lambda row: (row["provider"], row["feed"]))
    return {"feeds": feeds}
