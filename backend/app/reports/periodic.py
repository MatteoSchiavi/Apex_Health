"""AI reports (MASTER_SPEC §9.2, §19).

Templated daily summaries (no LLM, $0.00) — see daily.py. This module adds
the scheduled WEEKLY and MONTHLY reports: always POWERFUL tier (§9.2
"scheduled generation is hardcoded, not classified"), one-shot completions
over a data pack built with the §8.2 query functions. Every query call is
audited to agent_tool_calls with session_id=NULL (§6.4: "not a
chat-originated call"); the completion logs its token_usage row (§8.6).

Cadence (§19): weekly Monday 06:00, monthly 1st of month 06:00 — user-local
via the hourly-dispatch pattern (§17: user-local day boundaries). "Batch API
where supported" is a judgment call: at this volume (≤8 calls/month) the
standard completions path is used; the tier and cost accounting are
identical. Rows are idempotent per (user, report_type, period_start) —
a re-run refreshes instead of duplicating (§17).
"""

import json
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.llm import LLMClient, jsonable
from app.models.ai import AgentToolCall, AiReport
from app.models.user import User
from app.queries import (
    gear_overview,
    get_activity_summary,
    get_donation_status,
    get_journal_entries,
    get_metric_trend,
)
from app.queries.usage import log_llm_usage

logger = logging.getLogger("app.reports.periodic")

REPORT_SYSTEM_PROMPT = (
    "You write the athlete's periodic training/health report. Use ONLY the "
    "data provided; never invent numbers. Be concrete and specific: cite the "
    "actual values, compare against the healthy bands (readiness/recovery "
    "0-100, ACWR 0.8-1.3 with >1.5 = injury risk), call out trends, and end "
    "with 2-4 actionable recommendations. Markdown, concise sections."
)


@dataclass
class PeriodDataPack:
    payload: dict
    source_feature_ids: list


async def build_period_data_pack(session, user_id: int, start: date, end: date) -> PeriodDataPack:
    """Data pack via the §8.2 query functions, each call audited to
    agent_tool_calls (session_id NULL)."""
    payload: dict = {"period": {"start": start.isoformat(), "end": end.isoformat()}}
    source_ids: list[str] = []

    async def _track(tool_name: str, input_json: dict, result: object) -> object:
        session.add(
            AgentToolCall(
                session_id=None,  # §6.4: not a chat-originated call
                tool_name=tool_name,
                input_json=input_json,
                output_json=jsonable(result),
                error=None,
                latency_ms=None,
            )
        )
        return result

    metrics = {}
    for metric in ("readiness", "recovery", "acwr", "strain", "hrv_deviation_pct"):
        trend = await get_metric_trend(session, user_id, metric, start, end)
        metrics[metric] = trend
        source_ids.extend(f"{metric}@{row['date']}" for row in trend)
    await _track(
        "get_metric_trend",
        {"metric": list(metrics), "start_date": start.isoformat(), "end_date": end.isoformat()},
        metrics,
    )
    payload["metric_trends"] = metrics

    activities = await _track(
        "get_activity_summary",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        await get_activity_summary(session, user_id, start, end),
    )
    payload["activities"] = activities

    journal = await _track(
        "get_journal_entries",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        await get_journal_entries(session, user_id, start, end),
    )
    payload["journal"] = journal

    gear = await _track("get_gear_status", {}, await gear_overview(session, user_id))
    payload["gear"] = gear

    donation = await _track(
        "get_donation_status", {}, await get_donation_status(session, user_id, end)
    )
    payload["donation"] = donation

    return PeriodDataPack(payload=payload, source_feature_ids=source_ids)


async def upsert_periodic_report(
    sessionmaker: async_sessionmaker,
    llm: LLMClient,
    user: User,
    report_type: str,
    start: date,
    end: date,
) -> AiReport | None:
    """Generate (or refresh) the weekly/monthly ai_reports row: data pack →
    one powerful-tier completion → persist → push to linked chats. None when
    the period has no data at all."""
    if report_type not in ("weekly", "monthly"):
        raise ValueError(f"unsupported report_type {report_type!r}")

    async with sessionmaker() as session:
        existing = (
            await session.scalars(
                select(AiReport).where(
                    AiReport.user_id == user.id,
                    AiReport.report_type == report_type,
                    AiReport.period_start == start,
                )
            )
        ).first()
        if existing is not None:  # §17 idempotency — already generated
            return existing
        pack = await build_period_data_pack(session, user.id, start, end)
        await session.commit()

    if pack.payload["activities"]["total_sessions"] == 0 and pack.payload["metric_trends"][
        "readiness"
    ] == [] and pack.payload["journal"]["entries"] == []:
        logger.info("no data for %s report %s..%s — skipped", report_type, start, end)
        return None

    response = await llm.complete(
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write the {report_type} report for {start.isoformat()} — "
                    f"{end.isoformat()}.\n\nData pack (JSON):\n"
                    f"{json.dumps(pack.payload, ensure_ascii=False, default=str)}"
                ),
            }
        ],
        system=REPORT_SYSTEM_PROMPT,
        # §9.2: scheduled reports are ALWAYS powerful — never classified.
        tier="powerful",
    )

    async with sessionmaker() as session:
        row = (
            await session.scalars(
                select(AiReport).where(
                    AiReport.user_id == user.id,
                    AiReport.report_type == report_type,
                    AiReport.period_start == start,
                )
            )
        ).first()
        if row is None:
            row = AiReport(
                user_id=user.id, report_type=report_type, period_start=start, period_end=end
            )
            session.add(row)
        row.content_md = response.content or ""
        row.model_used = response.model
        row.source_feature_ids = pack.source_feature_ids
        await log_llm_usage(
            session,
            user_id=user.id,
            call_type=f"{report_type}_report",
            tier="powerful",
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cached_tokens=response.cached_tokens,
        )
        await session.commit()
        logger.info(
            "%s report persisted for user %s (%s..%s)", report_type, user.id, start, end
        )
        return row
