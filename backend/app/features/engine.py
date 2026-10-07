"""Feature engine orchestrator (§7, §23 Phase 2).

Computes one user's daily_features + discipline_features for a given LOCAL
day (§17), then upserts by primary key — re-running for the same (user, day)
is always a safe overwrite (§6.4 correction path; §17 idempotency).

Day D's inputs (all keyed on the USER'S LOCAL calendar):
- activities with local_date in [D-28, D]  -> load series, strain ceiling,
  discipline rows for D
- sleep_sessions with local_date in [D-28, D]  -> sleep quality/architecture
  (D's session = that morning's wake-up) + respiration baseline
- hrv_readings mapped to local days via users.timezone  -> a single-origin/method/context HRV aggregate
- daily_biometrics rows in [D-28, D]  -> resting HR

Row honesty rules:
- A day with no wellness signal AND no activities gets no row (nothing was
  measured — fabricating a zero-day would be a lie). If a stale row exists
  for such a day (data was corrected away), the recompute deletes it.
- data_completeness is 'partial' when a wellness staple (HRV reading,
  resting HR, sleep session) is missing, or when an activity on D carries no
  HR signal at all (§17: incomplete sensor days are flagged, never silently
  scored as complete). Baseline warm-up (fewer than MIN_OBS observations)
  and a journal-free day do NOT flag partial — they are not sensor gaps.
  The systemic-stress signal's journal component (§7) activates on days the journal
  carries soreness/energy scores.
- iron_status_flag (§8.3 get_donation_status): the latest lab panel on/before
  D that carries a ferritin value decides — "low" below the panel's own
  reference low (or the configured default), "normal" otherwise, None when
  no ferritin result exists yet. Point-in-time honest: no invented decay
  windows; a newer panel updates the flag, an old one persists as "the
  latest known".
"""

import logging
import math
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features import baselines, discipline as discipline_metrics, load, scores
from app.connectors.semantics import provider_semantics
from app.features.weights import cutoff_for_local_day, load_weight_selection
from app.metrics.provenance import baseline_snapshot, metric_snapshot
from app.medical.labs import ferritin_reference_low
from app.models.activity import Activity, ActivityStream, Discipline
from app.models.features import DailyFeature, DisciplineFeature
from app.models.integration import Integration
from app.models.journal import JournalEntry
from app.models.medical import LabPanel
from app.models.user import User
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.services.sleep_summary import recorded_awake_totals, summary_awake

logger = logging.getLogger("features.engine")

WINDOW_DAYS = 28
DECAY_HALF_LIFE_DAYS = 3.0


def _local_day_instant_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC bounds of local `day`: [local midnight, next local midnight)."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(), end_local.astimezone()


def _strain_ceiling(
    loads: dict[date, float], day: date, window_days: int
) -> float:
    """P-16 audit: single shared strain-ceiling window function.

    Returns the peak daily load over [day - window_days + 1, day] inclusive.
    Both the nightly path (ceiling for today) and the recompute path
    (ceiling for the prior day) call this with the same window_days, so a
    given date always gets the same ceiling regardless of which path
    computed it — no more nightly-vs-backfill divergence at window edges.
    """
    return max(
        (loads.get(day - timedelta(days=i), 0.0) for i in range(window_days)),
        default=0.0,
    )


