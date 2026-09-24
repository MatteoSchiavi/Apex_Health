"""Tool registry (MASTER_SPEC §8.3).

Every tool is a thin wrapper over a function in app/queries/ — the same
functions the scheduled report tasks (§19) and the Telegram bot call
directly, so "get my ACWR trend" has exactly one implementation (§8.2).

Write tools (§8.5) never commit directly: propose_* drafts a row and
returns it; confirmation happens via Telegram inline buttons. Tool errors
(surface as exceptions) are converted to tool RESULTS by the agent loop
(§8.4) — they never kill it.

W-01 audit: ``get_raw_biometrics`` exposes raw device values (HRV, RHR,
SpO2, respiration, weight) so the Anomaly Explainer role can answer
"why did my HRV tank?" without round-trips.

A-06 audit: ``confirm_draft`` mirrors the Telegram inline-button path so
web users can confirm training-plan and supplement drafts from the SPA.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import TrainingPlan
from app.models.gym_detail import GymDayPlan
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.queries.gym_detail import PlanNotFoundError, session_view
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
from app.queries.search import search_context
from app.queries.snapshot import gear_overview


@dataclass
class ToolContext:
    """Per-turn dependencies handed to every handler: the caller's session,
    user scope, today-in-user-tz, and optional services (embeddings)."""

    session: AsyncSession
    user_id: int
    today: date
    embedding_client: Any | None = None  # EmbeddingClient — wired by the bot ctx


@dataclass
class ToolSpec:
    name: str
    kind: str  # 'read' | 'write'
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


def _date(value: str | None, *, field_name: str, required: bool = True) -> date | None:
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required (YYYY-MM-DD)")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value!r}") from exc


def _date_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    start = _date(start_date, field_name="start_date")
    end = _date(end_date, field_name="end_date")
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    return start, end


# --- read tools -------------------------------------------------------------


async def _get_metric_trend(
    ctx: ToolContext,
    metric: str,
    start_date: str,
    end_date: str,
    discipline_id: int | None = None,
) -> dict:
    start, end = _date_range(start_date, end_date)
    rows = await get_metric_trend(
        ctx.session, ctx.user_id, metric, start, end, discipline_id=discipline_id
    )
    return {"metric": metric, "rows": rows}


async def _get_lab_trend(
    ctx: ToolContext, marker: str, start_date: str | None = None, end_date: str | None = None
) -> dict:
    start = _date(start_date, field_name="start_date", required=False)
    end = _date(end_date, field_name="end_date", required=False)
    rows = await get_lab_trend(ctx.session, ctx.user_id, marker, start_date=start, end_date=end)
    return {"marker": marker, "rows": rows}


async def _get_activity_summary(
    ctx: ToolContext, start_date: str, end_date: str, discipline_id: int | None = None
) -> dict:
    start, end = _date_range(start_date, end_date)
    return await get_activity_summary(
        ctx.session, ctx.user_id, start, end, discipline_id=discipline_id
    )


async def _get_journal_entries(
    ctx: ToolContext, start_date: str, end_date: str, tags: list[str] | None = None
) -> dict:
    start, end = _date_range(start_date, end_date)
    rows = await get_journal_entries(ctx.session, ctx.user_id, start, end, tags=tags)
    return {"entries": rows, "count": len(rows)}


async def _search_context(ctx: ToolContext, query: str, top_k: int = 5) -> dict:
    if ctx.embedding_client is None:
        # §8.4: degrade as a readable result, not a crash — the harness is
        # usable before the embedding key is configured.
        return {"error": "semantic search unavailable: embeddings client not configured"}
    result = await ctx.embedding_client.embed([query])
    hits = await search_context(ctx.session, ctx.user_id, result.vectors[0], top_k=top_k)
    return {"query": query, "hits": hits}


async def _get_training_plan(ctx: ToolContext, status: str | None = None) -> dict:
    plan = await get_training_plan(ctx.session, ctx.user_id, status=status)
    return {"plan": plan}


async def _get_donation_status(ctx: ToolContext) -> dict:
    status = await get_donation_status(ctx.session, ctx.user_id, ctx.today)
    return {"donation_status": status}


async def _get_gear_status(ctx: ToolContext, gear_id: int | None = None) -> dict:
    items = await gear_overview(ctx.session, ctx.user_id, gear_id=gear_id)
    return {"items": items}


async def _get_raw_biometrics(
    ctx: ToolContext,
    start_date: str,
    end_date: str,
    fields: list[str] | None = None,
) -> dict:
    """W-01 audit: raw device values for the Anomaly Explainer role.

    Returns daily_biometrics rows (resting_hr, spo2_avg, weight_kg,
    body_fat_pct, vo2max, steps) and hrv_readings (overnight_avg + 5min)
    over the requested range. ``fields=None`` returns all; otherwise
    filters to the named fields. NULL values are preserved verbatim —
    the model needs to see "not measured" honestly, not zero-invented.
    """
    start, end = _date_range(start_date, end_date)
    # Cap the range to prevent unbounded scans (D-02 audit pattern).
    if (end - start).days > 90:
        raise ValueError(
            "raw_biometrics range capped at 90 days — narrow the window for "
            "anomaly explanation"
        )

    allowed_fields = {
        "resting_hr", "spo2_avg", "weight_kg", "body_fat_pct", "vo2max",
        "steps", "floors", "hydration_ml", "hrv_ms", "hrv_reading_type",
    }
    if fields is not None:
        invalid = set(fields) - allowed_fields
        if invalid:
            raise ValueError(
                f"unknown fields {sorted(invalid)} (allowed: {sorted(allowed_fields)})"
            )

    bio_rows = (
        await ctx.session.scalars(
            select(DailyBiometric)
            .where(
                DailyBiometric.user_id == ctx.user_id,
                DailyBiometric.date >= start,
                DailyBiometric.date <= end,
            )
            .order_by(DailyBiometric.date)
        )
    ).all()

    from datetime import datetime as _dt, time as _time
    from zoneinfo import ZoneInfo
    user = await ctx.session.get(User, ctx.user_id)
    tz = ZoneInfo(user.timezone) if user else ZoneInfo("UTC")
    start_dt = _dt.combine(start, _time.min, tzinfo=tz)
    end_dt = _dt.combine(end + timedelta(days=1), _time.min, tzinfo=tz)

    hrv_rows = (
        await ctx.session.scalars(
            select(HrvReading)
            .where(
                HrvReading.user_id == ctx.user_id,
                HrvReading.timestamp >= start_dt.astimezone(),
                HrvReading.timestamp < end_dt.astimezone(),
            )
            .order_by(HrvReading.timestamp)
        )
    ).all()

    def _pick(d: dict, keys: set[str] | None) -> dict:
        if keys is None:
            return d
        return {k: v for k, v in d.items() if k in keys}

    bio_out = []
    for b in bio_rows:
        row = {
            "date": b.date.isoformat(),
            "resting_hr": b.resting_hr,
            "spo2_avg": float(b.spo2_avg) if b.spo2_avg is not None else None,
            "weight_kg": float(b.weight_kg) if b.weight_kg is not None else None,
            "body_fat_pct": float(b.body_fat_pct) if b.body_fat_pct is not None else None,
            "vo2max": float(b.vo2max) if b.vo2max is not None else None,
            "steps": b.steps,
            "floors": b.floors,
            "hydration_ml": b.hydration_ml,
        }
        bio_out.append(_pick(row, set(fields) if fields else None))

    hrv_out = []
    hrv_field_set = set(fields) if fields and {"hrv_ms", "hrv_reading_type"} & set(fields) else None
    if hrv_field_set is not None or fields is None:
        for h in hrv_rows:
            row = {
                "timestamp": h.timestamp.isoformat(),
                "hrv_ms": float(h.hrv_ms) if h.hrv_ms is not None else None,
                "hrv_reading_type": h.reading_type,
                "date": h.timestamp.astimezone(tz).date().isoformat(),
            }
            hrv_out.append(_pick(row, hrv_field_set))

    return {
        "rows": bio_out,
        "hrv_readings": hrv_out,
        "note": "raw device values; null = not measured (never invented)",
    }


async def _confirm_draft(
    ctx: ToolContext,
    draft_type: str,
    draft_id: int,
    action: str = "confirm",
) -> dict:
    """A-06 audit: web draft-confirmation mirror of the Telegram inline-button path.

    ``draft_type`` is "training_plan" or "supplement". ``action`` is
    "confirm" or "reject". The underlying confirm/reject functions in
    app.queries.plans are the SAME ones the Telegram callback path uses —
    one implementation, two surfaces (§8.2 law).
    """
    if draft_type not in ("training_plan", "supplement"):
        return {"error": "draft_type must be 'training_plan' or 'supplement'"}
    if action not in ("confirm", "reject"):
        return {"error": "action must be 'confirm' or 'reject'"}
    try:
        if draft_type == "training_plan":
            if action == "confirm":
                result = await confirm_plan_draft(ctx.session, ctx.user_id, draft_id)
            else:
                result = await reject_plan_draft(ctx.session, ctx.user_id, draft_id)
        else:
            if action == "confirm":
                result = await confirm_supplement_draft(ctx.session, ctx.user_id, draft_id)
            else:
                result = await reject_supplement_draft(ctx.session, ctx.user_id, draft_id)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"status": action, "draft_type": draft_type, "draft_id": draft_id, "result": result}


async def _get_score_components(ctx: ToolContext, date: str | None = None) -> dict:
    """W-01 audit: decompose the latest DailyFeature into its component
    contributions so the Anomaly Explainer can answer "why is recovery low?"
    without the model guessing at causality."""
    from app.models.features import DailyFeature
    day = _date(date, field_name="date", required=False) or ctx.today
    row = await ctx.session.get(DailyFeature, {"user_id": ctx.user_id, "date": day})
    if row is None:
        return {"date": day.isoformat(), "components": None, "note": "no feature row for this date"}
    return {
        "date": day.isoformat(),
        "components": {
            "recovery_score": float(row.recovery_score) if row.recovery_score is not None else None,
            "readiness_score": float(row.readiness_score) if row.readiness_score is not None else None,
            "strain_score": float(row.strain_score) if row.strain_score is not None else None,
            "acwr": float(row.acwr) if row.acwr is not None else None,
            "hrv_deviation_pct": float(row.hrv_deviation_from_baseline) if row.hrv_deviation_from_baseline is not None else None,
            "illness_risk_score": float(row.illness_risk_score) if row.illness_risk_score is not None else None,
            "injury_risk_score": float(row.injury_risk_score) if row.injury_risk_score is not None else None,
            "sleep_architecture_score": float(row.sleep_architecture_score) if row.sleep_architecture_score is not None else None,
            "data_completeness": row.data_completeness,
        },
    }


async def _get_integration_health(ctx: ToolContext) -> dict:
    """W-05 audit: integration health with failure streaks + last_synced_at
    so the Data-Health Steward can accurately answer "is my data synced?"."""
    from app.models.integration import Integration
    rows = (
        await ctx.session.scalars(
            select(Integration)
            .where(Integration.user_id == ctx.user_id)
            .order_by(Integration.provider)
        )
    ).all()
    return {
        "integrations": [
            {
                "provider": i.provider,
                "status": i.status,
                "consecutive_failures": i.consecutive_failures,
                "last_synced_at": i.last_synced_at.isoformat() if i.last_synced_at else None,
            }
            for i in rows
        ]
    }


# --- write tools (§8.5: draft only, confirm via Telegram) --------------------


async def _propose_training_plan(
    ctx: ToolContext, week_start: str, sessions: list[dict]
) -> dict:
    if not sessions:
        raise ValueError("sessions must be a non-empty list")
    week = _date(week_start, field_name="week_start")
    # Session dates must parse up front — one bad row aborts the whole draft.
    normalized = []
    for spec in sessions:
        day = _date(spec.get("date"), field_name="sessions[].date")
        normalized.append({**spec, "date": day})
    # Discipline slugs → ids (§6.4 seed names, e.g. 'road_cycling').
    resolved: dict[int, int] = {}
    for index, spec in enumerate(normalized):
        slug = spec.get("discipline")
        if slug is not None:
            discipline_id = await discipline_id_by_slug(ctx.session, slug)
            if discipline_id is None:
                raise ValueError(f"unknown discipline slug {slug!r}")
            resolved[index] = discipline_id
    draft = await create_plan_draft(
        ctx.session, ctx.user_id, week, normalized, discipline_ids=resolved
    )
    return {
        **draft,
        "note": "Draft created — awaiting confirmation via Telegram inline buttons (§8.5).",
    }


async def _propose_supplement_change(
    ctx: ToolContext,
    supplement_name: str,
    dose: str | None = None,
    schedule_cron: str | None = None,
    reason: str | None = None,
) -> dict:
    draft = await create_supplement_draft(
        ctx.session, ctx.user_id, supplement_name, dose, schedule_cron, reason
    )
    return {
        **draft,
        "note": "Draft created — awaiting confirmation via Telegram inline buttons (§8.5).",
    }


async def _sync_plan_to_technogym(ctx: ToolContext, training_plan_id: int) -> dict:
    """§8.3/§11: only a CONFIRMED plan can sync — and prescription-push itself
    is stage 11b, contingent on the real Technogym access tier (§24 open
    item). Until that lands the tool validates the precondition and returns
    the documented fallback ('/plan today', followed manually)."""
    row = await ctx.session.get(TrainingPlan, training_plan_id)
    if row is None or row.user_id != ctx.user_id:
        return {"error": "plan not found for this account"}
    if row.status == "draft":
        return {"error": "plan is still a draft — confirm it first (§8.5)"}
    return {
        "status": "pending_technogym_access",
        "plan_id": training_plan_id,
        "fallback": "Prescription-push (§11b) awaits Technogym access confirmation; "
        "use '/plan today' in Telegram and follow it manually.",
    }


# --- coach tools (owner feature batch, 2026-09) ------------------------------


async def _get_upcoming_events(ctx: ToolContext, horizon_days: int = 14) -> dict:
    """The user's calendar for the next N days — the base of every
    'am I ready for X / what should I train' conversation."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.models.coach import UserEvent

    horizon = min(max(int(horizon_days), 1), 60)
    now_start = datetime.combine(ctx.today, datetime.min.time())
    rows = (
        (
            await ctx.session.scalars(
                select(UserEvent)
                .where(
                    UserEvent.user_id == ctx.user_id,
                    UserEvent.starts_at >= now_start,
                    UserEvent.starts_at
                    < now_start + timedelta(days=horizon),
                )
                .order_by(UserEvent.starts_at)
            )
        )
        .all()
    )
    return {
        "events": [
            {
                "title": e.title,
                "kind": e.kind,
                "date": e.starts_at.date().isoformat(),
                "priority": e.priority,
                "taper_days": e.taper_days,
                "notes": e.notes,
            }
            for e in rows
        ]
    }


