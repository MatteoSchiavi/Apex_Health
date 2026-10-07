"""Adaptive gym advisor (owner feature batch: context-aware training).

The engine answers two owner requirements:

1. EVENT TAPER — "If I have ski training on Saturday, I will not train my
   legs on Friday or Thursday to get there with fresh legs." High-priority
   leg-heavy events (race, run, ride, ski, enduro) inside the event's
   taper window cut leg volume: high-impact plyometrics are dropped,
   sets are halved (floor 2), heavy squat/hinge patterns swap to
   mobility-friendly core work.

2. FEEDBACK — "If I go skiing and I have a little ache on my knee, maybe I
   will go easy on my knees with other leg exercises." Soreness areas map
   to movement patterns to avoid: knees -> plyo/lunge, lower_back ->
   heavy hinge, shoulders -> overhead pressing...; an injury flag drops
   the affected muscle group for the day and says so.

Deterministic and explainable by design: every adjustment appends a
human-readable note that the UI/watch/agent surfaces verbatim. The AI
harness layers richer tailoring ON TOP of this baseline (it receives the
same events + feedback + context docs), but the guardrails here hold even
when no LLM is configured.
"""

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.gym_detail import GymDayPlan, GymDayExercise, GymExercise
from app.queries.gym import resolve_day
from app.services.safety_interlock import (
    VetoDecision,
    exertion_veto,
    impact_allowed_by_ceiling,
)

logger = logging.getLogger("services.gym_advisor")

# Event kinds whose performance depends on fresh legs.
LEG_HEAVY_KINDS = {"race", "run", "ride", "ski", "enduro", "competition"}

# soreness area -> movement patterns to keep light/avoid
_SORENESS_PATTERN_MAP = {
    "knees": {"plyo", "lunge", "squat"},
    "knee": {"plyo", "lunge", "squat"},
    "lower_back": {"hinge", "hinge_explosive"},
    "back": {"hinge", "hinge_explosive"},
    "shoulders": {"push_v", "pull_v"},
    "shoulder": {"push_v", "pull_v"},
    "ankles": {"plyo"},
    "ankle": {"plyo"},
    "hamstrings": {"hinge", "sprint"},
    "hip_flexors": {"lunge"},
    "hips": {"lunge"},
    "elbows": {"push_h", "pull_v"},
    "wrists": {"push_h", "push_v"},
}

# muscle groups implicated by a soreness area (injury flag drops these)
_SORENESS_GROUP_MAP = {
    "knees": {"legs"},
    "knee": {"legs"},
    "lower_back": {"legs", "core"},
    "back": {"legs", "core"},
}

# Default weekly split used when generating a day plan from the catalog
# (gym_general week: push / legs / pull / full body / core-heavy).
DEFAULT_WEEK_SPLIT = {
    0: ("push", ["push", "core"]),
    1: ("legs", ["legs", "core"]),
    2: ("pull", ["pull", "core"]),
    3: ("full_body", ["full_body", "core"]),
    4: ("legs", ["legs", "core"]),
    5: ("upper", ["push", "pull"]),
    6: ("full_body", ["full_body", "core"]),
}

_REP_TARGETS = {
    "plyo": (5, 8),
    "hinge_explosive": (8, 12),
    "full_body_explosive": (8, 12),
    "core_anti": (30, 60),  # seconds-as-reps convention for holds
    "core_flex": (12, 20),
    "carry": (40, 60),
    "isolation": (12, 15),
}
_DEFAULT_REPS = (8, 12)


def _select_diverse_exercises(exercises: list[dict]) -> list[dict]:
    """Keep a varied catalog-backed session without stacking axial load."""
    selected: list[dict] = []
    axial_used = unilateral_used = isolation_used = core_used = False
    group_counts: dict[str, int] = {}
    used_ids: set[int] = set()
    axial = {"squat", "hinge", "hinge_explosive"}
    unilateral = {"lunge", "single_leg", "unilateral"}
    for exercise in exercises:
        pattern = exercise.get("movement_pattern", "")
        group = exercise.get("muscle_group", "")
        exercise_id = exercise.get("exercise_id")
        if exercise_id in used_ids:
            continue
        if group_counts.get(group, 0) >= 4:
            continue
        if pattern in axial:
            if axial_used:
                continue
            axial_used = True
        elif pattern in unilateral:
            if unilateral_used:
                continue
            unilateral_used = True
        elif pattern == "isolation":
            if isolation_used:
                continue
            isolation_used = True
        elif group == "core":
            if core_used:
                continue
            core_used = True
        selected.append(dict(exercise))
        used_ids.add(exercise_id)
        group_counts[group] = group_counts.get(group, 0) + 1
    return selected