def _select_hrv_series(
    readings: list[HrvReading], tz: ZoneInfo, first_day: date, last_day: date,
    main_provider: str | None = None,
) -> tuple[dict[date, float], dict[date, dict]]:
    """One origin/method/measurement-context series for the assessed local day.

    A source or daytime/overnight change rebuilds baseline support. Legacy
    un-attributed rows form their own explicit context, never a known vendor's
    baseline. Device identity is not persisted and remains a limitation.
    """
    eligible = []
    for reading in readings:
        local_day = reading.timestamp.astimezone(tz).date()
        if not first_day <= local_day <= last_day:
            continue
        if reading.reading_type not in {"overnight_avg", "5min", "rmssd_overnight", "rmssd_5min"}:
            continue
        try:
            value = float(reading.hrv_ms)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value) or value <= 0:
            continue
        origin = getattr(reading, "origin", None)
        recorded_method = getattr(reading, "method", None)
        method = recorded_method.upper() if isinstance(recorded_method, str) else None
        if method is not None and method != "RMSSD":
            continue
        if origin is not None:
            rule = provider_semantics(origin, "hrv")
            if method != "RMSSD" or rule.canonical_metric != "hrv_overnight_rmssd":
                continue
        context = "overnight" if reading.reading_type in {"overnight_avg", "rmssd_overnight"} else "daytime"
        key = (origin, method or "legacy_unknown", context)
        eligible.append((reading, local_day, value, key))
    if not eligible:
        return {}, {}
    current = [item for item in eligible if item[1] == last_day]
    candidates = current or [item for item in eligible if item[1] == max(row[1] for row in eligible)]
    if current and main_provider and any(item[3][0] == main_provider for item in current):
        candidates = [item for item in current if item[3][0] == main_provider]
    # Prefer overnight within eligible candidate day/provider; remaining ties
    # use actual timestamp/row identity rather than database return order.
    selected_context = max(candidates, key=lambda item: (
        item[3][2] == "overnight", item[0].timestamp, item[3][0] or "", item[0].id or 0
    ))[3]
    grouped = {}
    for reading, local_day, value, key in eligible:
        if key == selected_context:
            grouped.setdefault(local_day, []).append((reading, value))
    values, provenance = {}, {}
    origin, method, context = selected_context
    for local_day, rows in grouped.items():
        numbers = [value for _, value in rows]
        values[local_day] = sum(numbers) / len(numbers) if context == "overnight" else statistics.median(numbers)
        provenance[local_day] = {
            "table": "hrv_readings", "provider": origin,
            "attribution": "recorded" if origin is not None else "unavailable",
            "measurement_method": method, "measurement_context": context,
            "device_identity": None, "aggregation": "mean_overnight" if context == "overnight" else "median_daytime",
            "observations": [{"id": reading.id, "timestamp": reading.timestamp.isoformat(),
                              "reading_type": reading.reading_type, "origin": getattr(reading, "origin", None),
                              "method": getattr(reading, "method", None)} for reading, _ in rows],
        }
    return values, provenance


def _readings_by_local_day(
    readings: list[HrvReading], tz: ZoneInfo, first_day: date, last_day: date,
    main_provider: str | None = None,
) -> dict[date, float]:
    return _select_hrv_series(readings, tz, first_day, last_day, main_provider)[0]


def _sleep_sessions_by_day(sessions: list[SleepSession], main_provider: str | None) -> dict[date, SleepSession]:
    """Choose one coherent source/night, never mixed vendor stage totals."""
    grouped = {}
    for sleep in sessions:
        grouped.setdefault(sleep.local_date, []).append(sleep)
    selected = {}
    for local_day, candidates in grouped.items():
        preferred = [sleep for sleep in candidates if main_provider and getattr(sleep, "origin", None) == main_provider]
        selected[local_day] = max(preferred or candidates, key=lambda sleep: (
            sleep.total_sleep_s or 0, sleep.start_time, sleep.id or 0
        ))
    return selected


