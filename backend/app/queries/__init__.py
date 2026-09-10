"""Shared query layer (§8.2).

Every read the bot commands need is a function here — the same functions the
scheduled report tasks (§19) and the agent tools (§8.3) call, so "get my ACWR
trend" has exactly one implementation, not three that drift. The layer grows
with each phase; Phase 5 adds the remaining §8.3 tools (metrics, journal,
plans, search) plus the token_usage accounting (§8.6).
"""

from app.queries.journal import get_journal_entries
from app.queries.labs import get_donation_status, get_lab_trend
from app.queries.metrics import (
    discipline_id_by_slug,
    get_activity_summary,
    get_metric_trend,
)
from app.queries.plans import (
    confirm_plan_draft,
    confirm_supplement_draft,
    create_plan_draft,
    create_supplement_draft,
    get_plan_sessions_for_day,
    get_training_plan,
    reject_plan_draft,
    reject_supplement_draft,
)
from app.queries.search import search_context, store_embedding
from app.queries.snapshot import (
    activities_on_local_date,
    gear_overview,
    integrations_overview,
    latest_daily_feature,
    open_alerts,
    recent_daily_features,
    sleep_on_local_date,
)
from app.queries.usage import (
    day_spend,
    estimate_embedding_cost_usd,
    estimate_llm_cost_usd,
    log_embedding_usage,
    log_llm_usage,
)

__all__ = [
    "activities_on_local_date",
    "confirm_plan_draft",
    "confirm_supplement_draft",
    "create_plan_draft",
    "create_supplement_draft",
    "day_spend",
    "discipline_id_by_slug",
    "estimate_embedding_cost_usd",
    "estimate_llm_cost_usd",
    "gear_overview",
    "get_activity_summary",
    "get_donation_status",
    "get_journal_entries",
    "get_lab_trend",
    "get_metric_trend",
    "get_plan_sessions_for_day",
    "get_training_plan",
    "integrations_overview",
    "latest_daily_feature",
    "log_embedding_usage",
    "log_llm_usage",
    "open_alerts",
    "recent_daily_features",
    "reject_plan_draft",
    "reject_supplement_draft",
    "search_context",
    "sleep_on_local_date",
    "store_embedding",
]
