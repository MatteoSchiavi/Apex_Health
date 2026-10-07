"""Conservative, deterministic daily decisions, shared by UI and AI."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.lab import DecisionRecord
from app.services.analytics import baseline, constraints
from app.services.evidence import EvidenceError, coverage, scope_lock, snapshot_revision

VERSION = "daily-decision-v1"


def _interpretation(output, signals, locale):
    """Stable presentation contract; preserve the underlying rule output."""
    action = output["action"]
    headlines = {
        "train_normally": ("Keep your planned training", "Mantieni l’allenamento pianificato"),
        "reduce_volume": ("Keep the focus, reduce the volume", "Mantieni l’obiettivo, riduci il volume"),
        "swap_session": ("Review a gentler session", "Valuta una sessione più leggera"),
        "recover": ("Make room for recovery today", "Dedica oggi al recupero"),
        "collect_more_data": ("Add current evidence before adjusting training", "Aggiungi misurazioni attuali prima di adattare l’allenamento"),
    }
    changes = []
    for metric, signal in signals.items():
        latest = signal.get("latest")
        current = latest["value"] if latest and signal["availability"] == "available" else None
        reference = output["baselines"].get(metric, {})
        median = reference.get("median") if reference.get("state") == "available" else None
        changes.append({
            "metric": metric,
            "current": current,
            "baseline": median,
            "delta": round(current - median, 3) if current is not None and median is not None else None,
            "origin": latest["origin"] if latest else None,
        })
    recommendation = {"action": action, "reason": output["next_step"]}
    if action == "reduce_volume":
        recommendation["duration_factor"] = 0.7
    today_sessions = [s for s in output["constraints"]["sessions"] if s["date"] == output["date"]]
    if today_sessions:
        recommendation["planned_session_id"] = today_sessions[0]["id"]
    return {
        "state": {
            "collect_more_data": "insufficient_data",
            "train_normally": "stable",
            "reduce_volume": "adjustment_suggested",
            "swap_session": "adjustment_suggested",
            "recover": "recovery_suggested",
        }[action],
        "headline": headlines[action][locale == "it"],
        "key_changes": changes,
        "contributors": output["reasons"],
        "data_coverage": output["data_completeness"],
        "recommended_action": recommendation,
    }


async def daily_decision(session, user, *, now=None, for_ai=False, persist=False):
    # The evidence reads, revision and cached decision must share the erasure
    # boundary. A revision sampled after mixed reads is not a valid snapshot.
    await scope_lock(session, user.id, "changes")
    now = now or datetime.now(UTC)
    day = now.astimezone(ZoneInfo(user.timezone)).date()
    cover = await coverage(session, user, now=now, for_ai=for_ai)
    requirements = ["hrv_overnight_rmssd", "resting_hr", "sleep_duration"]
    signals = {m["metric"]: m for m in cover["metrics"] if m["metric"] in requirements}
    fresh = {
        k: v
        for k, v in signals.items()
        if v["availability"] == "available" and v["sample_days_7d"] >= 4
    }
    missing = [k for k in requirements if k not in fresh]
    ctx = await constraints(session, user, day)
    evidence, baselines = [], {}
    for key in requirements[:2]:
        latest = signals[key]["latest"]
        try:
            baselines[key] = await baseline(
                session,
                user,
                key,
                day - timedelta(days=31),
                day - timedelta(days=4),
                origin=latest["origin"] if latest else "garmin",
                for_ai=for_ai,
            )
        except EvidenceError:
            baselines[key] = {
                "state": "INSUFFICIENT_DATA",
                "median": None,
                "sample_count": 0,
            }
        if baselines[key]["state"] != "available":
            missing.append(key + "_baseline")
        if latest:
            evidence.append(latest)
    if signals["sleep_duration"]["latest"]:
        evidence.append(signals["sleep_duration"]["latest"])
    action, reasons = (
        "collect_more_data",
        ["Current coverage or comparable personal baselines are incomplete."],
    )
    alternatives = [
        {
            "action": "collect_more_data",
            "duration_min": None,
            "reason": "Sync/import missing observations or record a subjective check-in.",
        }
    ]
    if not missing:
        action, reasons = (
            "train_normally",
            ["Recent observations are covered; no conservative adjustment rule fired."],
        )
        hrv, hr, sleep = [signals[k]["latest"]["value"] for k in requirements]
        hrv_base, hr_base = [baselines[k]["median"] for k in requirements[:2]]
        if hrv_base and hrv < 0.8 * hrv_base and hr >= hr_base + 5:
            action, reasons = (
                "reduce_volume",
                [
                    "HRV is below the personal reference and resting HR is elevated; reduce workload while collecting a symptom note."
                ],
            )
        if sleep < 6:
            action, reasons = (
                "reduce_volume",
                [
                    "Recorded sleep was shorter than six hours; use a conservative volume adjustment."
                ],
            )
        alternatives = [
            {
                "action": "reduce_volume",
                "duration_factor": 0.7,
                "reason": "Keep the planned focus with less volume.",
            },
            {
                "action": "swap_session",
                "reason": "Choose an easy technical session or low-impact movement.",
            },
        ]
    taper = [
        e
        for e in ctx["events"]
        if e["priority"] == 1 and e["days_away"] <= e["taper_days"]
    ]
    if taper:
        reasons.append("A priority event is inside its configured taper window.")
        if action == "train_normally":
            action = "swap_session"
    subjective = ctx["subjective"][-1] if ctx["subjective"] else None
    if subjective and (subjective.get("pain") or subjective.get("felt_unwell")):
        action, reasons = (
            "recover",
            [
                "You reported pain or feeling unwell; avoid escalating training and seek appropriate help if symptoms persist."
            ],
        )
    availability = ctx["availability"][-1] if ctx["availability"] else None
    if availability and availability.get("minutes") == 0:
        action = "recover"
        reasons.append("Today is marked unavailable.")
    if availability and availability.get("minutes", 1440) > 0:
        reasons.append(
            (
                f"Il tempo disponibile per allenarti è di {availability['minutes']} minuti."
                if user.locale == "it"
                else f"Training time is limited to {availability['minutes']} minutes."
            )
        )
    if action == "recover":
        alternatives = [
            {
                "action": "recover",
                "reason": "Preserve rest and reassess symptoms and availability.",
            },
            {
                "action": "collect_more_data",
                "reason": "Record a symptom note and current evidence before returning to training.",
            },
        ]
    revision = await snapshot_revision(session, user.id)
    output = {
        "date": str(day),
        "action": action,
        "reasons": reasons[:4],
        "evidence": evidence,
        "constraints": ctx,
        "baselines": baselines,
        "data_completeness": {
            "fresh_signals": len(fresh),
            "required_signals": 3,
            "coverage_pct": round(len(fresh) / 3 * 100),
            "missing": missing,
        },
        "confidence": "limited" if missing else "supported_by_coverage",
        "model_confidence": None,
        "alternatives": alternatives,
        "counterfactual": "New current observations, a symptom check-in or changed availability/event constraints can change this decision.",
        "next_step": "Review a small session change before applying it."
        if ctx["sessions"]
        else "Record availability and choose an appropriately conservative session.",
        "formula_version": VERSION,
        "snapshot_revision": revision,
        "computed_at": now.isoformat(),
        "limitations": [
            "Conservative planning rules, not a diagnosis or performance/injury prediction.",
            "No proprietary readiness score is reconstructed.",
        ],
    }
    from app.services.lab_language import translate_decision

    output = translate_decision(output, user.locale)
    output.update(_interpretation(output, signals, user.locale))
    if persist:
        await scope_lock(session, user.id, "decision")
        row = await session.scalar(
            select(DecisionRecord).where(
                DecisionRecord.user_id == user.id,
                DecisionRecord.date == day,
                DecisionRecord.snapshot_revision == revision,
            )
        )
        if row is None:
            row = DecisionRecord(
                user_id=user.id, date=day, snapshot_revision=revision, output=output
            )
            session.add(row)
            await session.flush()
        output = {**output, "id": row.id, "outcome": row.outcome}
    return output