async def _load_window(
    session: AsyncSession, user: User, day: date
) -> dict:
    """Everything the computation for `day` needs, in one round of queries."""
    tz = ZoneInfo(user.timezone)
    first_day = day - timedelta(days=WINDOW_DAYS)
    main_provider = None
    if getattr(user, "main_integration_id", None) is not None:
        main_provider = await session.scalar(select(Integration.provider).where(
            Integration.id == user.main_integration_id, Integration.user_id == user.id,
            Integration.status == "active",
        ))
    window_start_utc, _ = _local_day_instant_bounds(first_day, tz)
    _, day_end_utc = _local_day_instant_bounds(day, tz)

    activities = (
        (
            await session.scalars(
                select(Activity)
                .where(
                    Activity.user_id == user.id,
                    Activity.local_date >= first_day,
                    Activity.local_date <= day,
                )
                .order_by(Activity.start_time)
            )
        )
        .unique()
        .all()
    )
    activity_ids = [a.id for a in activities]
    streams: list[ActivityStream] = []
    if activity_ids:
        streams = (
            (
                await session.scalars(
                    select(ActivityStream).where(
                        ActivityStream.activity_id.in_(activity_ids)
                    )
                )
            )
            .unique()
            .all()
        )
    streams_by_activity: dict[int, list[ActivityStream]] = {}
    for stream in streams:
        streams_by_activity.setdefault(stream.activity_id, []).append(stream)

    sleep_sessions = (
        (
            await session.scalars(
                select(SleepSession).where(
                    SleepSession.user_id == user.id,
                    SleepSession.local_date >= first_day,
                    SleepSession.local_date <= day,
                )
            )
        )
        .unique()
        .all()
    )
    sleep_awake = await recorded_awake_totals(session, list(sleep_sessions))
    hrv_readings = (
        (
            await session.scalars(
                select(HrvReading).where(
                    HrvReading.user_id == user.id,
                    HrvReading.timestamp >= window_start_utc,
                    HrvReading.timestamp < day_end_utc,
                )
            )
        )
        .unique()
        .all()
    )
    biometrics = (
        (
            await session.scalars(
                select(DailyBiometric).where(
                    DailyBiometric.user_id == user.id,
                    DailyBiometric.date >= first_day,
                    DailyBiometric.date <= day,
                )
            )
        )
        .unique()
        .all()
    )
    # The systemic-stress signal's journal component (§7) needs ONLY day D's entries —
    # soreness/energy are same-day self-reports, no baseline involved. The
    # journal `date` is already the user's local date (§17), no conversion.
    journal_entries = (
        (
            await session.scalars(
                select(JournalEntry).where(
                    JournalEntry.user_id == user.id,
                    JournalEntry.date == day,
                )
            )
        )
        .unique()
        .all()
    )
    iron_panel = (
        (
            await session.scalars(
                select(LabPanel)
                .where(
                    LabPanel.user_id == user.id,
                    LabPanel.date <= day,
                    LabPanel.ferritin_ng_ml.is_not(None),
                )
                .order_by(LabPanel.date.desc(), LabPanel.id.desc())
                .limit(1)
            )
        )
        .unique()
        .first()
    )
    iron_threshold = (
        await ferritin_reference_low(session, iron_panel) if iron_panel else None
    )
    disciplines = {
        d.id: d for d in (await session.scalars(select(Discipline))).all()
    }
    hrv_values, hrv_provenance = _select_hrv_series(hrv_readings, tz, first_day, day, main_provider)
    return {
        "tz": tz, "main_provider": main_provider,
        "activities": activities,
        "streams_by_activity": streams_by_activity,
        "sleep_sessions": sleep_sessions,
        "sleep_awake": sleep_awake,
        "journal_entries": journal_entries,
        "iron_panel": iron_panel,
        "iron_threshold": iron_threshold,
        "hrv_by_local_day": hrv_values,
        "hrv_observation_provenance": hrv_provenance,
        "biometrics": {b.date: b for b in biometrics},
        "disciplines": disciplines,
    }


