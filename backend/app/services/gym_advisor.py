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

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach import SessionFeedback, UserContextDoc, UserEvent
from app.models.gym_detail import GymDayPlan, GymDayExercise, GymExercise
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
        (r"Systemic stress signal elevated \(([^)]+)\): rest or mobility only\.", r"Segnale di stress sistemico elevato (\1): solo riposo o mobilità."),
        (r"Acute load spike \(load spike indicator ([^)]+)\): cap intensity below Zone 3\.", r"Picco di carico acuto (indicatore di picco di carico \1): intensità limitata sotto la zona 3."),
        (r"ACWR ([^ ]+) > 1.5: replace high-impact work with low-impact volume\.", r"ACWR \1 > 1,5: sostituire il lavoro ad alto impatto con volume a basso impatto."),
        (r"Recovery suppressed \(HRV ([^,]+), RHR ([^)]+) vs baseline\): cap at moderate intensity\.", r"Recupero ridotto (HRV \1, RHR \2 rispetto al riferimento): intensità limitata a moderata."),
        (r"ACWR ([^ ]+) < 0.8: recent recorded load is lower than its longer-window average\. Consider training history before increasing intensity\.", r"ACWR \1 < 0,8: il carico recente registrato è inferiore alla media di lungo periodo. Considera la storia di allenamento prima di aumentare l’intensità."),
    )
    for pattern, replacement in patterns:
        if re.fullmatch(pattern, reason):
            return re.sub(pattern, replacement, reason)
    return "Valutazione di sicurezza applicata; intensità ridotta secondo i dati disponibili."


