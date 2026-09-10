"""Shared query layer (§8.2).

Every read the bot commands need is a function here — the same functions the
scheduled report tasks (§19) and the agent tools (§8.3) call, so "get my ACWR
trend" has exactly one implementation, not three that drift. The layer grows
with each phase; Phase 5 adds the remaining §8.3 tools.
"""

from app.queries.labs import get_donation_status, get_lab_trend
from app.queries.snapshot import (
    activities_on_local_date,
    gear_overview,
    integrations_overview,
    latest_daily_feature,
    open_alerts,
    recent_daily_features,
    sleep_on_local_date,
)

__all__ = [
    "activities_on_local_date",
    "gear_overview",
    "get_donation_status",
    "get_lab_trend",
    "integrations_overview",
    "latest_daily_feature",
    "open_alerts",
    "recent_daily_features",
    "sleep_on_local_date",
]
