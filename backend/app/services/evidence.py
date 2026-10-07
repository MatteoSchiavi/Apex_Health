"""Canonical, source-aware evidence. No model can select eligibility or identity."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink
from app.models.coach import UserContextDoc, UserEvent
from app.models.integration import Integration, RawIngest
from app.models.lab import AthleteEntry, Observation, FeedState
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import User

VERSION = "apex-evidence-v1"
AVAILABILITY = {
    "available",
    "not_measured",
    "not_supported",
    "not_exposed",
    "pending_sync",
    "permission_denied",
    "fetch_failed",
    "stale",
}
AI_ORIGINS = {"garmin", "fit", "manual", "web", "whoop", "oura", "coros", "technogym"}
METRICS = {
    "hrv_overnight_rmssd": "ms",
    "resting_hr": "bpm",
    "sleep_duration": "h",
    "sleep_score": "/100",
    "respiration": "br/min",
    "spo2": "%",
    "stress": "/100",
    "body_battery": "/100",
    "training_readiness": "/100",
    "training_status": None,
    "recovery_time": "min",
    "provider_load": "Garmin load",
    "steps": "steps",
    "weight": "kg",
    "body_fat": "%",
    "vo2max": "ml/kg/min",
    "hydration": "ml",
    "temperature": "°C",
}


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
        allow_nan=False,
    )


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def eligible(origin: str, metadata: dict | None = None) -> bool:
    # A source label on a derivative cannot erase restricted inputs.
    sources = set((metadata or {}).get("input_origins", [])) | {origin}
    return bool(sources) and sources <= AI_ORIGINS


async def scope_lock(session: AsyncSession, user_id: int, resource: str):
    # Transaction-scoped lock also covers absent rows (creation races).
    key = int.from_bytes(
        hashlib.sha256(f"{user_id}:{resource}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def record_observation(
    session,
    *,
    user_id,
    metric,
    value,
    unit,
    origin,
    source_record_id,
    measured_at,
    timezone,
    fetched_at,
    acquisition="verified_import",
    raw_ingest_id=None,
    metadata=None,
    quality_flags=None,
):
    if metric not in METRICS:
        raise EvidenceError("UNSUPPORTED_METRIC", "Unsupported observation metric")
    if isinstance(value, (int, float)) and not math.isfinite(value):
        raise EvidenceError("INVALID_ARGUMENTS", "Observation value must be finite")
    if measured_at.tzinfo is None or fetched_at.tzinfo is None:
        raise EvidenceError(
            "INVALID_ARGUMENTS", "Observation timestamps require a timezone"
        )
    content = {
        "value": value,
        "unit": unit,
        "measured_at": measured_at.isoformat(),
        "metadata": metadata or {},
        "flags": quality_flags or [],
    }
    content_hash = digest(content)
    await scope_lock(session, user_id, "changes")
    await scope_lock(
        session, user_id, f"observation:{origin}:{metric}:{source_record_id}"
    )
    previous = await session.scalar(
        select(Observation)
        .where(
            Observation.user_id == user_id,
            Observation.origin == origin,
            Observation.metric == metric,
            Observation.source_record_id == source_record_id,
            Observation.current.is_(True),
        )
        .with_for_update()
    )
    if previous and previous.content_hash == content_hash:
        previous.fetched_at = max(previous.fetched_at, fetched_at)
        return previous
    revision = previous.revision + 1 if previous else 1
    if previous:
        previous.current = False
    row = Observation(
        user_id=user_id,
        metric=metric,
        value={"value": value},
        unit=unit,
        origin=origin,
        source_record_id=source_record_id,
        measured_at=measured_at,
        local_date=measured_at.astimezone(ZoneInfo(timezone)).date(),
        timezone=timezone,
        fetched_at=fetched_at,
        acquisition=acquisition,
        raw_ingest_id=raw_ingest_id,
        revision=revision,
        availability="available" if value is not None else "not_measured",
        quality_flags=quality_flags or [],
        metadata_json=metadata or {},
        content_hash=content_hash,
    )
    session.add(row)
    await session.flush()
    return row


def observation_dict(row: Observation, now: datetime) -> dict:
    stale = row.measured_at < now - timedelta(hours=48)
    return {
        "id": f"observation:{row.id}:{row.revision}",
        "metric": row.metric,
        "value": row.value.get("value"),
        "unit": row.unit,
        "origin": row.origin,
        "acquisition": row.acquisition,
        "source_record_id": row.source_record_id,
        "measured_at": row.measured_at.isoformat(),
        "local_date": row.local_date.isoformat(),
        "timezone": row.timezone,
        "fetched_at": row.fetched_at.isoformat(),
        "revision": row.revision,
        "availability": "stale"
        if stale and row.availability == "available"
        else row.availability,
        "quality_flags": row.quality_flags,
        "metadata": row.metadata_json,
        "usage_policy": "ai_eligible_v1"
        if eligible(row.origin, row.metadata_json)
        else "ai_denied_v1",
    }


async def query_observations(
    session, user_id, metric, start, end, *, for_ai=False, origin=None, limit=366
):
    if metric not in METRICS:
        raise EvidenceError("UNSUPPORTED_METRIC", "Unsupported metric")
    if start > end or (end - start).days > 365:
        raise EvidenceError(
            "INVALID_ARGUMENTS", "Choose a closed range of at most 366 days"
        )
    conditions = [
        Observation.user_id == user_id,
        Observation.current.is_(True),
        Observation.metric == metric,
        Observation.local_date.between(start, end),
    ]
    if origin:
        conditions.append(Observation.origin == origin)
    if for_ai:
        conditions.append(Observation.origin.in_(AI_ORIGINS))
    rows = (
        await session.scalars(
            select(Observation)
            .where(*conditions)
            .order_by(Observation.measured_at.desc(), Observation.id.desc())
            .limit(min(limit, 1000))
        )
    ).all()
    excluded = await excluded_observations(session, user_id) if for_ai else set()
    return [
        r
        for r in reversed(rows)
        if not for_ai
        or (
            eligible(r.origin, r.metadata_json)
            and r.id not in excluded
            and r.measured_at <= datetime.now(UTC) + timedelta(minutes=5)
        )
    ]


async def excluded_observations(session, user_id):
    rows = (
        await session.scalars(
            select(AthleteEntry)
            .where(
                AthleteEntry.user_id == user_id,
                AthleteEntry.kind == "observation_annotation",
            )
            .order_by(AthleteEntry.id)
        )
    ).all()
    latest = {r.payload["observation_id"]: r.payload for r in rows}
    return {ident for ident, p in latest.items() if p["exclude_from_analysis"]}


async def coverage(session, user: User, *, now=None, for_ai=False):
    now = now or datetime.now(UTC)
    day = now.astimezone(ZoneInfo(user.timezone)).date()
    conditions = [
        Observation.user_id == user.id,
        Observation.current.is_(True),
        Observation.local_date >= day - timedelta(days=27),
        Observation.local_date <= day,
    ]
    if for_ai:
        conditions.append(Observation.origin.in_(AI_ORIGINS))
    rows = (
        await session.scalars(
            select(Observation).where(*conditions).order_by(Observation.measured_at)
        )
    ).all()
    if for_ai:
        excluded = await excluded_observations(session, user.id)
        rows = [
            r
            for r in rows
            if eligible(r.origin, r.metadata_json)
            and r.id not in excluded
            and r.measured_at <= now + timedelta(minutes=5)
        ]
    integrations = (
        await session.scalars(select(Integration).where(Integration.user_id == user.id))
    ).all()
    from app.models.lab import FeedState

    feeds = (
        await session.scalars(select(FeedState).where(FeedState.user_id == user.id))
    ).all()
    if for_ai:
        feeds = [f for f in feeds if f.provider in AI_ORIGINS]
    result = []
    for metric, unit in METRICS.items():
        samples = [
            r for r in rows if r.metric == metric and r.value.get("value") is not None
        ]
        latest = samples[-1] if samples else None
        nights = {
            r.local_date for r in samples if r.local_date >= day - timedelta(days=6)
        }
        feed = next((f for f in feeds if f.feed == metric), None)
        state = (
            observation_dict(latest, now)["availability"]
            if latest
            else (
                feed.availability
                if feed
                else "not_exposed"
                if metric
                in (
                    "training_readiness",
                    "training_status",
                    "recovery_time",
                    "provider_load",
                )
                and any(i.provider == "garmin" for i in integrations)
                else "not_measured"
            )
        )
        if latest is None and state == "available":
            state = (
                "stale"
                if feed
                and feed.latest_measurement_at
                and feed.latest_measurement_at < now - timedelta(hours=48)
                else "not_measured"
            )
        result.append(
            {
                "metric": metric,
                "unit": unit,
                "availability": state,
                "sample_days_7d": len(nights),
                "expected_days": 7,
                "coverage_pct": round(len(nights) / 7 * 100),
                "latest": observation_dict(latest, now) if latest else None,
                "next_action": "sync_or_import"
                if state in ("not_measured", "stale", "fetch_failed")
                else None,
            }
        )
    return {
        "timezone": user.timezone,
        "local_date": str(day),
        "computed_at": now.isoformat(),
        "formula_version": VERSION,
        "metrics": result,
        "integrations": [
            {
                "provider": i.provider,
                "status": i.status,
                "normalization": next((
                    {"state": f.availability, **f.details}
                    for f in feeds if f.provider == i.provider and f.feed == "normalization"
                ), None),
                "last_successful_fetch": i.last_synced_at.isoformat()
                if i.last_synced_at
                else None,
                "consecutive_failures": i.consecutive_failures,
            }
            for i in integrations
        ],
        "source_policy": "Restricted origins and their derivatives are excluded from AI.",
    }


async def snapshot_revision(session, user_id):
    # Changes to data/constraints invalidate approvals and cached evidence.
    observation_root = await session.scalar(
        text(
            "SELECT md5(coalesce(string_agg(id::text || ':' || revision::text || ':' || content_hash, '' ORDER BY id), '')) FROM lab_observations WHERE user_id=:owner AND current"
        ),
        {"owner": user_id},
    )
    docs = (
        await session.execute(
            select(UserContextDoc.doc_kind, UserContextDoc.content)
            .where(UserContextDoc.user_id == user_id)
            .order_by(UserContextDoc.doc_kind)
        )
    ).all()
    events = (
        await session.execute(
            select(
                UserEvent.id,
                UserEvent.starts_at,
                UserEvent.ends_at,
                UserEvent.priority,
                UserEvent.taper_days,
                UserEvent.title,
                UserEvent.kind,
                UserEvent.notes,
            )
            .where(UserEvent.user_id == user_id)
            .order_by(UserEvent.id)
        )
    ).all()
    entries = (
        await session.execute(
            select(AthleteEntry.id, AthleteEntry.revision, AthleteEntry.payload)
            .where(AthleteEntry.user_id == user_id)
            .order_by(AthleteEntry.id)
        )
    ).all()
    plans = (
        await session.execute(
            select(
                PlannedSession.id,
                PlannedSession.date,
                PlannedSession.target_duration_min,
                PlannedSession.description,
                PlannedSession.session_type,
                PlannedSession.target_load,
                TrainingPlan.status,
            )
            .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
            .where(TrainingPlan.user_id == user_id)
            .order_by(PlannedSession.id)
        )
    ).all()
    # Hash mutable activity inputs inside PostgreSQL: bounded transfer, including
    # corrections and deletions (a max(id) or row count alone misses both).
    fingerprints = []
    for table in (
        "activities",
        "activity_source_links",
        "session_feedback",
        "lab_panels",
        "journal_entries",
        "gym_set_logs",
    ):
        fingerprint = await session.scalar(
            text(
                f"SELECT md5(coalesce(string_agg(to_jsonb(t)::text, '' ORDER BY id), '')) "
                f"FROM {table} t WHERE user_id = :owner"
            ),
            {"owner": user_id},
        )
        fingerprints.append(fingerprint)
    fingerprints.append(
        await session.scalar(
            text(
                "SELECT md5(coalesce(string_agg(id::text || content_hash || status || revision::text, '' ORDER BY id), '')) FROM lab_documents WHERE user_id=:owner"
            ),
            {"owner": user_id},
        )
    )
    profile = await session.get(User, user_id)
    profile_revision = (
        [
            profile.timezone,
            profile.main_integration_id,
            str(datetime.now(ZoneInfo(profile.timezone)).date()),
        ]
        if profile
        else None
    )
    return digest(
        [
            VERSION,
            observation_root,
            [list(x) for x in docs],
            [list(x) for x in events],
            [list(x) for x in entries],
            [list(x) for x in plans],
            fingerprints,
            profile_revision,
        ]
    )


async def eligible_activity_conditions(session, user_id):
    # Canonical rows may merge fields from alternate sources. Deny the entire row
    # if any linked origin is restricted until per-field lineage is available.
    denied = select(ActivitySourceLink.activity_id).where(
        ActivitySourceLink.user_id == user_id,
        ~ActivitySourceLink.source.in_(AI_ORIGINS),
    )
    linked = select(ActivitySourceLink.activity_id).where(
        ActivitySourceLink.user_id == user_id, ActivitySourceLink.source.in_(AI_ORIGINS)
    )
    return [
        Activity.user_id == user_id,
        Activity.id.in_(linked),
        ~Activity.id.in_(denied),
    ]


async def index_garmin_payload(
    session, raw: RawIngest, tz: ZoneInfo, *, start=None, end=None
):
    """Verified, explicit mapping only; unknown keys remain in the raw store."""
    if raw.source != "garmin" or not isinstance(raw.raw_json, dict):
        return
    from app.connectors.garmin.normalize import _epoch_ms, _timestamp_flex
    from app.connectors.validation import (
        valid_stress_level,
        valid_body_battery,
        valid_weight_kg,
        valid_body_fat_pct,
        valid_hrv_ms,
        valid_resting_hr_bpm,
        valid_sleep_score,
        valid_spo2_pct,
        valid_respiration_bpm,
    )

    await scope_lock(session, raw.user_id, "changes")
    payload, kind = raw.raw_json, raw.payload_type.split(":")[0]
    records = []
    if kind == "sleep" and isinstance(payload.get("dailySleepDTO"), dict):
        dto = payload["dailySleepDTO"]
        if dto.get("sleepEndTimestampGMT"):
            measured = _epoch_ms(dto["sleepEndTimestampGMT"], "sleep end")
            score = (payload.get("sleepScore") or {}).get("value")
            if score is None:
                score = ((dto.get("sleepScores") or {}).get("overall") or {}).get(
                    "value"
                )
            records = [
                (
                    "sleep_duration",
                    dto.get("sleepTimeSeconds") / 3600
                    if dto.get("sleepTimeSeconds") is not None
                    else None,
                    measured,
                ),
                ("sleep_score", valid_sleep_score(score), measured),
                (
                    "respiration",
                    valid_respiration_bpm(dto.get("avgRespirationValue")),
                    measured,
                ),
                ("spo2", valid_spo2_pct(dto.get("avgSpO2Value")), measured),
            ]
    elif kind == "hrv":
        summary = payload.get("hrvSummary") or {}
        readings = payload.get("hrvReadings") or []
        ts = [
            _timestamp_flex(r.get("timestamp") or r.get("readingTimeGMT"), "hrv")
            for r in readings
            if isinstance(r, dict) and (r.get("timestamp") or r.get("readingTimeGMT"))
        ]
        # Summary-only feed is a valid observation, with its provider calendar day.
        day_label = summary.get("calendarDate") or payload.get("calendarDate") or raw.payload_type.partition(":")[2]
        measured = (
            max(ts)
            if ts
            else (
                datetime.combine(date.fromisoformat(day_label), time.min, tzinfo=tz)
                if day_label
                else None
            )
        )
        if measured:
            records = [
                (
                    "hrv_overnight_rmssd",
                    valid_hrv_ms(summary.get("lastNightAvg")),
                    measured,
                )
            ]
    elif kind == "stats" and ":" in raw.payload_type:
        day = date.fromisoformat(raw.payload_type.split(":", 1)[1])
        measured = datetime.combine(day, time.min, tzinfo=tz)
        records = [
            (
                "resting_hr",
                valid_resting_hr_bpm(payload.get("restingHeartRate")),
                measured,
            ),
            ("steps", payload.get("totalSteps"), measured),
            ("stress", valid_stress_level(payload.get("averageStressLevel")), measured),
            (
                "body_battery",
                valid_body_battery(payload.get("bodyBatteryMostRecentValue")),
                measured,
            ),
            ("spo2", valid_spo2_pct(payload.get("averageSpo2")), measured),
        ]
    elif kind == "body_composition" and ":" in raw.payload_type:
        measured = datetime.combine(
            date.fromisoformat(raw.payload_type.split(":", 1)[1]), time.min, tzinfo=tz
        )
        total = payload.get("totalAverage") or {}
        weight = total.get("weight")
        records = [
            (
                "weight",
                valid_weight_kg(
                    weight / 1000 if isinstance(weight, (int, float)) else None
                ),
                measured,
            ),
            ("body_fat", valid_body_fat_pct(total.get("bodyFat")), measured),
        ]
    elif kind in ("training_readiness", "training_status", "recovery_time"):
        day_label = payload.get("calendarDate")
        if day_label:
            records = [
                (
                    kind,
                    payload.get("score")
                    if kind == "training_readiness"
                    else payload.get("value"),
                    datetime.combine(
                        date.fromisoformat(day_label), time.min, tzinfo=tz
                    ),
                )
            ]
    for metric, value, measured in records:
        if (start and measured.astimezone(tz).date() < start) or (
            end and measured.astimezone(tz).date() > end
        ):
            continue
        await update_feed(
            session,
            raw.user_id,
            "garmin",
            metric,
            "available" if value is not None else "not_measured",
            raw.fetched_at,
            measured,
        )
        provider_day = (
            (payload.get("hrvSummary") or {}).get("calendarDate")
            or payload.get("calendarDate")
            or (raw.payload_type.partition(":")[2] if kind == "hrv" else None)
            or measured.astimezone(tz).date().isoformat()
        )
        source_key = str((payload.get("dailySleepDTO") or {}).get("id") or provider_day)
        await record_observation(
            session,
            user_id=raw.user_id,
            metric=metric,
            value=value,
            unit=METRICS[metric],
            origin="garmin",
            source_record_id=f"{kind}:{source_key}",
            measured_at=measured,
            timezone=tz.key,
            fetched_at=raw.fetched_at,
            acquisition="unofficial_adapter",
            raw_ingest_id=raw.id,
            metadata={
                "feed": kind,
                "aggregation_window": "provider-defined",
                "reading_context": "overnight" if kind in ("sleep", "hrv") else "daily",
                "device_id": payload.get("deviceId")
                or (payload.get("dailySleepDTO") or {}).get("deviceId"),
                **(
                    {
                        "sleep_start": _epoch_ms(
                            dto["sleepStartTimestampGMT"], "sleep start"
                        ).isoformat(),
                        "sleep_end": measured.isoformat(),
                    }
                    if kind == "sleep" and dto.get("sleepStartTimestampGMT")
                    else {}
                ),
            },
        )


async def update_feed(session, user_id, provider, metric, state, now, measurement=None):
    await scope_lock(session, user_id, "feed:" + provider + ":" + metric)
    row = await session.scalar(
        select(FeedState).where(
            FeedState.user_id == user_id,
            FeedState.provider == provider,
            FeedState.feed == metric,
        )
    )
    if row is None:
        row = FeedState(
            user_id=user_id, provider=provider, feed=metric, availability=state
        )
        session.add(row)
    row.last_attempt_at = now
    row.availability = state
    if state in ("available", "not_measured"):
        row.last_success_at = now
        if measurement:
            row.latest_measurement_at = (
                max(row.latest_measurement_at, measurement)
                if row.latest_measurement_at
                else measurement
            )