def _italian_safety_reason(reason: str) -> str:
    """Translate known safety-interlock messages while retaining measured values."""
    patterns = (
        (r"Illness-risk elevated \(([^)]+)\): rest or mobility only\.", r"Rischio di malattia elevato (\1): solo riposo o mobilità."),
        (r"Acute load spike \(injury risk ([^)]+)\): cap intensity below Zone 3\.", r"Picco di carico acuto (rischio infortunio \1): intensità limitata sotto la zona 3."),
        (r"ACWR ([^ ]+) > 1.5: replace high-impact work with low-impact volume\.", r"ACWR \1 > 1,5: sostituire il lavoro ad alto impatto con volume a basso impatto."),
        (r"Recovery suppressed \(HRV ([^,]+), RHR ([^)]+) vs baseline\): cap at moderate intensity\.", r"Recupero ridotto (HRV \1, RHR \2 rispetto al riferimento): intensità limitata a moderata."),
        (r"ACWR ([^ ]+) < 0.8 indicates detraining — recommend progressive rebuild rather than peak intensity\.", r"ACWR \1 < 0,8 indica detraining: si consiglia una ripresa progressiva."),
    )
    for pattern, replacement in patterns:
        if re.fullmatch(pattern, reason):
            return re.sub(pattern, replacement, reason)
    return "Valutazione di sicurezza applicata; intensità ridotta secondo i dati disponibili."


async def upcoming_events(
    session: AsyncSession, user_id: int, today: date, horizon_days: int = 14
) -> list[UserEvent]:
    horizon_end = datetime.combine(
        today + timedelta(days=horizon_days), datetime.min.time()
    )
    return (
        (
            await session.scalars(
                select(UserEvent)
                .where(
                    UserEvent.user_id == user_id,
                    UserEvent.starts_at >= datetime.combine(today, datetime.min.time()),
                    UserEvent.starts_at < horizon_end,
                )
                .order_by(UserEvent.starts_at)
            )
        )
        .all()
    )


async def recent_feedback(
    session: AsyncSession, user_id: int, today: date, days: int = 2
) -> list[SessionFeedback]:
    since = today - timedelta(days=days)
    return (
        (
            await session.scalars(
                select(SessionFeedback)
                .where(
                    SessionFeedback.user_id == user_id,
                    SessionFeedback.date >= since,
                    SessionFeedback.date <= today,
                )
                .order_by(SessionFeedback.date.desc(), SessionFeedback.id.desc())
            )
        )
        .all()
    )


async def season_plan_note(session: AsyncSession, user_id: int) -> str | None:
    doc = await session.scalar(
        select(UserContextDoc).where(
            UserContextDoc.user_id == user_id,
            UserContextDoc.doc_kind == "season_plan",
        )
    )
    if doc and doc.content.strip():
        first_lines = " / ".join(
            line.strip() for line in doc.content.strip().splitlines() if line.strip()
        )
        return first_lines[:200]
    return None


# ------------------------------------------------------- pure adjustment core


_NO_ADJUSTMENT_NOTE = (
    "no adjustments — full template session (no upcoming priority events, no soreness)"
)


