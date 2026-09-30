"""Bot commands (§10.3): /status, /donate, /report, /gear, /plan, /forecast,
/gym.

All data reads go through app/queries (§8.2 — one implementation per read,
shared with the future agent tools and report tasks). /report is the
templated daily summary: deliberately NO LLM call (§9.2). /plan is the
§11b fallback delivery path — the confirmed plan reaches the user in
Telegram while prescription-push awaits the real Technogym access tier.
/forecast is §14's primary access point while the web dashboard is deferred.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.connectors.telegram.link_flow import get_linked_user_id
from app.models.user import User
from app.queries import (
    activities_on_local_date,
    create_slot,
    delete_slot,
    describe_weather_code,
    get_donation_status,
    get_forecast,
    get_plan_sessions_for_day,
    gear_overview,
    integrations_overview,
    latest_daily_feature,
    list_slots,
    open_alerts,
    resolve_day,
    resolve_range,
    sleep_on_local_date,
    update_slot,
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


NO_WEATHER_CONFIGURED = (
    "Weather is not configured yet — set WEATHER_HOME_LAT and "
    "WEATHER_HOME_LON to enable forecast caching (§14)."
)

NO_FORECAST_CACHED = (
    "No forecast cached yet — the 6-hourly refresh will fill the cache "
    "once coordinates are configured (§19)."
)


def format_forecast_day(row: dict) -> str:
    """One cached day → one Telegram line (metric units, Open-Meteo defaults)."""
    daily = row["payload"].get("daily") or {}
    desc = describe_weather_code(daily.get("weather_code"))
    detail = []
    if desc:
        detail.append(desc)
    if daily.get("temperature_2m_min") is not None or daily.get("temperature_2m_max") is not None:
        detail.append(
            f"{daily.get('temperature_2m_min', '—')}–{daily.get('temperature_2m_max', '—')}°C"
        )
    if daily.get("precipitation_sum") is not None:
        prob = daily.get("precipitation_probability_max")
        prob_part = f", {prob}%" if prob is not None else ""
        detail.append(f"{daily.get('precipitation_sum')}mm{prob_part}")
    if daily.get("wind_speed_10m_max") is not None:
        detail.append(f"wind {daily.get('wind_speed_10m_max')}km/h")
    return f"- {row['date'].isoformat()}: " + " · ".join(detail)


async def cmd_forecast(ctx, chat_id: int, user_id: int, arg: str = "") -> str:
    """§14: the cached forecast reaches the user while the dashboard is
    deferred — same data, same query layer as GET /weather/forecast.
    Optional `arg`: how many days to show (default: everything cached)."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.weather_home_lat == 0.0 and settings.weather_home_lon == 0.0:
        return NO_WEATHER_CONFIGURED

    days = 7
    if arg.strip().isdigit():
        days = max(1, min(16, int(arg.strip())))

    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        local_today = datetime.now(ZoneInfo(user.timezone)).date()
        rows = await get_forecast(
            session,
            lat=settings.weather_home_lat,
            lon=settings.weather_home_lon,
            days=days,
            today=local_today,
        )
    if not rows:
        return NO_FORECAST_CACHED

    header = (
        f"Forecast ({settings.weather_home_lat:.2f}, {settings.weather_home_lon:.2f})"
        f" — {user.timezone}"
    )
    lines = [header] + [format_forecast_day(r) for r in rows]
    return "\n".join(lines)


# ------------------------------------------------------------------ /gym ----

GYM_HELP = (
    "Gym schedule (Phase 10 v2):\n"
    "/gym — today's sessions\n"
    "/gym week — the 7-day schedule\n"
    "/gym list — recurring slots (with ids)\n"
    "/gym set Mon 18:00 Push Day — add a recurring slot\n"
    "/gym note <id> Bench 4x8 · Incline 3x10 — attach exercises\n"
    "/gym rm <id> — remove a slot\n"
    "Date-specific AI-planned sessions (confirmed plans) override the "
    "recurring template on their dates."
)

_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

GYM_SET_USAGE = "Usage: /gym set Mon 18:00 Push Day"


def _parse_weekday(token: str) -> int | None:
    return _WEEKDAYS.get(token.strip().lower())


