"""N-of-1 associations with matched weekdays and explicit exclusions."""

from datetime import date, timedelta
from statistics import median
from sqlalchemy import select
from app.models.lab import AthleteEntry
from app.services.evidence import EvidenceError, query_observations


async def experiment_analysis(session, user, ident, *, for_ai=False):
    experiment = await session.scalar(
        select(AthleteEntry).where(
            AthleteEntry.user_id == user.id,
            AthleteEntry.id == ident,
            AthleteEntry.kind == "experiment",
        )
    )
    if experiment is None:
        raise EvidenceError("NOT_FOUND", "Experiment not found")
    spec = experiment.payload
    end = date.fromisoformat(spec["end_date"])
    lag = spec.get("outcome_lag_days", 1)
    rows = await query_observations(
        session,
        user.id,
        spec["outcome_metric"],
        experiment.date,
        end + timedelta(days=lag),
        for_ai=for_ai,
        origin=spec["origin"],
    )
    devices = (
        await session.scalars(
            select(AthleteEntry).where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind == "device_change",
                AthleteEntry.payload["metrics"].contains([spec["outcome_metric"]]),
            )
        )
    ).all()
    last_change = max(
        (d.date for d in devices if d.date <= end), default=experiment.date
    )
    rows = [r for r in rows if r.local_date >= last_change]
    daily = {
        r.local_date: r for r in rows if isinstance(r.value.get("value"), (int, float))
    }
    logs = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user.id,
                AthleteEntry.kind == "experiment_checkin",
                AthleteEntry.date.between(experiment.date, end),
            )
            .order_by(AthleteEntry.id)
        )
    ).all()
    selected = {r.date: r for r in logs if r.payload["experiment_id"] == ident}
    exposed, control, exclusions = [], [], []
    for day, log in selected.items():
        value = daily.get(day + timedelta(days=lag))
        if log.payload["confounders"] or value is None:
            exclusions.append(
                {
                    "date": str(day),
                    "reason": "reported_confounder"
                    if log.payload["confounders"]
                    else "missing_outcome",
                }
            )
        else:
            (exposed if log.payload["exposed"] else control).append((day, value))
    pairs, unused = [], list(control)
    for day, value in exposed:
        matches = [
            (i, row)
            for i, row in enumerate(unused)
            if row[0].weekday() == day.weekday()
            and row[1].metadata_json.get("device_id")
            == value.metadata_json.get("device_id")
            and row[1].metadata_json.get("reading_context")
            == value.metadata_json.get("reading_context")
        ]
        if not matches:
            exclusions.append(
                {"date": str(day), "reason": "no_weekday_matched_control"}
            )
            continue
        i, (control_day, control_value) = min(
            matches, key=lambda pair: abs((pair[1][0] - day).days)
        )
        unused.pop(i)
        pairs.append(
            {
                "exposed_date": str(day),
                "control_date": str(control_day),
                "difference": value.value["value"] - control_value.value["value"],
                "evidence_ids": [
                    f"observation:{r.id}:{r.revision}" for r in (value, control_value)
                ],
            }
        )
    differences = [p["difference"] for p in pairs]
    return {
        "experiment_id": ident,
        "title": spec["title"],
        "metric": spec["outcome_metric"],
        "state": "exploratory" if len(pairs) >= 8 else "INSUFFICIENT_DATA",
        "sample_count": len(pairs),
        "minimum_pairs": 8,
        "pairs": pairs,
        "exclusions": exclusions,
        "median_matched_difference": median(differences) if len(pairs) >= 8 else None,
        "observed_difference_range": [min(differences), max(differences)]
        if len(pairs) >= 8
        else None,
        "causal": False,
        "limitations": [
            "Observational association, not causal evidence.",
            "Matching weekdays cannot remove unreported confounders, seasonality or self-selection.",
            "An observed range is not a calibrated confidence interval.",
        ],
    }