async def _update_context_doc(ctx: ToolContext, doc_kind: str, content: str) -> dict:
    """Direct write (NOT a draft): the context docs are the user's own notes
    — the agent keeping them current is bookkeeping, not a health decision
    (§8.5's draft law targets plans/protocols). updated_by records the
    authorship so the user can always tell what the agent changed."""
    from sqlalchemy import select

    from app.models.coach import UserContextDoc

    allowed = ("profile", "goals", "injuries", "equipment", "preferences", "season_plan")
    if doc_kind not in allowed:
        return {"error": f"doc_kind must be one of {', '.join(allowed)}"}
    if not content.strip():
        return {"error": "content must not be empty"}
    doc = await ctx.session.scalar(
        select(UserContextDoc).where(
            UserContextDoc.user_id == ctx.user_id,
            UserContextDoc.doc_kind == doc_kind,
        )
    )
    if doc is None:
        doc = UserContextDoc(user_id=ctx.user_id, doc_kind=doc_kind, content=content)
        ctx.session.add(doc)
    else:
        doc.content = content
    doc.updated_by = "ai"
    await ctx.session.flush()
    return {
        "status": "updated",
        "doc_kind": doc_kind,
        "chars": len(content),
        "note": "Context document updated (updated_by=ai).",
    }


async def _get_gym_day(ctx: ToolContext, date: str | None = None) -> dict:
    """The concrete gym day plan (exercises, sets/reps/rest, progress) —
    today unless a date is given."""
    day = _date(date, field_name="date", required=False)
    if day is None:
        day = ctx.today
    plan_id_row = await ctx.session.scalar(
        select(GymDayPlan.id).where(
            GymDayPlan.user_id == ctx.user_id, GymDayPlan.date == day
        )
    )
    if plan_id_row is None:
        return {
            "date": day.isoformat(),
            "plan": None,
            "note": "no concrete plan for this date — the recurring template "
            "applies; generate one via POST /gym/plan/{date}/generate",
        }
    try:
        view = await session_view(ctx.session, ctx.user_id, plan_id_row)
    except PlanNotFoundError:  # pragma: no cover - id from same table
        return {"date": day.isoformat(), "plan": None}
    return {"date": day.isoformat(), "plan": view}