def _compute_day(user: User, day: date, window: dict) -> dict | None:
    """Pure computation for one local day. Returns None when nothing was
    measured that day (no row should exist)."""
    tz = window["tz"]
    activities = window["activities"]
    disciplines: dict[int, Discipline] = window["disciplines"]

    hrv_by_day: dict[date, float] = window["hrv_by_local_day"]
    from app.services.biometric_provenance import biometric_origin
    rhr_context = window["biometrics"].get(day)
    if rhr_context is None or rhr_context.resting_hr is None:
        rhr_context = max((b for b in window["biometrics"].values()
                           if b.date <= day and b.resting_hr is not None),
                          key=lambda b: b.date, default=None)
    rhr_origin = biometric_origin(rhr_context, "resting_hr") if rhr_context else None
    rhr_by_day: dict[date, float] = {
        b.date: float(b.resting_hr)
        for b in window["biometrics"].values()
        if b.resting_hr is not None and biometric_origin(b, "resting_hr") == rhr_origin
    }
    sleep_by_day = _sleep_sessions_by_day(window["sleep_sessions"], window.get("main_provider"))
    context_sleep = sleep_by_day.get(day) or max(sleep_by_day.values(), key=lambda sleep: sleep.local_date, default=None)
    sleep_origin = getattr(context_sleep, "origin", None)
    resp_by_day: dict[date, float] = {
        local_day: float(sleep.respiration_avg)
        for local_day, sleep in sleep_by_day.items()
        if sleep.respiration_avg is not None and getattr(sleep, "origin", None) == sleep_origin
    }

    # --- age & load series -------------------------------------------------
    hrm = load.hr_max_for(load.age_at(user.dob, day))
    activities_with_streams = [
        (a, window["streams_by_activity"].get(a.id, [])) for a in activities
    ]
    loads, selected_loads, load_metadata = load.consistent_window_loads(activities_with_streams, hrm)
    loads_by_discipline: dict[str, dict[date, float]] = {}
    for activity, _streams in activities_with_streams:
        if activity.discipline_id not in disciplines:
            continue
        name = disciplines[activity.discipline_id].name
        trimp = selected_loads.get(activity.id)
        if trimp is None:
            continue
        loads_by_discipline.setdefault(name, {})
        day_loads = loads_by_discipline[name]
        day_loads[activity.local_date] = (
            day_loads.get(activity.local_date, 0.0) + trimp
        )

    # A missing load source is not a measured rest day. A recorded-session
    # history permits descriptive zero for dates without recorded sessions;
    # sessions with no eligible load remain unknown rather than fabricated zero.
    load_available = bool(selected_loads)
    def load_on(local_day):
        sessions = [activity for activity in activities if activity.local_date == local_day]
        if sessions:
            return loads.get(local_day) if any(a.id in selected_loads for a in sessions) else None
        historical_evidence = any(a.id in selected_loads and a.local_date <= local_day for a in activities)
        return 0.0 if historical_evidence else None
    day_load = load_on(day)
    acute7 = load.rolling_sum(loads, day, 7) if load_available else None
    chronic28 = load.rolling_sum(loads, day, WINDOW_DAYS) if load_available else None
    chronic_weekly = chronic28 / 4.0 if chronic28 is not None else None
    acwr = load.acwr_from(acute7, chronic28) if load_available else None
    load_metadata["availability"] = "available" if load_available else "unavailable"
    if load_metadata["method"] == "edwards_trimp":
        load_metadata["hr_max_bpm"] = hrm
        load_metadata["hr_max_method"] = "tanaka_age_estimate" if hrm is not None else "unavailable"
        load_metadata["limitation"] += " HRmax is an age-based estimate, not an individually measured maximum."
    load_metadata["zero_day_assumption"] = "No recorded session is a descriptive zero only after selected-method session evidence; absent capture is not verified rest."

    # --- baselines (prior window [D-28, D-1], D excluded) -------------------
    hrv_baseline = baselines.mean_baseline(hrv_by_day, day)
    rhr_baseline = baselines.mean_baseline(rhr_by_day, day)
    resp_baseline = baselines.mean_baseline(resp_by_day, day)

    hrv_dev = (
        None
        if hrv_baseline is None or hrv_baseline <= 0 or day not in hrv_by_day
        else (hrv_by_day[day] - hrv_baseline) / hrv_baseline * 100.0
    )
    rhr_dev = (
        None
        if rhr_baseline is None or day not in rhr_by_day
        else rhr_by_day[day] - rhr_baseline
    )
    resp_dev = (
        None
        if resp_baseline is None or resp_baseline <= 0 or day not in resp_by_day
        else (resp_by_day[day] - resp_baseline) / resp_baseline * 100.0
    )

    # --- strain & ceiling ---------------------------------------------------
    # P-16 audit: shared strain-ceiling window function — both nightly and
    # recompute paths use the SAME window definition ([D-27, D] inclusive
    # for today's ceiling; [D-28, D-1] inclusive for prior day's ceiling).
    # The previous code had an off-by-one between nightly and recompute that
    # produced two different strain values for the same date.
    peak28 = _strain_ceiling(loads, day, WINDOW_DAYS)
    prior_day = day - timedelta(days=1)
    prior_peak = _strain_ceiling(loads, prior_day, WINDOW_DAYS)
    prior_day_load = load_on(prior_day)
    prior_strain = scores.strain_score(prior_day_load, prior_peak)

    # --- weights (§6.4 selection rule; loaded by the async caller with
    # cutoff = start of local day D) -----------------------------------------
    w = window["weights"]

    sleep_session = sleep_by_day.get(day)
    strain = scores.strain_score(day_load, peak28)
    sleep_inputs = {
        "rem_pct": (
            float(sleep_session.rem_s) / float(sleep_session.total_sleep_s) * 100.0
            if sleep_session and sleep_session.rem_s is not None and sleep_session.total_sleep_s
            else None
        ),
        "deep_pct": (
            float(sleep_session.deep_s) / float(sleep_session.total_sleep_s) * 100.0
            if sleep_session and sleep_session.deep_s is not None and sleep_session.total_sleep_s
            else None
        ),
        "total_sleep_s": (
            float(sleep_session.total_sleep_s)
            if sleep_session and sleep_session.total_sleep_s is not None else None
        ),
        "awake_s": summary_awake(
            sleep_session, window.get("sleep_awake", {}).get(sleep_session.start_time)
        ) if sleep_session else None,
    }
    sleep_architecture = scores.sleep_architecture_score(
        w["sleep_architecture_score"], **sleep_inputs
    )
    # Proprietary vendor sleep scores have incompatible meanings. Recovery
    # consumes the actual Apex architecture composite from one coherent night.
    sleep_quality = sleep_architecture
    recovery = scores.recovery_score(
        w["recovery_score"], hrv_dev, rhr_dev, sleep_quality, prior_strain
    )
    readiness = scores.readiness_score(
        w["readiness_score"], recovery, sleep_architecture, acwr
    )
    # §7 journal component: day-level mean over the entries that carry each
    # score (entries lacking soreness/energy are simply not averaged in).
    day_journals = window.get("journal_entries", [])
    soreness_values = [
        float(e.soreness_score) for e in day_journals if e.soreness_score is not None
    ]
    energy_values = [
        float(e.energy_score) for e in day_journals if e.energy_score is not None
    ]
    journal_component = scores.journal_soreness_fatigue_component(
        (sum(soreness_values) / len(soreness_values)) if soreness_values else None,
        (sum(energy_values) / len(energy_values)) if energy_values else None,
    )
    systemic_stress = scores.systemic_stress_signal(
        w["systemic_stress_signal"], hrv_dev, rhr_dev, resp_dev, journal_component
    )
    mean28, std28 = load.load_distribution(loads, day) if load_available else (None, None)
    # P-13 audit: gate the load-spike load-spike component on a minimum
    # active-day count so an athlete returning from a 4-week break does not
    # maximize the indicator on their first normal session.
    active_days = load.active_day_count(loads, day)
    load_spike = scores.load_spike_indicator(
        w["load_spike_indicator"], acwr, day_load, mean28, std28, active_days=active_days
    )
    cdfi = scores.cross_discipline_fatigue_index(loads_by_discipline, day)

    # --- honesty flags (§17) ------------------------------------------------
    # partial = a wellness staple is missing, or an activity on D carries no
    # HR signal at all (no stream HR and no avg_hr). Baseline warm-up and the
    # structural journal gap are NOT sensor gaps.
    missing_wellness = (
        day not in hrv_by_day or day not in rhr_by_day or sleep_session is None
    )
    activity_hr_gaps = any(
        not any(st.hr is not None for st in streams) and activity.avg_hr is None
        for activity, streams in activities_with_streams
        if activity.local_date == day
    )
    data_completeness = (
        "partial" if (missing_wellness or activity_hr_gaps or load_metadata["excluded_sessions"]) else "full"
    )

    # iron_status_flag: latest known ferritin as of D (see module docstring).
    iron_panel = window.get("iron_panel")
    iron_threshold = window.get("iron_threshold")
    if iron_panel is not None and iron_threshold is not None:
        iron_flag = (
            "low"
            if float(iron_panel.ferritin_ng_ml) < float(iron_threshold)
            else "normal"
        )
    else:
        iron_flag = None

    daily_row = {
        "user_id": user.id,
        "date": day,
        "recovery_score": recovery,
        "strain_score": strain,
        "readiness_score": readiness,
        "load_metadata": load_metadata,
        "training_load_acute": acute7,
        "training_load_chronic": chronic_weekly,
        "acwr": acwr,
        "sleep_architecture_score": sleep_architecture,
        "hrv_deviation_from_baseline": hrv_dev,
        "systemic_stress_signal": systemic_stress,
        "load_spike_indicator": load_spike,
        "iron_status_flag": iron_flag,
        "cross_discipline_fatigue_index": cdfi,
        "data_completeness": data_completeness,
    }

    # Persist the actual calculation operands during computation. Legacy rows
    # have no such record and must never acquire reconstructed contributors.
    baseline_records = {
        "hrv": baseline_snapshot(hrv_by_day, day, hrv_baseline),
        "resting_hr": baseline_snapshot(rhr_by_day, day, rhr_baseline),
        "respiration": baseline_snapshot(resp_by_day, day, resp_baseline),
    }
    unknown_sensor = {"provider": None, "attribution": "unavailable",
                      "reason": "Selected provider is unavailable for this legacy or un-attributed canonical observation."}
    hrv_source = window.get("hrv_observation_provenance", {}).get(day, {
        **unknown_sensor, "table": "hrv_readings", "measurement_method": "legacy_method_unavailable",
    })
    rhr_source = {**unknown_sensor, "provider": rhr_origin,
                  "attribution": "recorded" if rhr_origin else "unavailable",
                  "table": "daily_biometrics", "field": "resting_hr", "date": day.isoformat()}
    sleep_provider = getattr(sleep_session, "origin", None) if sleep_session else None
    sleep_source = {"provider": sleep_provider, "attribution": "recorded" if sleep_provider else "unavailable",
                    "table": "sleep_sessions", "id": sleep_session.id if sleep_session else None,
                    "start_time": sleep_session.start_time.isoformat() if sleep_session else None,
                    "measurement_method": "vendor_estimated_sleep_stages", "device_identity": None}
    for name, record in baseline_records.items():
        record["sources_by_day"] = {}
        for observation in record["observations"]:
            observed_day = date.fromisoformat(observation)
            if name == "hrv":
                source = window.get("hrv_observation_provenance", {}).get(observed_day, unknown_sensor)
            elif name == "resting_hr":
                source = {**rhr_source, "date": observation}
            else:
                observed_sleep = sleep_by_day[observed_day]
                provider = getattr(observed_sleep, "origin", None)
                source = {"table": "sleep_sessions", "provider": provider, "id": observed_sleep.id,
                          "attribution": "recorded" if provider else "unavailable"}
            record["sources_by_day"][observation] = source
    load_source = {"provider": "garmin" if load_metadata["method"] == "garmin_recorded" else None,
                   "attribution": "recorded_method", "method": load_metadata["method"],
                   "unit": load_metadata["unit"], "included_sessions": load_metadata["included_sessions"],
                   "excluded_sessions": load_metadata["excluded_sessions"],
                   "hr_max_bpm": load_metadata.get("hr_max_bpm"),
                   "hr_max_method": load_metadata.get("hr_max_method"),
                   "observations": [{"activity_id": activity.id, "date": activity.local_date.isoformat(),
                                     "value": selected_loads[activity.id]}
                                    for activity in activities if activity.id in selected_loads],
                   "excluded_activity_ids": [activity.id for activity in activities if activity.id not in selected_loads]}
    selections = window.get("weight_selection", {})
    def composite(metric, value, feature, inputs, components, baseline_names=()):
        return metric_snapshot(
            metric, value, inputs, components=components, weights=w[feature],
            weight_selection=selections.get(feature),
            baselines={name: baseline_records[name] for name in baseline_names},
            sources={name: {"attribution": "apex_derived", "metric": "sleep_score" if name == "sleep_quality" else name}
                     if name in {"recovery", "sleep_architecture", "sleep_quality", "acwr", "prior_day_strain"}
                     else load_source if name in {"day_load", "mean28", "std28", "active_days"}
                     else {"attribution": "self_report", "provider": "journal"}
                     if name == "journal_soreness_fatigue"
                     else hrv_source if name in {"hrv_deviation", "hrv_drop"}
                     else rhr_source if name in {"resting_hr_deviation", "resting_hr_elevation"}
                     else sleep_source
                     for name in inputs},
        )
    provenance_metrics = {
        "recovery": composite(
            "recovery", recovery, "recovery_score",
            {"hrv_deviation": hrv_dev, "resting_hr_deviation": rhr_dev,
             "sleep_quality": sleep_quality, "prior_day_strain": prior_strain},
            scores.recovery_components(hrv_dev, rhr_dev, sleep_quality, prior_strain),
            ("hrv", "resting_hr"),
        ),
        "sleep_score": composite(
            "sleep_score", sleep_architecture, "sleep_architecture_score", sleep_inputs,
            scores.sleep_architecture_components(**sleep_inputs),
        ),
        "readiness": composite(
            "readiness", readiness, "readiness_score",
            {"recovery": recovery, "sleep_architecture": sleep_architecture, "acwr": acwr},
            scores.readiness_components(recovery, sleep_architecture, acwr),
        ),
        "systemic_stress": composite(
            "systemic_stress", systemic_stress, "systemic_stress_signal",
            {"hrv_drop": hrv_dev, "resting_hr_elevation": rhr_dev,
             "respiration_elevation": resp_dev, "journal_soreness_fatigue": journal_component},
            scores.systemic_stress_components(hrv_dev, rhr_dev, resp_dev, journal_component),
            ("hrv", "resting_hr", "respiration"),
        ),
        "load_spike": composite(
            "load_spike", load_spike, "load_spike_indicator",
            {"acwr": acwr, "day_load": day_load, "mean28": mean28,
             "std28": std28, "active_days": active_days},
            scores.load_spike_components(acwr, day_load, mean28, std28, active_days=active_days),
        ),
    }
    prior_strain_snapshot = metric_snapshot(
        "strain", prior_strain,
        {"day_load": prior_day_load, "peak28": prior_peak,
         "ceiling_floor": load.STRAIN_CEILING_FLOOR},
        sources={"day_load": load_source, "peak28": load_source,
                 "ceiling_floor": {"attribution": "formula_constant", "formula_version": "strain-v1"}},
        methodology={"as_of": prior_day.isoformat(), "window_start": (prior_day - timedelta(days=27)).isoformat(),
                     "window_end": prior_day.isoformat()},
    )
    provenance_metrics["recovery"]["methodology"] = {
        "prior_day_strain": prior_strain_snapshot, "sleep_quality_metric": "sleep_score",
        "source_policy": "apex_architecture_not_proprietary_sleep_score",
    }
    provenance_metrics["systemic_stress"]["methodology"] = {
        "journal_soreness_mean": sum(soreness_values) / len(soreness_values) if soreness_values else None,
        "journal_energy_mean": sum(energy_values) / len(energy_values) if energy_values else None,
        "soreness_observations": len(soreness_values), "energy_observations": len(energy_values),
    }
    provenance_metrics["load_spike"]["baselines"] = {
        "load_distribution": {"value": mean28, "population_std": std28, "active_days": active_days,
                              "window_days": 28, "window_start": (day - timedelta(days=28)).isoformat(),
                              "window_end": (day - timedelta(days=1)).isoformat(),
                              "aggregation": "zero_filled_recorded_load_days",
                              "required_active_days": 7, "sufficient": active_days >= 7,
                              "gate_behavior": "component_unavailable_below_7_active_days"}
    }
    for metric, value, inputs in (
        ("acute_load", acute7, {"daily_loads": {d.isoformat(): v for d, v in loads.items()
                                               if day - timedelta(days=6) <= d <= day}}),
        ("chronic_load", chronic_weekly, {"daily_loads": {d.isoformat(): v for d, v in loads.items()
                                                        if day - timedelta(days=27) <= d <= day},
                                          "weekly_scale_divisor": 4.0}),
        ("acwr", acwr, {"acute_load": acute7, "chronic_load": chronic_weekly}),
        ("strain", strain, {"day_load": day_load, "peak28": peak28,
                             "ceiling_floor": load.STRAIN_CEILING_FLOOR}),
        ("cross_discipline_fatigue", cdfi,
         {"discipline_daily_loads": {name: {d.isoformat(): v for d, v in values.items()
                                              if day - timedelta(days=27) <= d <= day}
                                     for name, values in loads_by_discipline.items()},
          "half_life_days": 3.0, "normalization_floor": 1.0}),
    ):
        provenance_metrics[metric] = metric_snapshot(
            metric, value, inputs,
            sources={name: {"attribution": "formula_constant", "formula_version": f"{metric}-v1"}
                     if name in {"ceiling_floor", "half_life_days", "normalization_floor", "weekly_scale_divisor"}
                     else load_source for name in inputs}, methodology=dict(load_metadata)
        )
    for metric, value, today_value, baseline_value, baseline_name in (
        ("hrv_deviation", hrv_dev, hrv_by_day.get(day), hrv_baseline, "hrv"),
        ("resting_hr_deviation", rhr_dev, rhr_by_day.get(day), rhr_baseline, "resting_hr"),
        ("respiration_deviation", resp_dev, resp_by_day.get(day), resp_baseline, "respiration"),
    ):
        provenance_metrics[metric] = metric_snapshot(
            metric, value, {"today": today_value, "baseline": baseline_value},
            baselines={baseline_name: baseline_records[baseline_name]},
            sources={"today": hrv_source if baseline_name == "hrv" else rhr_source if baseline_name == "resting_hr" else sleep_source,
                     "baseline": {"attribution": "apex_derived", "metric": f"{baseline_name}_baseline"}},
        )
    provenance_metrics["hrv_baseline"] = metric_snapshot(
        "hrv_baseline", hrv_baseline, {"observed_days": baseline_records["hrv"]["observed_days"]},
        baselines={"hrv": baseline_records["hrv"]}, sources={"hrv": hrv_source},
    )
    daily_row["calculation_provenance"] = {
        "schema_version": 1, "as_of": day.isoformat(), "timezone": str(tz),
        "metrics": provenance_metrics,
    }

    # --- discipline rows for D (§17: scoped by discipline, never pooled) ---
    per_discipline: dict[int, dict[str, list[float]]] = {}
    ftp_estimates: dict[int, list[float]] = {}
    for activity, streams in activities_with_streams:
        if activity.local_date != day:
            continue
        if activity.discipline_id not in disciplines:
            continue
        disc = disciplines[activity.discipline_id]
        values = per_discipline.setdefault(activity.discipline_id, {})
        decoupling = discipline_metrics.aerobic_decoupling(activity, streams)
        if decoupling is not None:
            values.setdefault("decoupling", []).append(decoupling)
        ef = discipline_metrics.efficiency_factor(activity, streams, disc.name)
        if ef is not None:
            values.setdefault("ef", []).append(ef)
        ftp = discipline_metrics.ftp_estimate(activity, streams, disc.ftp_model_type)
        if ftp is not None:
            ftp_estimates.setdefault(activity.discipline_id, []).append(ftp)

    discipline_rows = []
    for discipline_id, values in per_discipline.items():
        decoupling = (
            sum(values["decoupling"]) / len(values["decoupling"])
            if "decoupling" in values
            else None
        )
        ef = sum(values["ef"]) / len(values["ef"]) if "ef" in values else None
        ftp = (
            max(ftp_estimates[discipline_id])
            if discipline_id in ftp_estimates
            else None
        )
        if decoupling is None and ef is None and ftp is None:
            continue
        discipline_rows.append(
            {
                "user_id": user.id,
                "discipline_id": discipline_id,
                "date": day,
                "estimated_ftp": ftp,
                "aerobic_decoupling_pct": decoupling,
                "efficiency_factor": ef,
            }
        )
    for discipline_id, estimates in ftp_estimates.items():
        if any(row["discipline_id"] == discipline_id for row in discipline_rows):
            continue
        discipline_rows.append(
            {
                "user_id": user.id,
                "discipline_id": discipline_id,
                "date": day,
                "estimated_ftp": max(estimates),
                "aerobic_decoupling_pct": None,
                "efficiency_factor": None,
            }
        )

    has_wellness = (
        day in hrv_by_day
        or day in rhr_by_day
        or sleep_session is not None
        or day in resp_by_day
    )
    has_activities = any(a.local_date == day for a in activities)
    if not has_wellness and not has_activities:
        return None
    return {"daily": daily_row, "discipline_rows": discipline_rows}


