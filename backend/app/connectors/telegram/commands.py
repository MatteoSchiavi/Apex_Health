"""Bot commands (§10.3): /status, /donate, /report, /gear, /plan.

All data reads go through app/queries (§8.2 — one implementation per read,
shared with the future agent tools and report tasks). /report is the
templated daily summary: deliberately NO LLM call (§9.2). /plan is the
§11b fallback delivery path — the confirmed plan reaches the user in
Telegram while prescription-push awaits the real Technogym access tier.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.connectors.telegram.link_flow import get_linked_user_id
from app.models.user import User
from app.queries import (
    activities_on_local_date,
    get_donation_status,
    get_plan_sessions_for_day,
    gear_overview,
    integrations_overview,
    latest_daily_feature,
    open_alerts,
    sleep_on_local_date,
)

logger = logging.getLogger("connectors.telegram.commands")

NO_FEATURES = "No daily metrics yet — connect a source and let the nightly feature engine run."
NO_DONATIONS = "No donations recorded yet — lab panels land here with the medical module (Phase 4)."
NO_GEAR = "No gear tracked yet — gear arrives with the maintenance module (Phase 4)."


async def cmd_status(ctx, chat_id: int, user_id: int) -> str:
    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        now = datetime.now(ZoneInfo(user.timezone))
        feature = await latest_daily_feature(session, user_id)
        integrations = await integrations_overview(session, user_id)
        alerts = await open_alerts(session, user_id)

    lines = [f"Status — {now.strftime('%Y-%m-%d %H:%M')} ({user.timezone})"]
    if feature is None:
        lines.append(NO_FEATURES)
    else:
        lines.append(
            f"Recovery {_fmt(feature.recovery_score, 0)} · "
            f"Strain {_fmt(feature.strain_score, 1)} · "
            f"Readiness {_fmt(feature.readiness_score, 0)} ({feature.date})"
        )
        lines.append(f"ACWR {_fmt(feature.acwr, 2)}")
    if integrations:
        lines.append("Integrations:")
        for i in integrations:
            synced = i["last_synced_at"].strftime("%Y-%m-%d %H:%MZ") if i["last_synced_at"] else "never"
            suffix = f", {i['consecutive_failures']} consecutive failures" if i["consecutive_failures"] else ""
            lines.append(f"- {i['provider']}: {i['status']}, last sync {synced}{suffix}")
    else:
        lines.append("No integrations connected yet.")
    lines.append(f"Open alerts: {len(alerts)}")
    return "\n".join(lines)


async def cmd_donate(ctx, chat_id: int, user_id: int) -> str:
    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        today = datetime.now(ZoneInfo(user.timezone)).date()
        feature = await latest_daily_feature(session, user_id)
        status = await get_donation_status(session, user_id, today)

    if status is None:
        return NO_DONATIONS
    lines = [
        "Donation status",
        f"Last {status['donation_type']}: {status['date']} ({status['days_since']} days ago)",
    ]
    if status["next_eligible_date"]:
        eligible = today >= status["next_eligible_date"]
        lines.append(
            f"Next eligible: {status['next_eligible_date']} — "
            + ("eligible now" if eligible else f"in {(status['next_eligible_date'] - today).days} days")
        )
    lines.append("Iron flag: " + (str(feature.iron_status_flag) if feature and feature.iron_status_flag else "none yet"))
    return "\n".join(lines)


async def cmd_report(ctx, chat_id: int, user_id: int) -> str:
    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        tz = ZoneInfo(user.timezone)
        feature = await latest_daily_feature(session, user_id)
        if feature is None:
            return NO_FEATURES
        activities = await activities_on_local_date(session, user_id, feature.date)
        sleep = await sleep_on_local_date(session, user_id, feature.date)

    lines = [f"Daily report — {feature.date} ({user.timezone})"]
    lines.append(
        f"Readiness {_fmt(feature.readiness_score, 0)} · "
        f"Recovery {_fmt(feature.recovery_score, 0)} · "
        f"Strain {_fmt(feature.strain_score, 1)}"
    )
    lines.append(
        f"ACWR {_fmt(feature.acwr, 2)} "
        f"(acute {_fmt(feature.training_load_acute, 0)} · chronic {_fmt(feature.training_load_chronic, 0)})"
    )
    if sleep:
        lines.append(
            f"Sleep {_fmt_duration(sleep['total_sleep_s'])}"
            + (f" · score {_fmt(sleep['sleep_score'], 0)}" if sleep["sleep_score"] is not None else "")
        )
    if feature.hrv_deviation_from_baseline is not None:
        lines.append(f"HRV {_fmt(feature.hrv_deviation_from_baseline, 1)}% vs baseline")
    if activities:
        parts = []
        for a in activities:
            part = f"{a['discipline']} {_fmt_duration(a['duration_s'])}"
            if a["distance_m"]:
                part += f" ({a['distance_m'] / 1000:.1f} km)"
            parts.append(part)
        lines.append("Training: " + " · ".join(parts))
    else:
        lines.append("No activities on this day.")
    return "\n".join(lines)


async def cmd_gear(ctx, chat_id: int, user_id: int) -> str:
    async with ctx.sessionmaker() as session:
        items = await gear_overview(session, user_id)
    if not items:
        return NO_GEAR
    lines = ["Gear:"]
    for g in items:
        detail = []
        if g["service_interval_km"]:
            detail.append(f"{g['km_since_service']:.0f}/{g['service_interval_km']:.0f} km")
        if g["service_interval_hours"]:
            detail.append(f"{g['hours_since_service']:.0f}/{g['service_interval_hours']:.0f} h")
        pct = f" ({g['usage_pct']:.0f}%)" if g["usage_pct"] is not None else ""
        flag = " ⚠️ service due" if (g["usage_pct"] or 0) >= 100 else ""
        lines.append(f"- {g['name']} ({g['gear_type']}): " + ", ".join(detail) + pct + flag)
    return "\n".join(lines)


async def resolve_user_id(ctx, chat_id: int) -> int | None:
    async with ctx.sessionmaker() as session:
        return await get_linked_user_id(session, chat_id)


def _fmt(value, digits: int) -> str:
    return f"{float(value):.{digits}f}" if value is not None else "—"


def _fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h{m:02d}" if h else f"{m}m"


NO_PLAN_TODAY = (
    "No confirmed plan sessions for today."
    "\n\nNote: prescription-push to Technogym equipment (§11b) awaits the "
    "access-tier confirmation (§24) — until then follow the plan manually."
)


async def cmd_plan(ctx, chat_id: int, user_id: int) -> str:
    """§11b fallback delivery: the day's CONFIRMED-plan sessions. '/plan' and
    '/plan today' are the same (the day-boundary rule makes 'today' local)."""
    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        local_today = datetime.now(ZoneInfo(user.timezone)).date()
        sessions = await get_plan_sessions_for_day(session, user_id, local_today)
    if not sessions:
        return NO_PLAN_TODAY

    lines = [f"Plan for today — {local_today.isoformat()}:"]
    for s in sessions:
        detail = []
        if s["session_type"]:
            detail.append(s["session_type"])
        if s["target_duration_min"]:
            detail.append(f"{s['target_duration_min']} min")
        if s["target_load"] is not None:
            detail.append(f"load {s['target_load']:.0f}")
        if s["description"]:
            detail.append(s["description"])
        lines.append(f"- " + " · ".join(detail))
    lines.append(
        "\nPrescription-push to Technogym equipment (§11b) awaits the "
        "access-tier confirmation (§24) — follow the session manually."
    )
    return "\n".join(lines)
