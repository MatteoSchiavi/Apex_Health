"""Transactional HealthKit ledger and source-owned derived projections.

No payloads or credentials are logged. The immutable account-scoped UUID
ledger remains the replay authority; deletions become permanent tombstones.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import DateTime, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.healthkit import HealthKitBatch, HealthKitPairing, HealthKitSample
from app.models.lab import FeedState, Observation
from app.models.watch import DeviceToken
from app.models.wellness import DailyBiometric, SleepSession
from app.schemas.healthkit import HealthKitDelta, SLEEP_TYPE, WORKOUT_TYPE
from app.services.apple_health_import import _priority_samples, _sleep_priority, _sleep_totals, _step_total
from app.services.device_merge import resolve_activity_winner
from app.services.biometric_provenance import biometric_origin, set_biometric
from app.services.evidence import METRICS, digest, record_observation, scope_lock

SOURCE = "apple_healthkit"
# HKWorkoutActivityType numeric enum values, never invented sport names.
SPORTS = {13: "road_cycling", 16: "gym_general", 20: "strength", 24: "hiking",
          35: "rowing", 37: "running", 46: "swimming", 50: "strength",
          52: "walking", 57: "yoga", 60: "skiing", 61: "skiing", 63: "gym_general", 67: "snowboard"}
SLEEP_CATEGORIES = {0: "InBed", 1: "AsleepUnspecified", 2: "Awake", 3: "Core", 4: "Deep", 5: "REM"}
# Equivalent registry metrics only. SDNN and wrist temperature have dedicated
# provider contexts and cannot masquerade as RMSSD/body temperature.
DAILY = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate_samples_bpm", None, None, "bpm", "mean"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_hr_bpm", "resting_hr", "resting_hr", "bpm", "latest"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_sdnn_ms", None, None, "ms", "mean"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "steps", "steps", "steps", "sum"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_energy_kcal", None, None, "kcal", "sum"),
    "HKQuantityTypeIdentifierBodyMass": ("weight_kg", "weight_kg", "weight", "kg", "latest"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_pct", "body_fat_pct", "body_fat", "%", "latest"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiration", None, "respiration", "br/min", "mean"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2_pct", "spo2_avg", "spo2", "%", "mean"),
    "HKQuantityTypeIdentifierVO2Max": ("vo2max", "vo2max", "vo2max", "ml/kg/min", "latest"),
    "HKQuantityTypeIdentifierBodyTemperature": ("body_temperature_c", None, "temperature", "°C", "latest"),
    "HKQuantityTypeIdentifierBasalBodyTemperature": ("basal_body_temperature_c", None, None, "degC", "latest"),
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": ("sleeping_wrist_temperature_c", None, None, "degC", "mean"),
}


def _source(payload):
    # Bundle/device keep different producers with identical display names apart.
    return "|".join((payload["source_name"], payload["source_bundle"], payload.get("device") or ""))


def _time(payload, key):
    return datetime.fromisoformat(payload[key])


def _ledger_payload(sample, timezone):
    payload = sample.model_dump(mode="json")
    # Canonicalize instants for immutable comparison across equivalent offsets.
    payload["start_at"] = sample.start_at.astimezone(UTC).isoformat()
    payload["end_at"] = sample.end_at.astimezone(UTC).isoformat()
    payload["local_date"] = sample.start_at.astimezone(timezone).date().isoformat()
    payload["end_local_date"] = sample.end_at.astimezone(timezone).date().isoformat()
    return payload


async def _invalidate(session, user_id, record_ids):
    if record_ids:
        rows = (await session.scalars(select(Observation).where(
            Observation.user_id == user_id, Observation.origin == SOURCE,
            Observation.source_record_id.in_(record_ids), Observation.current.is_(True),
        ))).all()
        for row in rows:
            if row.availability == "deleted":
                continue
            tombstone = await record_observation(session, user_id=user_id, metric=row.metric,
                value=None, unit=row.unit, origin=SOURCE, source_record_id=row.source_record_id,
                measured_at=row.measured_at, timezone=row.timezone, fetched_at=datetime.now(UTC),
                acquisition="device_sync", metadata={"deleted": True})
            tombstone.availability = "deleted"


async def _evidence(session, user, metric, value, unit, ident, measured_at, metadata, now):
    if metric in METRICS:
        await record_observation(session, user_id=user.id, metric=metric, value=value,
            unit=unit, origin=SOURCE, source_record_id=ident, measured_at=measured_at,
            timezone=user.timezone, fetched_at=now, acquisition="device_sync", metadata=metadata)


async def _daily_projections(session, user, days, now):
    if not days:
        return
    payloads = (await session.scalars(select(HealthKitSample.payload).where(
        HealthKitSample.user_id == user.id, HealthKitSample.deleted.is_(False),
        HealthKitSample.payload["local_date"].astext.in_([d.isoformat() for d in days]),
    ))).all()
    groups = defaultdict(lambda: defaultdict(list))
    for p in payloads:
        if p["type"] in DAILY:
            groups[date.fromisoformat(p["local_date"])][p["type"]].append(
                (_time(p, "start_at"), _time(p, "end_at"), p["value"], _source(p), p["uuid"]))
    for day in sorted(days):
        bio = await session.scalar(select(DailyBiometric).where(DailyBiometric.user_id == user.id,
            DailyBiometric.date == day).with_for_update().execution_options(populate_existing=True))
        if bio is None:
            bio = DailyBiometric(user_id=user.id, date=day)
            session.add(bio)
        metrics = dict(bio.source_metrics or {})
        old = dict(metrics.get(SOURCE) or {})
        suppliers = dict(old.get("canonical_supplier_fields") or {})
        other_sources = sorted(key for key in metrics if key != SOURCE and not key.startswith("_"))
        other_source_hash = digest({key: metrics[key] for key in other_sources})
        projection = {key: value for key, value in old.items() if key in {"sleep", "sleep_projection_ids"}}
        new_suppliers = {}
        for typ, (key, field, metric, unit, method) in DAILY.items():
            samples, source = _priority_samples(groups[day][typ])
            record_id = f"daily:{day}:{key}"
            value = None
            if samples:
                if method == "sum":
                    value, _ = _step_total([row[:4] for row in samples])
                elif method == "latest":
                    value = max(samples, key=lambda row: (row[0], row[4]))[2]
                else:
                    value = sum(row[2] for row in samples) / len(samples)
                if field in {"steps", "resting_hr"}:
                    value = round(value)
                projection[key] = {"value": value, "unit": unit, "method": method,
                    "source": source, "samples": len(samples), "start": min(row[0] for row in samples).isoformat(),
                    "end": max(row[1] for row in samples).isoformat()}
                await _evidence(session, user, metric, value, unit, record_id,
                    max(row[0] for row in samples), {"aggregation": method, "sample_type": typ,
                    "source_identity": source, "samples": len(samples)}, now)
            elif key in old:
                await _invalidate(session, user.id, [record_id])
            if field:
                current = getattr(bio, field)
                supplier = suppliers.get(field)
                # Only an attributed actual write proves ownership. Equal-value
                # refreshes by another provider transfer the supplier marker.
                own = biometric_origin(bio, field) == SOURCE and supplier is not None and current is not None and float(current) == supplier["value"]
                if current is None or own:
                    set_biometric(bio, field, None if value is None else value if field in {"steps", "resting_hr"} else Decimal(str(value)), SOURCE)
                    if value is not None:
                        new_suppliers[field] = {"value": value, "other_sources": other_sources, "other_source_hash": other_source_hash}
                elif supplier:
                    projection.setdefault("projection_limitations", []).append(f"{field}: supplier changed; preserved current value")
        projection["canonical_supplier_fields"] = new_suppliers
        # The per-field setter may have changed ownership while this projection
        # was assembled. Preserve that authoritative map when writing summaries.
        metrics = dict(bio.source_metrics or {})
        metrics[SOURCE] = projection
        bio.source_metrics = metrics
    await session.flush()


async def _sleep_projections(session, user, days, now):
    if not days:
        return
    tz = ZoneInfo(user.timezone)
    search_days = {day + timedelta(days=shift) for day in days for shift in range(-3, 4)}
    payloads = (await session.scalars(select(HealthKitSample.payload).where(
        HealthKitSample.user_id == user.id, HealthKitSample.deleted.is_(False),
        HealthKitSample.payload["type"].astext == SLEEP_TYPE,
        HealthKitSample.payload["end_local_date"].astext.in_([d.isoformat() for d in search_days]),
    ))).all()
    # Pick a producer per end day before overlap arbitration; never combine
    # competing vendor stages. Episodes preserve wake-day semantics and naps.
    by_end_day = defaultdict(list)
    for p in payloads:
        by_end_day[p["end_local_date"]].append((_time(p, "start_at"), _time(p, "end_at"), SLEEP_CATEGORIES[int(p["value"])], _source(p)))
    selected = []
    for entries in by_end_day.values():
        rows, _ = _priority_samples(entries)
        selected.extend(rows)
    by_source = defaultdict(list)
    for row in selected:
        by_source[row[3]].append(row)
    episodes = []
    for source, rows in by_source.items():
        source_episodes = []
        for row in sorted(rows):
            if not source_episodes or (row[0] - max(e[1] for e in source_episodes[-1])).total_seconds() >= 7200 or row[1] - source_episodes[-1][0][0] > timedelta(hours=48):
                source_episodes.append([row])
            else:
                source_episodes[-1].append(row)
        for entries in source_episodes:
            asleep = [row for row in entries if _sleep_priority(row[2])[0] > 1]
            if not asleep:
                continue
            start, end = min(row[0] for row in asleep), max(row[1] for row in asleep)
            day = end.astimezone(tz).date()
            if day in days:
                totals = _sleep_totals([row[:3] for row in entries])
                episodes.append((day, start, end, totals, source))
    await session.execute(delete(SleepSession).where(SleepSession.user_id == user.id,
        SleepSession.origin == SOURCE, SleepSession.local_date.in_(days)))
    by_day = defaultdict(list)
    for episode in episodes:
        by_day[episode[0]].append(episode)
    for day in sorted(days):
        # Source arbitration again at actual episode wake date, so midnight
        # category intervals cannot introduce competing-source night totals.
        selected_episodes, source = _priority_samples(by_day[day], source_index=4)
        summaries = []
        for _, start, end, totals, _ in selected_episodes:
            total = totals["deep"] + totals["core"] + totals["rem"] + totals["asleep"]
            summaries.append({"start": start.isoformat(), "end": end.isoformat(), "total_sleep_s": total or None, "stages": totals, "source": source})
            existing = await session.scalar(select(SleepSession.id).where(SleepSession.user_id == user.id, SleepSession.start_time == start))
            if existing is None:
                session.add(SleepSession(user_id=user.id, origin=SOURCE, local_date=day, start_time=start,
                    end_time=end, total_sleep_s=total or None, deep_s=totals["deep"] or None,
                    light_s=totals["core"] or None, rem_s=totals["rem"] or None, awake_s=totals["awake"] or None))
        bio = await session.scalar(select(DailyBiometric).where(DailyBiometric.user_id == user.id,
            DailyBiometric.date == day).with_for_update().execution_options(populate_existing=True))
        if bio is None:
            if not summaries:
                continue
            bio = DailyBiometric(user_id=user.id, date=day)
            session.add(bio)
        metrics = dict(bio.source_metrics or {})
        apple = dict(metrics.get(SOURCE) or {})
        apple["sleep"] = summaries
        metrics[SOURCE] = apple
        bio.source_metrics = metrics
        ident = f"sleep:{day}"
        measured_summaries = [row for row in summaries if row["total_sleep_s"] is not None]
        if measured_summaries:
            await _evidence(session, user, "sleep_duration", sum(row["total_sleep_s"] for row in measured_summaries) / 3600,
                "h", ident, max(_time(row, "end") for row in measured_summaries),
                {"source_identity": source, "method": "overlap_union_selected_source", "episodes": len(measured_summaries)}, now)
        else:
            await _invalidate(session, user.id, [ident])
    await session.flush()


def _workout_summary(payload):
    summary = payload["metadata"].get("workout_summary", {})
    if not isinstance(summary, dict):
        return {}
    result = {}
    for key, maximum in (("distance_m", 1000000), ("total_energy_kcal", 20000), ("duration_s", 86400)):
        value = summary.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= maximum:
            result[key] = value
    return result


async def _add_workout(session, user, payload):
    ident = payload["uuid"]
    link = await session.scalar(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id,
        ActivitySourceLink.source == SOURCE, ActivitySourceLink.external_id == ident))
    if link:
        return
    start, end = _time(payload, "start_at"), _time(payload, "end_at")
    summary = _workout_summary(payload)
    elapsed = int((end - start).total_seconds())
    active_duration = summary.get("duration_s")
    duration = round(active_duration) if active_duration is not None and 1 <= active_duration <= elapsed else elapsed
    decision = await resolve_activity_winner(session, user, start, duration, SOURCE)
    candidate = await session.get(Activity, decision.winner_activity_id) if decision.winner_activity_id else None
    discipline = await session.scalar(select(Discipline.id).where(Discipline.name == SPORTS.get(payload["workout_activity_type"], "")))
    if candidate is not None and discipline is not None and candidate.discipline_id is not None and candidate.discipline_id != discipline:
        candidate = None
    if candidate is None and discipline is not None:
        from app.connectors.reconciliation import find_reconcilable_activity
        candidate = await find_reconcilable_activity(session, user_id=user.id,
            start_time=start, discipline_id=discipline, source=SOURCE)
    created = candidate is None
    if created:
        tz = ZoneInfo(user.timezone)
        candidate = Activity(user_id=user.id, discipline_id=discipline, start_time=start,
            start_tz_offset_minutes=int(start.astimezone(tz).utcoffset().total_seconds() / 60),
            local_date=start.astimezone(tz).date(), duration_s=duration,
            distance_m=summary.get("distance_m"), calories=round(summary["total_energy_kcal"]) if "total_energy_kcal" in summary else None,
            data_completeness="partial")
        session.add(candidate)
        await session.flush()
    # Existing canonical rows remain their provider's projections. Only the
    # source link and provenance are attached; deletion cannot erase them.
    metrics = dict(candidate.source_metrics or {})
    apple = dict(metrics.get(SOURCE) or {})
    if created:
        supplied = {field: float(getattr(candidate, field)) for field in ("distance_m", "calories") if getattr(candidate, field) is not None}
        apple["canonical_supplier_fields"] = supplied
        merged = dict(metrics.get("_merged_fields") or {})
        merged.update({field: SOURCE for field in supplied})
        if merged:
            metrics["_merged_fields"] = merged
    workouts = dict(apple.get("workouts") or {})
    workouts[ident] = {"uuid": ident, "type": WORKOUT_TYPE, "workout_activity_type": payload["workout_activity_type"],
        "source_name": payload["source_name"], "source_bundle": payload["source_bundle"],
        "device": payload["device"], "start_at": payload["start_at"], "end_at": payload["end_at"], "summary": summary}
    apple["workouts"] = workouts
    metrics[SOURCE] = apple
    candidate.source_metrics = metrics
    session.add(ActivitySourceLink(user_id=user.id, activity_id=candidate.id, source=SOURCE, external_id=ident))
    await session.flush()


async def _delete_workout(session, user_id, ident):
    link = await session.scalar(select(ActivitySourceLink).where(ActivitySourceLink.user_id == user_id,
        ActivitySourceLink.source == SOURCE, ActivitySourceLink.external_id == ident))
    if link is None:
        return
    activity = await session.scalar(select(Activity).where(Activity.id == link.activity_id,
        Activity.user_id == user_id).with_for_update().execution_options(populate_existing=True))
    await session.delete(link)
    await session.flush()
    remaining = await session.scalar(select(ActivitySourceLink.id).where(ActivitySourceLink.user_id == user_id,
        ActivitySourceLink.activity_id == activity.id).limit(1))
    metrics = dict(activity.source_metrics or {})
    apple = dict(metrics.get(SOURCE) or {})
    workouts = dict(apple.get("workouts") or {})
    workouts.pop(ident, None)
    if workouts:
        apple["workouts"] = workouts
        metrics[SOURCE] = apple
    else:
        merged = dict(metrics.get("_merged_fields") or {})
        for field, previous_value in (apple.get("canonical_supplier_fields") or {}).items():
            current = getattr(activity, field, None)
            if merged.get(field) == SOURCE and current is not None and float(current) == previous_value:
                setattr(activity, field, None)
                merged.pop(field, None)
        if merged:
            metrics["_merged_fields"] = merged
        else:
            metrics.pop("_merged_fields", None)
        metrics.pop(SOURCE, None)
    activity.source_metrics = metrics
    if remaining is None and not metrics:
        from sqlalchemy import text
        from app.models.activity import ActivityStream, ActivityLap
        from app.models.gear import ActivityGearLink
        await session.execute(delete(ActivityStream).where(ActivityStream.activity_id == activity.id))
        await session.execute(delete(ActivityLap).where(ActivityLap.activity_id == activity.id))
        await session.execute(delete(ActivityGearLink).where(ActivityGearLink.activity_id == activity.id))
        await session.execute(text("DELETE FROM segment_efforts WHERE activity_id = :id"), {"id": activity.id})
        await session.delete(activity)


async def erase_healthkit_source(session: AsyncSession, user):
    """Erase only this account's Apple source and revoke all native access.

    Caller holds changes then apple_health_import through preview and commit.
    Reusing projections preserves other providers and legacy unknown suppliers.
    """
    from sqlalchemy import update
    days = set((await session.scalars(select(DailyBiometric.date).where(
        DailyBiometric.user_id == user.id, DailyBiometric.source_metrics[SOURCE].is_not(None),
    ))).all())
    sleep_days = set((await session.scalars(select(SleepSession.local_date).where(
        SleepSession.user_id == user.id, SleepSession.origin == SOURCE,
    ))).all())
    sleep_days.update(days)
    workouts = (await session.scalars(select(ActivitySourceLink.external_id).where(
        ActivitySourceLink.user_id == user.id, ActivitySourceLink.source == SOURCE,
    ).order_by(ActivitySourceLink.id))).all()
    for ident in workouts:
        await _delete_workout(session, user.id, ident)
    now = datetime.now(UTC)
    await session.execute(update(DeviceToken).where(DeviceToken.user_id == user.id,
        DeviceToken.scope == "healthkit_sync", DeviceToken.revoked_at.is_(None)).values(revoked_at=now))
    await session.execute(delete(HealthKitPairing).where(HealthKitPairing.user_id == user.id))
    await session.execute(delete(HealthKitBatch).where(HealthKitBatch.device_id.in_(
        select(DeviceToken.id).where(DeviceToken.user_id == user.id))))
    await session.execute(delete(HealthKitSample).where(HealthKitSample.user_id == user.id))
    await session.flush()
    await _daily_projections(session, user, days, now)
    await _sleep_projections(session, user, sleep_days, now)
    # Remove Apple namespaces after the source-owned setters cleared fields.
    for row in (await session.scalars(select(DailyBiometric).where(
        DailyBiometric.user_id == user.id, DailyBiometric.date.in_(days | sleep_days),
    ))).all():
        metrics = dict(row.source_metrics or {})
        metrics.pop(SOURCE, None)
        row.source_metrics = metrics or None
    await session.execute(delete(Observation).where(Observation.user_id == user.id, Observation.origin == SOURCE))
    await session.execute(delete(FeedState).where(FeedState.user_id == user.id, FeedState.provider == SOURCE))
    await session.flush()


async def ingest_healthkit(session: AsyncSession, user, token: DeviceToken, batch: HealthKitDelta):
    """Caller holds scoped auth locks; receipt and all side effects commit once."""
    await scope_lock(session, user.id, "changes")
    await scope_lock(session, user.id, "apple_health_import")
    content_hash = digest(batch.model_dump(mode="json"))
    existing = await session.scalar(select(HealthKitBatch).where(HealthKitBatch.device_id == token.id,
        HealthKitBatch.batch_id == batch.batch_id))
    if existing:
        if existing.content_hash != content_hash:
            raise HTTPException(409, "Batch ID already used with different content")
        return existing.receipt
    if token.sync_checkpoint != batch.expected_checkpoint:
        raise HTTPException(409, "Checkpoint mismatch; retry the pending batch or read status")
    now, tz = datetime.now(UTC), ZoneInfo(user.timezone)
    ids = [sample.uuid for sample in batch.additions] + batch.deletions
    known = {row.uuid: row for row in (await session.scalars(select(HealthKitSample).where(
        HealthKitSample.user_id == user.id, HealthKitSample.uuid.in_(ids)).with_for_update())).all()} if ids else {}
    daily_days, sleep_days = set(), set()
    latest_new_measurement = None

    def affected(p):
        if p["type"] == SLEEP_TYPE:
            end_day = date.fromisoformat(p["end_local_date"])
            sleep_days.update(end_day + timedelta(days=n) for n in range(-2, 3))
        elif p["type"] in DAILY:
            daily_days.add(date.fromisoformat(p["local_date"]))

    for sample in batch.additions:
        payload = _ledger_payload(sample, tz)
        previous = known.get(sample.uuid)
        if previous is not None:
            if previous.deleted:
                continue  # Tombstones defeat reordered backfill/resurrection.
            previous_wire = {key: value for key, value in previous.payload.items() if key not in {"local_date", "end_local_date"}}
            incoming_wire = {key: value for key, value in payload.items() if key not in {"local_date", "end_local_date"}}
            if digest(previous_wire) != digest(incoming_wire):
                raise HTTPException(409, "HealthKit UUID already exists with different content")
            continue
        row = HealthKitSample(user_id=user.id, uuid=sample.uuid, payload=payload, deleted=False, received_at=now)
        session.add(row)
        latest_new_measurement = max(latest_new_measurement, sample.end_at) if latest_new_measurement else sample.end_at
        affected(payload)
        if sample.type == WORKOUT_TYPE:
            await _add_workout(session, user, payload)
    for ident in batch.deletions:
        previous = known.get(ident)
        if previous is None:
            session.add(HealthKitSample(user_id=user.id, uuid=ident, payload=None, deleted=True, received_at=now))
        elif not previous.deleted:
            affected(previous.payload)
            if previous.payload["type"] == WORKOUT_TYPE:
                await _delete_workout(session, user.id, str(ident))
            previous.deleted = True
            previous.payload = None  # Erase deleted sensitive provenance.
        await _invalidate(session, user.id, [str(ident)])
    await session.flush()
    await _daily_projections(session, user, daily_days, now)
    await _sleep_projections(session, user, sleep_days, now)
    token.sync_checkpoint += 1
    token.last_used_at = now
    receipt = {"checkpoint": token.sync_checkpoint, "accepted": len(batch.additions), "deleted": len(batch.deletions)}
    session.add(HealthKitBatch(device_id=token.id, batch_id=batch.batch_id, content_hash=content_hash,
        checkpoint=token.sync_checkpoint, receipt=receipt, created_at=now))
    state = await session.scalar(select(FeedState).where(FeedState.user_id == user.id,
        FeedState.provider == SOURCE, FeedState.feed == "healthkit"))
    if state is None:
        state = FeedState(user_id=user.id, provider=SOURCE, feed="healthkit")
        session.add(state)
    state.availability = "available"
    state.last_attempt_at = state.last_success_at = now
    state.cursor = {"device_id": token.id, "checkpoint": token.sync_checkpoint}
    state.details = {"accepted": receipt["accepted"], "deleted": receipt["deleted"], "background_delivery": "best_effort"}
    latest = latest_new_measurement
    if batch.deletions:
        state.latest_measurement_at = await session.scalar(select(func.max(cast(HealthKitSample.payload["end_at"].astext, DateTime(timezone=True)))).where(
            HealthKitSample.user_id == user.id, HealthKitSample.deleted.is_(False)))
    elif latest and (state.latest_measurement_at is None or latest > state.latest_measurement_at):
        state.latest_measurement_at = latest
    await session.flush()
    return receipt
