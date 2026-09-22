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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.gym_detail import GymDayPlan, GymDayExercise, GymExercise
from app.queries.gym import resolve_day

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
) -> tuple[list[dict], list[str]]:
    """Pure, testable adjustment core.

    exercises: [{exercise_id, name, muscle_group, movement_pattern,
                 impact_level, sets, reps_min, reps_max, rest_seconds, notes}]
    events:    [{kind, priority, starts_at (date), taper_days, title}]
    feedback:  [{date, activity_kind, rpe, soreness (list), injury_flag, notes}]
    """
    notes: list[str] = []
    rows = [dict(e) for e in exercises]
    if not rows:
        return rows, notes

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
                    f"soreness '{key}' reported — keep {note_bits} patterns light "
                    "(low impact, no grinding sets)"
                )
            if fb.get("injury_flag"):
                dropped_groups |= _SORENESS_GROUP_MAP.get(key, set())
                notes.append(
                    f"injury flag on '{key}' — {_SORENESS_GROUP_MAP.get(key, set()) or 'affected'} "
                    "work dropped for today; see the note from your feedback"
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
                f"'{ev.get('title')}' is {'today' if days_to == 0 else 'tomorrow'} — "
                "rest or very-light mobility only"
            )
        elif ev.get("priority") == 1 and ev.get("kind") in LEG_HEAVY_KINDS and days_to <= ev.get(
            "taper_days", 3
        ):
            leg_taper = True
            notes.append(
                f"taper for '{ev.get('title')}' ({ev.get('kind')}) in {days_to} day(s) — "
                "leg volume halved, no high-impact plyometrics, fresh legs first"
            )

    # ---- apply ------------------------------------------------------------
    for row in rows:
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

    if rest_day_advised:
        # everything light: cap sets at 2, drop all high impact
        for row in rows:
            if row.get("impact_level") == "high":
                row["_drop"] = True
                continue
            row["sets"] = min(row["sets"], 2)

    kept = [r for r in rows if not r.pop("_drop", False)]
    if dropped_groups and not any(r["muscle_group"] not in dropped_groups for r in rows):
        # everything was dropped — never hand back an empty session
        kept = [r for r in rows]
        for r in kept:
            r["sets"] = max(2, min(r["sets"], 3))
        notes.append("all target groups were protected — kept a minimal light session instead")
    if not notes:
        notes.append(_NO_ADJUSTMENT_NOTE)
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
    split, then adjusted by the advisor."""
    existing = await session.scalar(
        select(GymDayPlan).where(GymDayPlan.user_id == user.id, GymDayPlan.date == day)
    )
    if existing is not None:
        rows = await _plan_rows(session, existing)
        return existing, rows, "existing plan returned unchanged"

    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    template = await resolve_day(session, user.id, day)
    title = template[0]["title"] if template else DEFAULT_WEEK_SPLIT[day.weekday()][0].title()
    groups = DEFAULT_WEEK_SPLIT[day.weekday()][1]

    catalog = (
        (await session.scalars(select(GymExercise).order_by(GymExercise.id))).all()
    )
    exercises: list[dict] = []
    for group in groups:
        pool = [e for e in catalog if e.muscle_group == group]
        for e in pool[:4]:
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
    adjusted, notes = adjust(exercises, events, feedback, today)
    season = await season_plan_note(session, user.id)
    if season:
        notes.append(f"season plan on file: {season}")

    # 'ai' when the advisor changed anything (or a season plan informed the
    # day); 'template' when the session is straight from the catalog split.
    changed = notes != [_NO_ADJUSTMENT_NOTE]
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