def adjust(
    exercises: list[dict],
    events: list[dict],
    feedback: list[dict],
    today: date,
    *,
    safety: dict | None = None,
    locale: str = "en",
) -> tuple[list[dict], list[str]]:
    """Pure, testable adjustment core.

    exercises: [{exercise_id, name, muscle_group, movement_pattern,
                 impact_level, sets, reps_min, reps_max, rest_seconds, notes}]
    events:    [{kind, priority, starts_at (date), taper_days, title}]
    feedback:  [{date, activity_kind, rpe, soreness (list), injury_flag, notes}]

    P-04 audit (safety interlock): when ``safety`` carries a deterministic
    risk verdict from ``services.safety_interlock.exertion_veto`` (verdict in
    {go, modify, rest} + intensity_ceiling), the veto is applied FIRST and
    overrides every other rule. The athlete's journal feedback then layers on
    top — both can drop high-impact work, neither can resurrect it.
    """
    notes: list[str] = []
    italian = locale == "it"
    rows = [dict(e) for e in exercises]
    if not rows:
        return rows, notes

    # ---- P-04 safety interlock (deterministic veto, runs FIRST) -----------
    veto_ceiling: str | None = None
    if safety is not None:
        veto = exertion_veto(
            illness_risk=safety.get("illness_risk"),
            injury_risk=safety.get("injury_risk"),
            acwr=safety.get("acwr"),
            hrv_dev_pct=safety.get("hrv_dev_pct"),
            rhr_dev_bpm=safety.get("rhr_dev_bpm"),
        )
        if veto.vetoed:
            veto_ceiling = veto.intensity_ceiling
            notes.extend(
                [_italian_safety_reason(reason) for reason in veto.reasons]
                if italian
                else veto.reasons
            )
            if veto_ceiling == "rest":
                # Rest verdict: cap every row at 2 sets and drop all
                # high/moderate impact — the athlete needs recovery, not load.
                for row in rows:
                    if row.get("impact_level") in {"high", "moderate"}:
                        row["_drop"] = True
                    else:
                        row["sets"] = min(row.get("sets", 3), 2)
                        row["impact_level"] = "low"
            elif veto_ceiling == "low":
                for row in rows:
                    if row.get("impact_level") in {"high", "moderate"}:
                        row["_drop"] = True
            elif veto_ceiling == "moderate":
                for row in rows:
                    if row.get("impact_level") == "high":
                        row["_drop"] = True

    # ---- soreness / injury rules (most specific first) --------------------
    avoid_patterns: set[str] = set()
    light_groups: set[str] = set()
    dropped_groups: set[str] = set()
    for fb in feedback:
        areas = fb.get("soreness") or []
        if not isinstance(areas, list):
            continue
        for area in areas:
            key = str(area).strip().lower()
            patterns = _SORENESS_PATTERN_MAP.get(key)
            if patterns:
                avoid_patterns |= patterns
                if fb.get("rpe") and fb["rpe"] >= 8:
                    light_groups |= _SORENESS_GROUP_MAP.get(key, set())
                note_bits = ", ".join(sorted(patterns))
                notes.append(
                    (f"indolenzimento '{key}' segnalato — mantenere leggeri i movimenti "
                     "({note_bits}), a basso impatto e senza serie forzate")
                    if italian else
                    f"soreness '{key}' reported — keep {note_bits} patterns light (low impact, no grinding sets)"
                )
            if fb.get("injury_flag"):
                dropped_groups |= _SORENESS_GROUP_MAP.get(key, set())
                groups_text = ", ".join(sorted(_SORENESS_GROUP_MAP.get(key, set()))) or "affected"
                notes.append(
                    (f"segnalazione di infortunio per '{key}' — lavoro ({groups_text}) escluso per oggi; "
                     "consulta la nota del tuo feedback")
                    if italian else
                    f"injury flag on '{key}' — {groups_text} work dropped for today; see the note from your feedback"
                )

    # ---- event taper rules ------------------------------------------------
    leg_taper = False
    rest_day_advised = False
    for ev in events:
        ev_date: date = ev["starts_at"]
        days_to = (ev_date - today).days
        if days_to < 0 or days_to > 7:
            continue
        if days_to <= 1 and ev.get("priority") == 1:
            rest_day_advised = True
            notes.append(
                (f"'{ev.get('title')}' è {'oggi' if days_to == 0 else 'domani'} — solo riposo o mobilità molto leggera")
                if italian else
                f"'{ev.get('title')}' is {'today' if days_to == 0 else 'tomorrow'} — rest or very-light mobility only"
            )
        elif ev.get("priority") == 1 and ev.get("kind") in LEG_HEAVY_KINDS and days_to <= ev.get(
            "taper_days", 3
        ):
            leg_taper = True
            notes.append(
                (f"scarico per '{ev.get('title')}' ({ev.get('kind')}) tra {days_to} giorni — volume gambe dimezzato, "
                 "niente pliometria ad alto impatto, priorità a gambe fresche")
                if italian else
                f"taper for '{ev.get('title')}' ({ev.get('kind')}) in {days_to} day(s) — leg volume halved, no high-impact plyometrics, fresh legs first"
            )

    # ---- apply ------------------------------------------------------------
    for row in rows:
        # P-04: a row already dropped by the safety veto stays dropped.
        if row.get("_drop"):
            continue

        group = row["muscle_group"]
        pattern = row.get("movement_pattern")

        if group in dropped_groups:
            row["_drop"] = True
            continue

        if pattern in avoid_patterns:
            row["_drop"] = True
            continue

        if group in light_groups:
            row["sets"] = max(2, row["sets"] - 2)
            row["impact_level"] = "low"
            continue

        if leg_taper and group == "legs":
            if row.get("impact_level") == "high" or pattern == "plyo":
                row["_drop"] = True
                continue
            if pattern in {"squat", "hinge", "lunge"}:
                row["sets"] = max(2, row["sets"] // 2)
                row["reps_min"] = max(6, int(row["reps_min"] * 0.7))
                row["reps_max"] = max(row["reps_min"] + 2, int((row["reps_max"] or row["reps_min"]) * 0.7))
            continue

        if leg_taper and group in {"full_body"} and pattern in {"hinge_explosive", "full_body_explosive"}:
            row["_drop"] = True
            continue

        # P-04: even when no specific rule touched the row, the veto ceiling
        # may still drop it (e.g. moderate ceiling drops all high impact even
        # if the row's pattern is not in avoid_patterns).
        if veto_ceiling is not None and not impact_allowed_by_ceiling(
            row.get("impact_level"), veto_ceiling
        ):
            row["_drop"] = True

    if rest_day_advised:
        # everything light: cap sets at 2, drop all high impact
        for row in rows:
            if row.get("_drop"):
                continue
            if row.get("impact_level") == "high":
                row["_drop"] = True
                continue
            row["sets"] = min(row["sets"], 2)

    kept = [r for r in rows if not r.pop("_drop", False)]
    if dropped_groups and not any(r["muscle_group"] not in dropped_groups for r in rows):
        # everything was dropped — never hand back an empty session
        notes.append(
            "tutti i gruppi muscolari interessati sono protetti — sessione di riposo o mobilità leggera consigliata"
            if italian else
            "all target groups are protected — rest or light mobility is recommended"
        )
    if not notes:
        notes.append(
            "nessuna modifica — sessione completa del programma (nessun evento prioritario imminente, nessun indolenzimento)"
            if italian else _NO_ADJUSTMENT_NOTE
        )
    return kept, notes


# ------------------------------------------------------------- day plan gen


async def generate_day_plan(
    session: AsyncSession,
    user,  # User
    day: date,
) -> tuple[GymDayPlan, list[dict], str]:
    """Generate (or return the existing) concrete gym plan for `day`.

    Resolution order mirrors the watch: a concrete GymDayPlan wins if one
    exists; otherwise the recurring template slot for the weekday defines
    the session title, and the exercise rows are composed from the catalog
    split, then adjusted by the advisor.

    P-04 audit: pulls the latest ``DailyFeature`` row and passes its risk
    scores to ``adjust(safety=...)`` so the deterministic veto layer gates
    every prescription BEFORE the events/feedback rules run.
    """
    existing = await session.scalar(
        select(GymDayPlan).where(GymDayPlan.user_id == user.id, GymDayPlan.date == day)
    )
    if existing is not None:
        rows = await _plan_rows(session, existing)
        return existing, rows, "existing plan returned unchanged"

    tz = ZoneInfo(user.timezone)
    # All advisory lookups must be anchored to the requested plan date. This
    # avoids applying today's feedback or future feature data to backdated plans.
    today = day
    template = await resolve_day(session, user.id, day)
    title = template[0]["title"] if template else DEFAULT_WEEK_SPLIT[day.weekday()][0].title()
    groups = DEFAULT_WEEK_SPLIT[day.weekday()][1]

    catalog = (
        (await session.scalars(select(GymExercise).order_by(GymExercise.id))).all()
    )
    exercises: list[dict] = []
    for group in groups:
        pool = [e for e in catalog if e.muscle_group == group]
        for e in pool:
            reps_min, reps_max = _REP_TARGETS.get(e.movement_pattern, _DEFAULT_REPS)
            exercises.append(
                {
                    "exercise_id": e.id,
                    "name": e.name,
                    "muscle_group": e.muscle_group,
                    "movement_pattern": e.movement_pattern,
                    "impact_level": e.impact_level,
                    "sets": 3 if e.muscle_group != "core" else 3,
                    "reps_min": reps_min,
                    "reps_max": reps_max,
                    "rest_seconds": 120 if e.impact_level != "low" else 90,
                    "notes": None,
                }
            )
    catalog_exercises = exercises
    exercises = _select_diverse_exercises(catalog_exercises)

    events = [
        {
            "kind": ev.kind,
            "priority": ev.priority,
            "starts_at": ev.starts_at.astimezone(tz).date(),
            "taper_days": ev.taper_days,
            "title": ev.title,
        }
        for ev in await upcoming_events(session, user.id, today, horizon_days=14)
    ]
    feedback = [
        {
            "date": fb.date,
            "activity_kind": fb.activity_kind,
            "rpe": fb.rpe,
            "soreness": fb.soreness,
            "injury_flag": fb.injury_flag,
            "notes": fb.notes,
        }
        for fb in await recent_feedback(session, user.id, today)
    ]

    # P-04: pull the latest DailyFeature and pass its risk scores to the
    # safety interlock. Falls back gracefully (no feature row → no veto).
    from app.models.features import DailyFeature
    latest_feature = await session.scalar(
        select(DailyFeature)
        .where(DailyFeature.user_id == user.id, DailyFeature.date <= day)
        .order_by(DailyFeature.date.desc())
        .limit(1)
    )
    safety: dict | None = None
    if latest_feature is not None:
        safety = {
            "illness_risk": latest_feature.illness_risk_score,
            "injury_risk": latest_feature.injury_risk_score,
            "acwr": latest_feature.acwr,
            "hrv_dev_pct": latest_feature.hrv_deviation_from_baseline,
        }

    adjusted, notes = adjust(
        exercises, events, feedback, today, safety=safety, locale=user.locale
    )
    if len(exercises) < len(catalog_exercises):
        notes.append(
            "selezione varia dal catalogo: limitate le varianti di squat e hip hinge nella stessa sessione"
            if user.locale == "it" else
            "varied catalog selection: limited squat and hip-hinge variations in one session"
        )
    season = await season_plan_note(session, user.id)
    if season:
        notes.append(f"season plan on file: {season}")

    # 'ai' when the advisor changed anything (or a season plan informed the
    # day); 'template' when the session is straight from the catalog split.
    unchanged_note = (
        "nessuna modifica — sessione completa del programma (nessun evento prioritario imminente, nessun indolenzimento)"
        if user.locale == "it" else _NO_ADJUSTMENT_NOTE
    )
    changed = adjusted != exercises or notes != [unchanged_note] or bool(season)
    plan = GymDayPlan(
        user_id=user.id,
        date=day,
        title=title,
        source="ai" if changed else "template",
        status="draft",
        adjustment_note=" | ".join(notes)[:800],
    )
    session.add(plan)
    await session.flush()
    for pos, row in enumerate(adjusted, start=1):
        session.add(
            GymDayExercise(
                gym_day_plan_id=plan.id,
                exercise_id=row["exercise_id"],
                position=pos,
                sets=row["sets"],
                reps_min=row["reps_min"],
                reps_max=row.get("reps_max"),
                rest_seconds=row.get("rest_seconds", 90),
                notes=row.get("notes"),
            )
        )
    await session.flush()
    rows = await _plan_rows(session, plan)
    return plan, rows, plan.adjustment_note or ""


async def _plan_rows(session: AsyncSession, plan: GymDayPlan) -> list[dict]:
    rows = (
        await session.scalars(
            select(GymDayExercise)
            .where(GymDayExercise.gym_day_plan_id == plan.id)
            .order_by(GymDayExercise.position)
        )
    ).all()
    return [await _exercise_row(session, row) for row in rows]


async def _exercise_row(session: AsyncSession, row: GymDayExercise) -> dict:
    ex = await session.get(GymExercise, row.exercise_id)
    return {
        "gym_day_exercise_id": row.id,
        "exercise_id": row.exercise_id,
        "name": ex.name if ex else "?",
        "muscle_group": ex.muscle_group if ex else "",
        "movement_pattern": ex.movement_pattern if ex else "",
        "impact_level": ex.impact_level if ex else "low",
        "position": row.position,
        "sets": row.sets,
        "reps_min": row.reps_min,
        "reps_max": row.reps_max,
        "rest_seconds": row.rest_seconds,
        "notes": row.notes,
    }