def _format_session(entry: dict) -> str:
    bits = []
    if entry.get("start_time"):
        bits.append(entry["start_time"])
    if entry.get("target_duration_min"):
        bits.append(f"{entry['target_duration_min']} min")
    bits.append(entry["title"])
    origin = "plan" if entry["source"] == "plan" else "routine"
    line = f"- {' · '.join(bits)} ({origin})"
    if entry.get("description"):
        line += f"\n    {entry['description']}"
    return line


async def cmd_gym(ctx, chat_id: int, user_id: int, arg: str = "") -> str:
    """Phase 10 v2: the gym schedule in Telegram — read paths share the query
    layer with the watch endpoints; quick edits mean the routine can be
    maintained from a phone without any REST client."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    parts = arg.strip().split(None, 1)
    sub = (parts[0].lower() if parts else "") or "today"
    rest = parts[1] if len(parts) > 1 else ""

    async with ctx.sessionmaker() as session:
        user = await session.get(User, user_id)
        now = datetime.now(ZoneInfo(user.timezone))
        local_today = now.date()

        if sub in ("today", "tomorrow"):
            day = local_today if sub == "today" else local_today + timedelta(days=1)
            sessions = await resolve_day(session, user_id, day)
            if not sessions:
                return f"No sessions scheduled for {day.isoformat()} — rest day."
            lines = [f"Gym — {day.isoformat()} ({now.strftime('%a') if sub == 'today' else ''}):"]
            lines += [_format_session(e) for e in sessions]
            return "\n".join(lines).replace("  )", ")")

        if sub == "week":
            monday = local_today - timedelta(days=local_today.weekday())
            week = await resolve_range(session, user_id, monday, days=7)
            names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            lines = [f"Week of {monday.isoformat()}:"]
            for day_entry in week:
                if day_entry["sessions"]:
                    for entry in day_entry["sessions"]:
                        when = entry.get("start_time") or ""
                        lines.append(f"- {names[day_entry['weekday']]} {when} {entry['title']}".rstrip())
                else:
                    lines.append(f"- {names[day_entry['weekday']]} — rest")
            return "\n".join(lines)

        if sub == "list":
            slots = await list_slots(session, user_id)
            if not slots:
                return "No recurring slots yet.\n" + GYM_HELP
            names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            lines = ["Recurring weekly slots:"]
            for s in slots:
                flag = "" if s.active else " (paused)"
                lines.append(f"#{s.id} {names[s.weekday]} {s.start_time.strftime('%H:%M')} {s.title}{flag}")
                if s.description:
                    lines.append(f"    {s.description}")
            return "\n".join(lines)

        if sub == "set":
            tokens = rest.split(None, 2)
            if len(tokens) < 3:
                return GYM_SET_USAGE
            weekday = _parse_weekday(tokens[0])
            if weekday is None:
                return GYM_SET_USAGE
            time_token = tokens[1]
            try:
                hour, minute = time_token.split(":", 1)
                start = datetime.strptime(f"{int(hour):02d}:{int(minute):02d}", "%H:%M").time()
            except (ValueError, TypeError):
                return GYM_SET_USAGE
            title = tokens[2].strip()
            if not title or len(title) > 60:
                return "Title must be 1-60 characters."
            slot = await create_slot(session, user_id, weekday, start, title)
            await session.commit()
            names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            return (
                f"Added #{slot.id}: {names[weekday]} {start.strftime('%H:%M')} {title}\n"
                f"Attach exercises with /gym note {slot.id} <exercises>."
            )

        if sub == "note":
            tokens = rest.split(None, 1)
            if len(tokens) < 2 or not tokens[0].isdigit():
                return "Usage: /gym note <id> <exercises>"
            slot = await update_slot(session, user_id, int(tokens[0]), description=tokens[1].strip()[:2000])
            if slot is None:
                return "No such slot."
            await session.commit()
            return f"Updated #{slot.id} {slot.title}:\n    {slot.description}"

        if sub == "rm":
            if not rest.strip().isdigit():
                return "Usage: /gym rm <id>"
            if not await delete_slot(session, user_id, int(rest.strip())):
                return "No such slot."
            await session.commit()
            return "Removed."

        return GYM_HELP