async def compute_user_day(
    session: AsyncSession, user: User, day: date
) -> dict | None:
    """Compute + upsert one local day. Returns the computed rows (or None if
    the day had no data and no row exists)."""
    from app.services.evidence import scope_lock
    await scope_lock(session, user.id, "changes")
    window = await _load_window(session, user, day)
    tz = window["tz"]
    cutoff = cutoff_for_local_day(day, tz)
    window["weight_selection"] = {
        feature: await load_weight_selection(session, feature, cutoff)
        for feature in (
            "recovery_score", "readiness_score", "sleep_architecture_score",
            "systemic_stress_signal", "load_spike_indicator",
        )
    }
    window["weights"] = {
        feature: {component: row["value"] for component, row in selected.items()}
        for feature, selected in window["weight_selection"].items()
    }
    computed = _compute_day(user, day, window)
    if computed is None:
        existing = await session.get(DailyFeature, {"user_id": user.id, "date": day})
        if existing is not None:
            await session.delete(existing)
        await session.execute(delete(DisciplineFeature).where(DisciplineFeature.user_id == user.id, DisciplineFeature.date == day))
        await session.commit()
        return None
    await _upsert_rows(session, user.id, [computed])
    return computed


async def compute_user_range(
    session: AsyncSession, user: User, start: date, end: date
) -> dict:
    """Recompute a closed local-date range (the §6.4 correction path:
    'fix the feature_weights row, then manually re-run the nightly
    feature-engine task for the affected date range'). Idempotent per day."""
    if end < start or (end - start).days > 365:
        raise ValueError("Recompute requires a closed range of at most 366 days")
    computed_days = 0
    discipline_rows_written = 0
    day = start
    while day <= end:
        result = await compute_user_day(session, user, day)
        if result is not None:
            computed_days += 1
            discipline_rows_written += len(result["discipline_rows"])
        day += timedelta(days=1)
    return {
        "user_id": user.id,
        "start": start,
        "end": end,
        "days_computed": computed_days,
        "discipline_rows_written": discipline_rows_written,
    }