# --- registry ----------------------------------------------------------------


def _schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="get_metric_trend",
            kind="read",
            description="Daily trend of one health/performance metric "
            "(readiness, recovery, strain, acwr, acute_load, chronic_load, "
            "sleep_architecture, hrv_deviation_pct, illness_risk, injury_risk, "
            "cross_discipline_fatigue, iron_status_flag) over a date range; "
            "discipline-scoped metrics (estimated_ftp, aerobic_decoupling_pct, "
            "efficiency_factor) need discipline_id.",
            parameters=_schema(
                {
                    "metric": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "discipline_id": {"type": "integer"},
                },
                ["metric", "start_date", "end_date"],
            ),
            handler=_get_metric_trend,
        ),
        ToolSpec(
            name="get_lab_trend",
            kind="read",
            description="Lab marker series across blood panels (e.g. ferritin, hemoglobin).",
            parameters=_schema(
                {
                    "marker": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                ["marker"],
            ),
            handler=_get_lab_trend,
        ),
        ToolSpec(
            name="get_activity_summary",
            kind="read",
            description="Aggregated activities (sessions, duration, distance, training load) "
            "over a date range, with a per-discipline breakdown.",
            parameters=_schema(
                {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "discipline_id": {"type": "integer"},
                },
                ["start_date", "end_date"],
            ),
            handler=_get_activity_summary,
        ),
        ToolSpec(
            name="get_journal_entries",
            kind="read",
            description="The athlete's journal entries over a date range, optionally filtered by tags.",
            parameters=_schema(
                {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                ["start_date", "end_date"],
            ),
            handler=_get_journal_entries,
        ),
        ToolSpec(
            name="search_context",
            kind="read",
            description="Semantic search over the athlete's journal entries and AI reports "
            "(pgvector cosine). Use for fuzzy/recall questions.",
            parameters=_schema(
                {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                ["query"],
            ),
            handler=_search_context,
        ),
        ToolSpec(
            name="get_training_plan",
            kind="read",
            description="Current/active training plan with its planned sessions; "
            "optionally filter by status (draft|confirmed|active|completed).",
            parameters=_schema({"status": {"type": "string"}}, []),
            handler=_get_training_plan,
        ),
        ToolSpec(
            name="get_donation_status",
            kind="read",
            description="Blood donation status: last donation, days since, next eligible date.",
            parameters=_schema({}, []),
            handler=_get_donation_status,
        ),
        ToolSpec(
            name="get_gear_status",
            kind="read",
            description="Gear usage vs service interval; optionally one item via gear_id.",
            parameters=_schema({"gear_id": {"type": "integer"}}, []),
            handler=_get_gear_status,
        ),
        ToolSpec(
            name="propose_training_plan",
            kind="write",
            description="DRAFT a weekly training plan (never applies directly — the user "
            "confirms via Telegram). Each session: {date, discipline? (slug), session_type?, "
            "target_duration_min?, target_load?, description?}.",
            parameters=_schema(
                {
                    "week_start": {"type": "string", "description": "YYYY-MM-DD (snapped to its Monday)"},
                    "sessions": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                ["week_start", "sessions"],
            ),
            handler=_propose_training_plan,
        ),
        ToolSpec(
            name="propose_supplement_change",
            kind="write",
            description="DRAFT a supplement protocol change (never applies directly — the user "
            "confirms via Telegram).",
            parameters=_schema(
                {
                    "supplement_name": {"type": "string"},
                    "dose": {"type": "string"},
                    "schedule_cron": {"type": "string"},
                    "reason": {"type": "string"},
                },
                ["supplement_name"],
            ),
            handler=_propose_supplement_change,
        ),
        ToolSpec(
            name="sync_plan_to_technogym",
            kind="write",
            description="Push a CONFIRMED plan to Technogym as a prescribed program "
            "(contingent on Technogym access — §11b).",
            parameters=_schema({"training_plan_id": {"type": "integer"}}, ["training_plan_id"]),
            handler=_sync_plan_to_technogym,
        ),
        ToolSpec(
            name="get_upcoming_events",
            kind="read",
            description="The user's calendar events (races, trips, ski weeks, "
            "competitions) for the next N days — the context behind training "
            "tailoring and tapering.",
            parameters=_schema(
                {"horizon_days": {"type": "integer", "description": "default 14, max 60"}},
                [],
            ),
            handler=_get_upcoming_events,
        ),
        ToolSpec(
            name="update_context_doc",
            kind="write",
            description="Create/update one of the user's context documents "
            "(profile, goals, injuries, equipment, preferences, season_plan) "
            "in compact markdown. Use when the user states durable facts "
            "(goals, injuries, equipment, season plans).",
            parameters=_schema(
                {
                    "doc_kind": {"type": "string", "enum": ["profile", "goals", "injuries", "equipment", "preferences", "season_plan"]},
                    "content": {"type": "string"},
                },
                ["doc_kind", "content"],
            ),
            handler=_update_context_doc,
        ),
        ToolSpec(
            name="get_gym_day",
            kind="read",
            description="The concrete gym day plan for a date (default today): "
            "exercises with sets/reps/rest and completion progress.",
            parameters=_schema(
                {"date": {"type": "string", "description": "YYYY-MM-DD, default today"}},
                [],
            ),
            handler=_get_gym_day,
        ),
        ToolSpec(
            name="get_raw_biometrics",
            kind="read",
            description="W-01: raw device values (resting_hr, spo2_avg, weight_kg, "
            "body_fat_pct, vo2max, steps, hrv_ms + reading_type) over a date range. "
            "Use for anomaly explanation ('why did my HRV tank?'). NULL = not "
            "measured (never invented). Range capped at 90 days.",
            parameters=_schema(
                {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional field filter (resting_hr, spo2_avg, weight_kg, "
                        "body_fat_pct, vo2max, steps, floors, hydration_ml, hrv_ms, hrv_reading_type)",
                    },
                },
                ["start_date", "end_date"],
            ),
            handler=_get_raw_biometrics,
        ),
        ToolSpec(
            name="get_score_components",
            kind="read",
            description="W-01: decompose one day's DailyFeature into its component "
            "contributions (recovery, readiness, strain, ACWR, hrv_deviation_pct, "
            "illness_risk, injury_risk, sleep_architecture, data_completeness) so "
            "the model can explain 'why is recovery low?' without guessing.",
            parameters=_schema(
                {"date": {"type": "string", "description": "YYYY-MM-DD, default today"}},
                [],
            ),
            handler=_get_score_components,
        ),
        ToolSpec(
            name="get_integration_health",
            kind="read",
            description="W-05: integration status with consecutive_failures and "
            "last_synced_at so the model can accurately answer 'is my data synced?' "
            "instead of reporting 'connected' while sync has failed.",
            parameters=_schema({}, []),
            handler=_get_integration_health,
        ),
        ToolSpec(
            name="confirm_draft",
            kind="write",
            description="A-06: confirm or reject a training_plan or supplement draft "
            "from the web UI (mirrors the Telegram inline-button path). action=confirm "
            "applies the draft; action=reject discards it.",
            parameters=_schema(
                {
                    "draft_type": {"type": "string", "enum": ["training_plan", "supplement"]},
                    "draft_id": {"type": "integer"},
                    "action": {"type": "string", "enum": ["confirm", "reject"]},
                },
                ["draft_type", "draft_id"],
            ),
            handler=_confirm_draft,
        ),
    ]
}


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI-compatible tools payload for the LLM request (§8.4)."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in TOOL_REGISTRY.values()
    ]


WRITE_TOOLS = frozenset(spec.name for spec in TOOL_REGISTRY.values() if spec.kind == "write")