async def upcoming_events(
    session: AsyncSession, user_id: int, today: date, horizon_days: int = 14
) -> list[UserEvent]:
    from app.models.user import User
    athlete = await session.get(User, user_id)
    tz = ZoneInfo(athlete.timezone if athlete else "UTC")
    horizon_end = datetime.combine(
        today + timedelta(days=horizon_days), datetime.min.time(), tzinfo=tz
    )
    return (
        (
            await session.scalars(
                select(UserEvent)
                .where(
                    UserEvent.user_id == user_id,
                    UserEvent.starts_at >= datetime.combine(today, datetime.min.time(), tzinfo=tz),
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
            systemic_stress=safety.get("systemic_stress"),
            load_spike=safety.get("load_spike"),
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
            if pattern in {"squat", "hinge", "lunge"} and row.get("reps_min") is not None:
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

ENGINE_VERSION = "recorded-history-v2-duration"
_HISTORY_DAYS = 7  # scheduling observation window, not a recovery deadline
_GROUPS = {"legs", "push", "pull", "core", "full_body"}


def _groups_in_text(text: str) -> list[str]:
    """Only explicit split labels; free text never becomes an instruction."""
    text = text.lower().replace("_", " ").replace("-", " ")
    if re.search(r"\b(full body|total body|corpo intero)\b", text):
        return ["legs", "push", "pull", "core"]
    groups = []
    if re.search(r"\b(upper body|upper|parte superiore)\b", text):
        groups.extend(["push", "pull"])
    for group, pattern in (
        ("legs", r"\b(legs|leg day|lower body|lower|gambe)\b"),
        ("push", r"\b(push|petto|chest|spinta)\b"),
        ("pull", r"\b(pull|dorso|tirata)\b"),
        ("core", r"\b(core|addominali)\b"),
    ):
        if re.search(pattern, text) and group not in groups:
            groups.append(group)
    return groups


def _prescription(entry: dict | None, catalog: list) -> tuple[list[str], list[int]]:
    """Actual named exercise prescription wins over a misleading title."""
    if not entry:
        return [], []
    if "steps" in entry:
        rows = _programmed_rows(entry, catalog)
        return list(dict.fromkeys(r["muscle_group"] for r in rows)), [r["exercise_id"] for r in rows]
    description = (entry.get("description") or "").lower()
    prescribed = [e for e in catalog if re.search(r"(?<!\w)" + re.escape(e.name.lower()) + r"(?!\w)", description)]
    if prescribed:
        return list(dict.fromkeys(e.muscle_group for e in prescribed)), [e.id for e in prescribed]
    groups = _groups_in_text(description)
    if not groups:
        groups = _groups_in_text(entry.get("session_type") or entry.get("title") or "")
    return groups, []


def choose_split(day: date, intended: list[str], history: list[dict], *,
                 preferred_split: str = "", upcoming: list[dict] | None = None,
                 confirmed: bool = False, locale: str = "en") -> tuple[list[str], str]:
    """Scheduling diversity for suggestions; never estimate physiological recovery."""
    italian = locale == "it"
    relevant = [h for h in history if 0 <= (day - h["date"]).days <= _HISTORY_DAYS]
    group_days = {g: sorted({h["date"] for h in relevant if h.get("groups", {}).get(g, 0) > 0}) for g in _GROUPS}
    groups = list(intended)
    if not groups:
        split = preferred_split.lower()
        if re.search(r"upper.*lower|lower.*upper", split):
            upper = max(group_days["push"] + group_days["pull"], default=date.min)
            lower = max(group_days["legs"], default=date.min)
            groups = ["push", "pull", "core"] if lower >= upper else ["legs", "core"]
        elif all(g in split for g in ("push", "pull")) and ("leg" in split or "gambe" in split):
            choice = min(("push", "legs", "pull"), key=lambda g: (max(group_days[g], default=date.min), ("push", "legs", "pull").index(g)))
            groups = [choice, "core"]
        elif _groups_in_text(preferred_split):
            groups = _groups_in_text(preferred_split)
        elif any(group_days[g] for g in ("legs", "push", "pull")):
            lower = max(group_days["legs"], default=date.min)
            upper = max(group_days["push"] + group_days["pull"], default=date.min)
            groups = ["push", "pull", "core"] if lower >= upper else ["legs", "core"]
        else:
            groups = list(DEFAULT_WEEK_SPLIT[day.weekday()][1])
    lower_work = [h for h in relevant if h.get("groups", {}).get("legs", 0) > 0 and (day - h["date"]).days <= 1]
    repeated_lower = [h for h in relevant if h.get("groups", {}).get("legs", 0) >= 6 and (day - h["date"]).days <= 3]
    hard_endurance = next((u for u in upcoming or [] if u.get("hard") and 0 <= (u["date"] - day).days <= 1), None)
    conflict = "legs" in groups or "full_body" in groups
    inferred_upper = not intended and "legs" not in groups and bool(lower_work)
    reason = ""
    if (conflict or inferred_upper) and (lower_work or len(repeated_lower) >= 2):
        recorded = max(lower_work or repeated_lower, key=lambda h: h["date"])
        reason = (f"Lavoro gambe registrato il {recorded['date']} ({recorded['source']}); " if italian else
                  f"Lower-body work recorded on {recorded['date']} ({recorded['source']}); ")
    elif conflict and hard_endurance:
        reason = (f"Seduta endurance intensa confermata il {hard_endurance['date']} ({hard_endurance['source']}); " if italian else
                  f"Confirmed hard endurance session on {hard_endurance['date']} ({hard_endurance['source']}); ")
    if reason:
        if confirmed:
            return groups, reason + ("programma confermato mantenuto. Valuta un'alternativa per la parte superiore prima di modificarlo." if italian else
                "confirmed session retained. Review an upper-body alternative before changing it.")
        return ["push", "pull", "core"], reason + ("proposta per la parte superiore per evitare di sovrapporre il lavoro gambe." if italian else
            "suggesting upper body to avoid stacking lower-body work.")
    upper_overlap = [h for h in relevant if (day - h["date"]).days <= 1
        and any(h.get("groups", {}).get(g, 0) >= 6 for g in groups if g in {"push", "pull"})]
    if upper_overlap:
        recorded = max(upper_overlap, key=lambda h: h["date"])
        reason = (f"Volume per la parte superiore registrato il {recorded['date']} ({recorded['source']}); " if italian else
            f"Upper-body set volume recorded on {recorded['date']} ({recorded['source']}); ")
        if confirmed:
            return groups, reason + ("programma confermato mantenuto; valuta un'alternativa prima di modificarlo." if italian else
                "confirmed session retained; review an alternative before changing it.")
        trained = {g for h in upper_overlap for g in ("push", "pull") if h.get("groups", {}).get(g, 0) >= 6}
        alternative = [g for g in ("push", "pull") if g not in trained] + ["core"]
        if not alternative[:-1] and not lower_work and not hard_endurance:
            alternative = ["legs", "core"]
        return alternative, reason + ("proposta per i gruppi meno allenati recentemente." if italian else
            "suggesting groups with less recent recorded work.")
    if any(h.get("unknown_strength") for h in relevant):
        return groups, ("Forza registrata senza dettagli degli esercizi: gruppi allenati e intensità non verificabili." if italian else
            "Strength activity recorded without exercise details: trained groups and intensity are unknown.")
    if not relevant:
        return groups, ("Nessuna attività recente registrata; recupero e lavoro precedente non sono verificabili. Suddivisione indicativa." if italian else
            "No recent activity recorded; recovery and prior training are unknown. Split is provisional.")
    return groups, ("Proposta basata sul programma e sul lavoro registrato; il recupero non è stimato." if italian else
        "Suggestion follows the intended split and recorded work; recovery is not inferred.")


def _flatten_steps(steps: list[dict]) -> list[dict]:
    rows = []
    for step in steps:
        if step.get("kind") == "repeat":
            for _ in range(step.get("repetitions", 1)):
                rows.extend(step.get("steps", []))
        else:
            rows.append(step)
    return rows


def _programmed_rows(entry: dict, catalog: list) -> list[dict]:
    """Approved explicit exercise/sets/reps; unknown prescriptions stay unknown."""
    result = []
    for step in _flatten_steps(entry.get("steps", [])):
        if step.get("kind") != "strength":
            continue
        exercise = next((e for e in catalog if e.name.casefold() == (step.get("exercise") or "").casefold()), None)
        timed = step.get("duration_s") is not None and step.get("reps") is None
        if exercise is None or step.get("sets") is None or (step.get("reps") is None and not timed):
            return []
        note = step.get("description") or None
        if step.get("load_kg") is not None:
            note = " | ".join(filter(None, [note, f"{step['load_kg']} kg prescribed"]))
        result.append({"exercise_id": exercise.id, "name": exercise.name, "muscle_group": exercise.muscle_group,
            "movement_pattern": exercise.movement_pattern, "impact_level": exercise.impact_level,
            "sets": step["sets"], "reps_min": step.get("reps"), "reps_max": step.get("reps"),
            "duration_min_s": step["duration_s"] if timed else None, "duration_max_s": step["duration_s"] if timed else None,
            "rest_seconds": 90, "notes": note})
    return result


async def planning_inputs(session: AsyncSession, user, day: date) -> dict:
    """Bounded, owned actual logs, imports and approved future sessions."""
    from app.models.activity import Activity, Discipline
    from app.models.athlete import AthleteProfile
    from app.models.athlete_training import SessionCheckin
    from app.models.features import DailyFeature
    from app.models.gym_detail import GymSetLog
    from app.models.training import PlannedSession, TrainingPlan
    from app.models.structured_workout import StructuredWorkoutVersion
    from app.services.structured_workouts import structure_of
    from app.services.activity_presentation import imported_strength, sport_kind
    from app.services.athlete_day import plan_conditions

    tz = ZoneInfo(user.timezone)
    start = datetime.combine(day - timedelta(days=_HISTORY_DAYS), datetime.min.time(), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    logs = (await session.execute(select(GymSetLog, GymExercise)
        .join(GymDayExercise, GymSetLog.gym_day_exercise_id == GymDayExercise.id)
        .join(GymDayPlan, GymDayExercise.gym_day_plan_id == GymDayPlan.id)
        .join(GymExercise, GymDayExercise.exercise_id == GymExercise.id)
        .where(GymSetLog.user_id == user.id, GymDayPlan.user_id == user.id,
               GymSetLog.done_at >= start, GymSetLog.done_at < end)
        .order_by(GymSetLog.done_at, GymSetLog.id).limit(5001))).all()
    activities = (await session.execute(select(Activity, Discipline.name).outerjoin(Discipline)
        .where(Activity.user_id == user.id, Activity.start_time >= start, Activity.start_time < end)
        .order_by(Activity.start_time, Activity.id).limit(201))).all()
    checks = (await session.scalars(select(SessionCheckin).outerjoin(Activity, SessionCheckin.activity_id == Activity.id)
        .outerjoin(PlannedSession, SessionCheckin.planned_session_id == PlannedSession.id)
        .where(SessionCheckin.user_id == user.id, or_(
            and_(Activity.start_time >= start, Activity.start_time < end),
            and_(PlannedSession.date >= day - timedelta(days=2), PlannedSession.date <= day)))
        .order_by(SessionCheckin.updated_at, SessionCheckin.id).limit(201))).all()
    planned = (await session.execute(select(TrainingPlan, PlannedSession, Discipline.name)
        .join(PlannedSession, PlannedSession.training_plan_id == TrainingPlan.id)
        .outerjoin(Discipline, PlannedSession.discipline_id == Discipline.id)
        .where(TrainingPlan.user_id == user.id, PlannedSession.date >= day,
            PlannedSession.date <= day + timedelta(days=3), *plan_conditions(PlannedSession.date))
        .order_by(PlannedSession.date, PlannedSession.start_time, PlannedSession.id).limit(101))).all()
    versions = (await session.scalars(select(StructuredWorkoutVersion).where(
        StructuredWorkoutVersion.user_id == user.id,
        StructuredWorkoutVersion.planned_session_id.in_([workout.id for _, workout, _ in planned[:100]]))
        .distinct(StructuredWorkoutVersion.planned_session_id)
        .order_by(StructuredWorkoutVersion.planned_session_id, StructuredWorkoutVersion.revision.desc()).limit(101))).all()
    structured = {}
    for version in versions[:100]:
        if version.planned_session_id not in structured:
            structured[version.planned_session_id] = {"steps": [step.model_dump(mode="json") for step in structure_of(version).steps],
                "workout_revision": version.revision, "workout_hash": version.payload_hash}
    history, buckets = [], {}
    for log, ex in logs[:5000]:
        if (log.reps_done or 0) <= 0 and (log.duration_s or 0) <= 0:
            continue
        observed_day = log.done_at.astimezone(tz).date()
        bucket = buckets.setdefault(observed_day, {"date": observed_day, "groups": {}, "patterns": [], "exercise_ids": [],
            "source": "gym set logs", "set_ids": [], "volume_kg": 0, "weight_known_sets": 0})
        bucket["groups"][ex.muscle_group] = bucket["groups"].get(ex.muscle_group, 0) + 1
        bucket["patterns"].append(ex.movement_pattern)
        bucket["exercise_ids"].append(ex.id)
        bucket["set_ids"].append(log.id)
        if log.weight_kg is not None and log.reps_done is not None:
            bucket["volume_kg"] += float(log.weight_kg) * log.reps_done
            bucket["weight_known_sets"] += 1
    history.extend(buckets.values())
    for activity, discipline in activities[:200]:
        local_day = activity.start_time.astimezone(tz).date()
        kind = sport_kind(discipline, activity.source_metrics)
        details = imported_strength(activity.source_metrics) if kind == "strength" else []
        # Actual set timestamps, not a same-date plan, establish overlap.
        overlapping = any(activity.start_time <= log.done_at < activity.start_time + timedelta(seconds=activity.duration_s)
                          and ((log.reps_done or 0) > 0 or (log.duration_s or 0) > 0) for log, _ in logs[:5000])
        groups = {}
        if not overlapping:
            for ex in details:
                if ex.get("muscle_group"):
                    groups[ex["muscle_group"]] = groups.get(ex["muscle_group"], 0) + ex["sets"]
        history.append({"date": local_day, "groups": groups, "source": f"activity:{activity.id}",
            "unknown_strength": kind == "strength" and not overlapping and not groups,
            "kind": kind, "duration_s": activity.duration_s, "training_load": activity.training_load,
            "exercise_names": [e["name"] for e in details], "recorded_exercises": details})
    upcoming, intended = [], []
    for plan, workout, discipline in planned[:100]:
        kind = sport_kind(discipline)
        item = {"date": workout.date, "title": workout.session_type or "Strength", "session_type": workout.session_type,
            "description": workout.description, "source": f"planned_session:{workout.id}",
            "plan_id": plan.id, "revision": plan.revision, "protected": plan.protected or workout.protected,
            "intensity_targets": workout.intensity_targets, "kind": kind}
        item.update(structured.get(workout.id, {}))
        if workout.date == day and kind == "strength":
            intended.append(item)
        if kind in {"running", "cycling"}:
            label = " ".join((workout.session_type or "", workout.description or "")).lower()
            rpe = str((workout.intensity_targets or {}).get("rpe", ""))
            item["hard"] = bool(re.search(r"\b(intervals?|ripetute|tempo|threshold|soglia|race|gara|vo2\w*)\b", label)
                                or re.fullmatch(r"(?:8|9|10)(?:\s*[-–]\s*(?:9|10))?", rpe)
                                or any(step.get("kind") in {"interval", "threshold", "tempo"} for step in _flatten_steps(item.get("steps", []))))
            upcoming.append(item)
    feature = await session.scalar(select(DailyFeature).where(DailyFeature.user_id == user.id,
        DailyFeature.date <= day, DailyFeature.date >= day - timedelta(days=2)).order_by(DailyFeature.date.desc()).limit(1))
    safety = {"date": feature.date, "systemic_stress": feature.systemic_stress_signal,
        "load_spike": feature.load_spike_indicator, "acwr": feature.acwr,
        "hrv_dev_pct": feature.hrv_deviation_from_baseline} if feature else None
    profile = await session.get(AthleteProfile, user.id)
    return {"history": history, "intended": intended, "upcoming": upcoming, "safety": safety,
        "checks": [{"id": c.id, "revision": c.revision, "fatigue": c.fatigue, "soreness": c.soreness,
                    "rpe": c.rpe, "pain": c.pain, "felt_unwell": c.felt_unwell, "status": c.status} for c in checks[:200]],
        "profile": profile.context if profile else {}, "profile_revision": profile.revision if profile else 0,
        "training_focus": profile.training_focus if profile else [],
        "complete": len(logs) <= 5000 and len(activities) <= 200 and len(checks) <= 200 and len(planned) <= 100 and len(versions) <= 100}


def _catalog_rows(catalog: list, groups: list[str], history: list[dict], day: date,
                  prescribed: list[int], preferred: str = "") -> list[dict]:
    rows = []
    observed_ids = {i for h in history for i in h.get("exercise_ids", [])}
    observed_names = {name.lower() for h in history for name in h.get("exercise_names", [])}
    pool = [e for e in catalog if (e.id in prescribed if prescribed else e.muscle_group in groups)]
    # Programmed/recorded exercises stay stable for progression. Unestablished
    # choices alternate deterministically by week, never randomly per request.
    pool.sort(key=lambda e: (prescribed.index(e.id) if e.id in prescribed else 999,
        0 if e.id in observed_ids or e.name.lower() in observed_names or e.name.lower() in preferred.lower() else 1,
        (e.id + day.toordinal() // 7) % max(len(catalog), 1), e.id))
    for ex in pool:
        timed = ex.movement_pattern == "core_anti"
        reps_min, reps_max = (None, None) if timed else _REP_TARGETS.get(ex.movement_pattern, _DEFAULT_REPS)
        rows.append({"exercise_id": ex.id, "name": ex.name, "muscle_group": ex.muscle_group,
            "movement_pattern": ex.movement_pattern, "impact_level": ex.impact_level,
            "sets": 3, "reps_min": reps_min, "reps_max": reps_max,
            "duration_min_s": 30 if timed else None, "duration_max_s": 60 if timed else None,
            "rest_seconds": 120 if ex.impact_level != "low" else 90, "notes": None})
    return rows if prescribed else _select_diverse_exercises(rows)


def _snapshot(title: str, rows: list[dict], note: str, *, source: str = "template") -> dict:
    return {"title": title, "status": "draft", "source": source, "exercises": [{k: r.get(k) for k in ("exercise_id", "sets", "reps_min", "reps_max", "duration_min_s", "duration_max_s", "rest_seconds", "notes")} for r in rows],
            "adjustment_note": note}


async def _generation_context(session: AsyncSession, user, day: date) -> tuple:
    """Read exactly the inputs used for generation, without proposing or writing."""
    from app.queries.gym import list_slots

    inputs = await planning_inputs(session, user, day)
    catalog = list((await session.scalars(select(GymExercise).order_by(GymExercise.id))).all())
    entry = inputs["intended"][0] if inputs["intended"] else None
    if not entry:
        slots = [s for s in await list_slots(session, user.id) if s.active and s.weekday == day.weekday()]
        if slots:
            entry = {"title": slots[0].title, "description": slots[0].description, "source": f"gym_schedule_slot:{slots[0].id}"}
    tz = ZoneInfo(user.timezone)
    events = [{"kind": ev.kind, "priority": ev.priority, "starts_at": ev.starts_at.astimezone(tz).date(),
        "taper_days": ev.taper_days, "title": ev.title} for ev in await upcoming_events(session, user.id, day)]
    feedback = [{"date": fb.date, "activity_kind": fb.activity_kind, "rpe": fb.rpe, "soreness": fb.soreness,
        "injury_flag": fb.injury_flag, "notes": fb.notes} for fb in await recent_feedback(session, user.id, day)]
    return inputs, catalog, entry, events, feedback


def _input_fingerprint(user, day: date, context: tuple) -> str:
    import hashlib
    import json

    inputs, catalog, entry, events, feedback = context
    evidence = {"version": ENGINE_VERSION, "day": day, "timezone": user.timezone, "locale": user.locale,
        "inputs": inputs, "entry": entry,
        "catalog": [(e.id, e.name, e.muscle_group, e.movement_pattern, e.impact_level) for e in catalog],
        "events": events, "feedback": feedback}
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


async def current_input_fingerprint(session: AsyncSession, user, day: date) -> str:
    """Confirmation freshness check; caller holds changes then gym-day locks."""
    return _input_fingerprint(user, day, await _generation_context(session, user, day))


async def generate_day_plan(session: AsyncSession, user, day: date) -> tuple[GymDayPlan, list[dict], str]:
    """POST generates or safely refreshes a draft; GET never writes anything.

    Confirmed/completed/manual plans and any plan with recorded sets are
    retained. Draft revisions preserve before/after snapshots and the input
    fingerprint in ChangeAudit. No canonical session is written here.
    """
    from app.models.gym_detail import GymSetLog
    from app.models.lab import ChangeAudit
    from app.services.evidence import scope_lock
    # Shared evidence writers take changes first; never acquire it after a
    # gym-day lock (profile updates and confirmations must see one snapshot).
    await scope_lock(session, user.id, "changes")
    await scope_lock(session, user.id, f"gym-plan:{day}")
    existing = await session.scalar(select(GymDayPlan).where(GymDayPlan.user_id == user.id, GymDayPlan.date == day))
    context = await _generation_context(session, user, day)
    inputs, catalog, entry, events, feedback = context
    intended, prescribed = _prescription(entry, catalog)
    groups, explanation = choose_split(day, intended, inputs["history"], preferred_split=inputs["profile"].get("gym_split", ""),
        upcoming=inputs["upcoming"], confirmed=bool(inputs["intended"]), locale=user.locale)
    immutable = existing is not None and (existing.status != "draft" or existing.source == "manual")
    if existing is not None and not immutable:
        immutable = bool(await session.scalar(select(GymSetLog.id).join(GymDayExercise,
            GymSetLog.gym_day_exercise_id == GymDayExercise.id).where(GymSetLog.user_id == user.id,
                GymDayExercise.gym_day_plan_id == existing.id).limit(1)))
    if immutable:
        rows = await _plan_rows(session, existing)
        _, conflict = choose_split(day, list(dict.fromkeys(r["muscle_group"] for r in rows)), inputs["history"],
            upcoming=inputs["upcoming"], confirmed=True, locale=user.locale)
        return existing, rows, " | ".join(filter(None, [existing.adjustment_note, conflict]))
    exercises = _catalog_rows(catalog, groups, inputs["history"], day, prescribed, inputs["profile"].get("preferred_exercises", ""))
    if entry and "steps" in entry:
        exercises = _programmed_rows(entry, catalog)
    adjusted, safety_notes = adjust(exercises, events, feedback, day, safety=inputs["safety"], locale=user.locale)
    # Canonical prescriptions remain reviewable and unchanged even with a veto.
    # Concerns are disclosed; this advisor cannot approve a canonical mutation.
    if inputs["intended"] and adjusted != exercises:
        adjusted = exercises
        explanation += (" Modifiche per sicurezza proposte da rivedere; prescrizione confermata mantenuta." if user.locale == "it" else
                        " Safety adjustments require review; confirmed prescription retained.")
    notes = [explanation]
    if not inputs["intended"]:
        notes.extend(n for n in safety_notes if n != _NO_ADJUSTMENT_NOTE and not n.startswith("nessuna modifica"))
        checks = inputs["checks"]
        reported = any(c.get("fatigue") is not None and c["fatigue"] >= 7 or c.get("soreness") is not None and c["soreness"] >= 7
                       or c.get("pain") is True or c.get("felt_unwell") is True for c in checks)
        if reported:
            adjusted = [dict(r, sets=min(r["sets"], 2)) for r in adjusted if r["impact_level"] != "high"]
            notes.append("Fatica, indolenzimento o malessere segnalati: volume della proposta ridotto." if user.locale == "it" else
                "Reported fatigue, soreness or discomfort: proposal volume reduced.")
        hard_recent = any(h.get("kind") in {"running", "cycling"} and h.get("duration_s", 0) >= 5400
                          and (day - h["date"]).days <= 1 for h in inputs["history"])
        if hard_recent and any(r["muscle_group"] in {"legs", "full_body"} for r in adjusted):
            adjusted = [dict(r, sets=min(r["sets"], 2)) if r["muscle_group"] in {"legs", "full_body"} else r for r in adjusted]
            notes.append("Endurance di almeno 90 minuti registrata recentemente: volume gambe della proposta ridotto; intensità non nota." if user.locale == "it" else
                "Recent recorded endurance lasted at least 90 minutes: proposed leg volume reduced; intensity unknown.")
    elif safety_notes != [_NO_ADJUSTMENT_NOTE] and not all(n.startswith("nessuna modifica") for n in safety_notes):
        notes.append("Contesto di sicurezza da rivedere prima della sessione confermata." if user.locale == "it" else
            "Review available safety context before the confirmed session.")
    if not inputs["intended"] and inputs["profile"].get("preferred_rest_day") == day.weekday():
        adjusted = []
        notes.insert(0, "Giorno di riposo preferito nel profilo: nessuna seduta suggerita." if user.locale == "it" else
            "Saved preferred rest day: no workout suggested.")
    if inputs["profile"].get("self_declared_restrictions"):
        notes.append("Rivedi le limitazioni dichiarate nel profilo prima di confermare." if user.locale == "it" else
            "Review your saved self-declared restrictions before confirming.")
    if not inputs["safety"]:
        notes.append("Dati di recupero recenti non disponibili." if user.locale == "it" else "Recent recovery data unavailable.")
    if not inputs["complete"]:
        notes.append("Storia parziale: limite dei dati raggiunto." if user.locale == "it" else "History incomplete: observation limit reached.")
    if inputs["training_focus"] and "gym" not in inputs["training_focus"]:
        notes.append("Forza non inclusa nelle priorità salvate; proposta facoltativa." if user.locale == "it" else "Strength is outside saved training priorities; suggestion is optional.")
    if len(inputs["intended"]) > 1:
        notes.append("Più sessioni forza confermate: questa proposta descrive solo la prima." if user.locale == "it" else "Multiple confirmed strength sessions: this suggestion covers only the first.")
    if inputs["intended"] and not intended:
        adjusted = []
        notes.insert(0, "Prescrizione forza confermata senza gruppi o esercizi riconoscibili: consulta il programma, nessun esercizio inventato." if user.locale == "it" else
            "Confirmed strength prescription has no identifiable groups or exercises: consult the program; no exercises inferred.")
    upper_only = "legs" not in groups and "full_body" not in groups
    fallback_title = ("Parte superiore" if user.locale == "it" else "Upper body") if upper_only else ("Forza" if user.locale == "it" else "Strength")
    title = entry["title"] if entry else fallback_title
    if entry and not inputs["intended"] and groups != intended:
        title = fallback_title
    if inputs["intended"] and "steps" not in entry and adjusted:
        notes.append("Serie e ripetizioni sono una proposta da confermare, non obiettivi del programma." if user.locale == "it" else
            "Sets and reps are a proposal for review, not recorded program targets.")
    note = " | ".join(notes)[:1800]
    fingerprint = _input_fingerprint(user, day, context)
    previous_audit = await session.scalar(select(ChangeAudit).where(ChangeAudit.user_id == user.id,
        ChangeAudit.action.in_(("gym_draft_generated", "gym_draft_refreshed")),
        ChangeAudit.payload["plan_id"].astext == str(existing.id if existing else 0)).order_by(ChangeAudit.id.desc()).limit(1)) if existing else None
    before = _snapshot(existing.title, await _plan_rows(session, existing), existing.adjustment_note or "", source=existing.source) if existing else None
    after = _snapshot(title, adjusted, note)
    if existing and before == after and previous_audit and previous_audit.payload.get("input_fingerprint") == fingerprint:
        return existing, await _plan_rows(session, existing), existing.adjustment_note or ""
    revision = int(previous_audit.payload.get("revision", 1)) + 1 if previous_audit else (2 if existing else 1)
    plan = existing or GymDayPlan(user_id=user.id, date=day, status="draft")
    plan.title, plan.source, plan.adjustment_note = title, "template", note
    plan.updated_at = datetime.now(ZoneInfo("UTC"))
    if existing:
        await session.execute(delete(GymDayExercise).where(GymDayExercise.gym_day_plan_id == existing.id))
    else:
        session.add(plan)
    await session.flush()
    for pos, row in enumerate(adjusted, start=1):
        session.add(GymDayExercise(gym_day_plan_id=plan.id, exercise_id=row["exercise_id"], position=pos,
            sets=row["sets"], reps_min=row["reps_min"], reps_max=row.get("reps_max"),
            duration_min_s=row.get("duration_min_s"), duration_max_s=row.get("duration_max_s"),
            rest_seconds=row.get("rest_seconds", 90), notes=row.get("notes")))
    session.add(ChangeAudit(user_id=user.id, action="gym_draft_refreshed" if existing else "gym_draft_generated",
        payload={"plan_id": plan.id, "revision": revision, "engine_version": ENGINE_VERSION,
                 "input_fingerprint": fingerprint, "before": before, "after": after}))
    await session.flush()
    return plan, await _plan_rows(session, plan), note


async def _plan_rows(session: AsyncSession, plan: GymDayPlan) -> list[dict]:
    rows = (await session.scalars(select(GymDayExercise).where(GymDayExercise.gym_day_plan_id == plan.id)
                                 .order_by(GymDayExercise.position))).all()
    return [await _exercise_row(session, row) for row in rows]


async def _exercise_row(session: AsyncSession, row: GymDayExercise) -> dict:
    ex = await session.get(GymExercise, row.exercise_id)
    return {"gym_day_exercise_id": row.id, "exercise_id": row.exercise_id, "name": ex.name if ex else "?",
        "muscle_group": ex.muscle_group if ex else "", "movement_pattern": ex.movement_pattern if ex else "",
        "impact_level": ex.impact_level if ex else "low", "position": row.position, "sets": row.sets,
        "reps_min": row.reps_min, "reps_max": row.reps_max,
        "duration_min_s": row.duration_min_s, "duration_max_s": row.duration_max_s, "rest_seconds": row.rest_seconds, "notes": row.notes}