def _num(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(repr(round(value, 6)))


async def _upsert_rows(
    session: AsyncSession, user_id: int, computed: list[dict]
) -> None:
    for result in computed:
        daily = result["daily"]
        stmt = pg_insert(DailyFeature).values(
            **{
                key: (_num(value) if isinstance(value, float) else value)
                for key, value in daily.items()
            }
        )
        update_cols = {
            col.name: stmt.excluded[col.name]
            for col in DailyFeature.__table__.columns
            if col.name not in ("user_id", "date")
        }
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "date"], set_=update_cols
            )
        )
        await session.execute(delete(DisciplineFeature).where(DisciplineFeature.user_id == user_id, DisciplineFeature.date == daily["date"]))
        for row in result["discipline_rows"]:
            stmt_d = pg_insert(DisciplineFeature).values(
                **{
                    key: (_num(value) if isinstance(value, float) else value)
                    for key, value in row.items()
                }
            )
            update_cols_d = {
                col.name: stmt_d.excluded[col.name]
                for col in DisciplineFeature.__table__.columns
                if col.name not in ("user_id", "discipline_id", "date")
            }
            await session.execute(
                stmt_d.on_conflict_do_update(
                    index_elements=["user_id", "discipline_id", "date"],
                    set_=update_cols_d,
                )
            )
    await session.commit()
