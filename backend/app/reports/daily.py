"""Templated daily summaries (MASTER_SPEC §9.2, §19).

Daily summaries are TEMPLATED — no LLM call, $0.00 (§9.2 "daily summaries
are templated (no LLM call)"). The same builder feeds both the scheduled
ai_reports 'daily' row and any chat-side rendering, so the daily summary has
exactly one implementation (§8.2). `model_used` stays NULL on templated rows
(§6.4).

Cadence: §19 does not schedule the daily summary explicitly (the table
lists the weekly/monthly AI reports); judgment call — it runs at :45 inside
each user's 03:00-03:59 local window, after the feature engine (:00) and
gear accumulation (:15), so it summarizes freshly computed data.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.ai import AiReport
from app.models.features import DailyFeature
from app.models.user import User
from app.queries import (
    activities_on_local_date,
    gear_overview,
    open_alerts,
    sleep_on_local_date,
)

logger = logging.getLogger("app.reports.daily")


@dataclass
class DailySummary:
    feature_date: date
    content_md: str
    source_feature_ids: list[str] = field(default_factory=list)


def _fmt(value, digits: int = 0) -> str:
    return f"{value:.{digits}f}" if value is not None else "–"


def _fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "–"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


async def build_daily_summary(session, user: User, day: date) -> DailySummary | None:
    """One implementation of the templated daily summary (§8.2): features,
    sleep, activities, open alerts, service-due gear — as Markdown."""
    feature = (
        await session.scalars(
            select(DailyFeature).where(
                DailyFeature.user_id == user.id, DailyFeature.date == day
            )
        )
    ).first()
    if feature is None:
        return None

    activities = await activities_on_local_date(session, user.id, day)
    sleep = await sleep_on_local_date(session, user.id, day)

    tz = ZoneInfo(user.timezone)
    lines = [f"# Daily report — {day} ({tz.key})", ""]
    lines.append(
        f"- Readiness {_fmt(feature.readiness_score)} · "
        f"Recovery {_fmt(feature.recovery_score)} · "
        f"Strain {_fmt(feature.strain_score, 1)}"
    )
    lines.append(
        f"- ACWR {_fmt(feature.acwr, 2)} "
        f"(acute {_fmt(feature.training_load_acute)} · "
        f"chronic {_fmt(feature.training_load_chronic)})"
    )
    if sleep:
        sleep_line = f"- Sleep {_fmt_duration(sleep['total_sleep_s'])}"
        if sleep["sleep_score"] is not None:
            sleep_line += f" · score {_fmt(sleep['sleep_score'])}"
        lines.append(sleep_line)
    if feature.hrv_deviation_from_baseline is not None:
        lines.append(f"- HRV {_fmt(feature.hrv_deviation_from_baseline, 1)}% vs baseline")
    if activities:
        parts = []
        for a in activities:
            part = f"{a['discipline']} {_fmt_duration(a['duration_s'])}"
            if a["distance_m"]:
                part += f" ({a['distance_m'] / 1000:.1f} km)"
            parts.append(part)
        lines.append("- Training: " + " · ".join(parts))
    else:
        lines.append("- Training: none on this day.")

    alerts = await open_alerts(session, user.id)
    if alerts:
        lines.append("")
        lines.append("## Open alerts")
        for a in alerts:
            lines.append(f"- [{a.type}] {a.message}")

    gear = await gear_overview(session, user.id)
    due = [g for g in gear if (g["usage_pct"] or 0) >= 100]
    if due:
        lines.append("")
        lines.append("## Gear service due")
        for g in due:
            lines.append(f"- {g['name']} ({g['gear_type']})")

    # §6.4 audit list: metric-name/date identifiers actually used
    source_ids = [
        f"{metric}@{day.isoformat()}"
        for metric in (
            "readiness",
            "recovery",
            "strain",
            "acwr",
            "training_load_acute",
            "training_load_chronic",
            "sleep_architecture",
            "hrv_deviation_pct",
        )
    ]
    return DailySummary(
        feature_date=day,
        content_md="\n".join(lines).strip(),
        source_feature_ids=source_ids,
    )


async def upsert_daily_report(
    sessionmaker: async_sessionmaker, user: User, day: date
) -> AiReport:
    """Persist the templated summary as an ai_reports row (§17 idempotent
    upsert on (user, report_type, period_start) — a re-run refreshes the
    row instead of duplicating it)."""
    async with sessionmaker() as session:
        summary = await build_daily_summary(session, user, day)
        if summary is None:
            raise ValueError(f"no daily features for user {user.id} on {day}")
        row = (
            await session.scalars(
                select(AiReport).where(
                    AiReport.user_id == user.id,
                    AiReport.report_type == "daily",
                    AiReport.period_start == day,
                )
            )
        ).first()
        if row is None:
            row = AiReport(user_id=user.id, report_type="daily", period_start=day, period_end=day)
            session.add(row)
        row.content_md = summary.content_md
        row.model_used = None  # templated — §6.4
        row.source_feature_ids = summary.source_feature_ids
        await session.commit()
        logger.info("daily report persisted for user %s day %s", user.id, day)
        return row
