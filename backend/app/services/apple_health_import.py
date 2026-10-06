"""Import an Apple Health export.zip without extracting untrusted paths.

HealthKit has no server-side OAuth/API. This module handles the user's manual
Health app export, with bounded ZIP/XML parsing and account-scoped writes.
"""
from __future__ import annotations

import hashlib
import io
import math
import zipfile
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import BinaryIO, Iterator
from xml.etree.ElementTree import iterparse
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_bytes
from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.integration import RawIngest
from app.models.lab import LabDocument
from app.models.wellness import DailyBiometric, SleepSession
from app.connectors.validation import (
    valid_resting_hr_bpm, valid_spo2_pct, valid_weight_kg,
)

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 500 * 1024 * 1024
MAX_XML_RECORDS = 1_000_000
MAX_ZIP_MEMBERS = 10_000
MAX_COMPRESSION_RATIO = 200
MAX_XML_DEPTH = 64
SOURCE = "apple_health"
IMPORT_SOURCE = "apple_health_import"


class AppleHealthImportError(ValueError):
    pass


def _xml_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        raise AppleHealthImportError("Export has too many ZIP entries")
    candidates = [i for i in infos if PurePosixPath(i.filename).name.lower() == "export.xml"]
    if len(candidates) != 1:
        raise AppleHealthImportError("ZIP must contain exactly one export.xml")
    info = candidates[0]
    if info.file_size > MAX_XML_BYTES:
        raise AppleHealthImportError("export.xml exceeds the 500 MB limit")
    if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
        raise AppleHealthImportError("export.xml compression ratio is too high")
    return info


def _number(value: str | None) -> float | None:
    try:
        n = float(value) if value else None
        return n if n is not None and math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def _kg(value: float, unit: str) -> float | None:
    u = unit.lower()
    if u == "kg":
        return value
    if u in {"lb", "lbs"}:
        return value * 0.45359237
    if u == "g":
        return value / 1000
    return None


def _distance_m(value: float, unit: str) -> float | None:
    return value * 1000 if unit.lower() == "km" else value if unit.lower() == "m" else None


def iter_health_records(stream: BinaryIO) -> Iterator[dict]:
    """Yield supported export records with bounded parser state."""
    count = 0
    try:
        root = None
        depth = 0
        for event, el in iterparse(stream, events=("start", "end")):
            if event == "start":
                depth += 1
                if depth > MAX_XML_DEPTH:
                    raise AppleHealthImportError("export.xml nesting is too deep")
                if root is None: root = el
                continue
            if el.tag in {"Record", "Workout"}:
                count += 1
                if count > MAX_XML_RECORDS:
                    raise AppleHealthImportError("Export exceeds the one million record limit")
                entry = {"kind": el.tag, **el.attrib}
                if el.tag == "Workout":
                    entry["statistics"] = [dict(child.attrib) for child in el if child.tag == "WorkoutStatistics"]
                yield entry
            # Clear every completed top-level subtree, including unknown Apple
            # elements, so large exports have bounded XML parser memory.
            if depth == 2:
                el.clear()
                if root is not None: root.clear()
            depth -= 1
    except AppleHealthImportError:
        raise
    except Exception as exc:
        raise AppleHealthImportError("export.xml is invalid or incomplete") from exc


def parse_export(content: bytes) -> list[dict]:
    """Parse a supported export into normalized entries (test/helper API)."""
    if len(content) > MAX_ARCHIVE_BYTES:
        raise AppleHealthImportError("Archive exceeds the 100 MB limit")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            info = _xml_member(zf)
            with zf.open(info) as xml:
                return list(iter_health_records(xml))
    except AppleHealthImportError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise AppleHealthImportError("Invalid or unreadable Apple Health ZIP") from exc


def _sport_name(raw: str) -> str | None:
    key = raw.rsplit(".", 1)[-1].lower()
    prefix = "hkworkoutactivitytype"
    if key.startswith(prefix):
        key = key[len(prefix):]
    return {
        "running": "running", "walking": "walking", "hiking": "hiking",
        "cycling": "road_cycling", "swimming": "swimming", "rowing": "rowing",
        "yoga": "yoga", "traditionalstrengthtraining": "strength",
        "functionalstrengthtraining": "strength", "elliptical": "gym_general",
        "highintensityintervaltraining": "gym_general", "dance": "gym_general",
        "downhillSkiing".lower(): "skiing", "snowboarding": "snowboard",
    }.get(key)


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def _step_source_priority(source: str) -> tuple[int, str]:
    label = source.lower()
    if "watch" in label: return (0, label)
    if "iphone" in label: return (1, label)
    return (2, label)


def _step_total(samples: list[tuple[datetime, datetime, float, str]]) -> tuple[float, str | None]:
    if not samples: return 0, None
    sources = sorted({sample[3] for sample in samples}, key=_step_source_priority)
    selected = sources[0]
    intervals = sorted((a, b, value) for a, b, value, source in samples if source == selected)
    total = 0.0
    block_end = None
    block_count = 0.0
    for start, end, value in intervals:
        if block_end is None or start >= block_end:
            total += block_count
            block_count, block_end = value, end
        else:
            block_count = max(block_count, value)
            block_end = max(block_end, end)
    return total + block_count, selected


def _priority_samples(samples: list[tuple], source_index: int = 3) -> tuple[list[tuple], str | None]:
    if not samples: return [], None
    sources = sorted({sample[source_index] for sample in samples}, key=_step_source_priority)
    source = sources[0]
    return [sample for sample in samples if sample[source_index] == source], source


def _sleep_priority(kind: str) -> tuple[int, str | None]:
    value = kind.rsplit(".", 1)[-1].lower()
    if "deep" in value: return 5, "deep"
    if "rem" in value: return 5, "rem"
    if "core" in value: return 5, "core"
    if "awake" in value: return 4, "awake"
    if "asleep" in value: return 3, "asleep"
    if "inbed" in value: return 1, "inbed"
    return 0, None


def _sleep_totals(entries: list[tuple[datetime, datetime, str]]) -> dict[str, int]:
    boundaries = sorted({point for start, end, _ in entries for point in (start, end)})
    totals = {"deep": 0, "core": 0, "rem": 0, "awake": 0, "asleep": 0}
    for start, end in zip(boundaries, boundaries[1:]):
        active = [kind for a, b, kind in entries if a < end and b > start]
        if not active: continue
        _, selected = max((_sleep_priority(kind) for kind in active), key=lambda pair: pair[0])
        if selected in totals:
            totals[selected] += int((end - start).total_seconds())
    return totals


async def import_apple_health(session: AsyncSession, user, filename: str, content: bytes) -> dict:
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        raise AppleHealthImportError("Archive must be between 1 byte and 100 MB")
    sha = hashlib.sha256(content).hexdigest()
    from app.services.evidence import scope_lock
    await scope_lock(session, user.id, "apple_health_import")
    prior = await session.scalar(select(LabDocument.id).where(
        LabDocument.user_id == user.id, LabDocument.content_hash == sha,
        LabDocument.media_type == "application/zip",
    ))
    if prior:
        return {"file_hash": sha, "already_imported": True, "records_seen": 0,
                "activities_imported": 0, "days_updated": 0, "sleep_sessions_imported": 0}

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
        info = _xml_member(zf)
        xml = zf.open(info)
    except AppleHealthImportError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise AppleHealthImportError("Invalid or unreadable Apple Health ZIP") from exc

    # Keep an encrypted source copy, as with original FIT uploads.
    session.add(LabDocument(user_id=user.id, filename=filename[:200],
                            media_type="application/zip", content_hash=sha,
                            ciphertext=encrypt_bytes(content), status="source_file"))
    await session.flush()
    source_document = await session.scalar(select(LabDocument).where(
        LabDocument.user_id == user.id, LabDocument.content_hash == sha,
        LabDocument.media_type == "application/zip",
    ))
    raw_reference = RawIngest(
        user_id=user.id,
        source=IMPORT_SOURCE,
        payload_type="apple_health_export",
        raw_json={"lab_document_id": source_document.id, "file_hash": sha},
        processed=True,
    )
    session.add(raw_reference)
    await session.flush()
    tz = ZoneInfo(user.timezone)
    days: dict[date, dict] = defaultdict(lambda: {"steps": [], "sdnn": [], "rhr": [], "spo2": [], "weight": [], "heart_rate": []})
    workouts, sleeps = [], []
    seen = 0
    try:
        for entry in iter_health_records(xml):
            seen += 1
            if entry["kind"] == "Workout":
                workouts.append(entry)
                continue
            typ = entry.get("type", "")
            start = _timestamp(entry.get("startDate"))
            end = _timestamp(entry.get("endDate"))
            value = _number(entry.get("value"))
            if typ == "HKCategoryTypeIdentifierSleepAnalysis" and start and end and end > start:
                sleeps.append((start, end, entry.get("value", "")))
            if not start or value is None:
                continue
            unit = entry.get("unit", "")
            source_name = entry.get("sourceName", "unknown")
            if typ == "HKQuantityTypeIdentifierStepCount" and value >= 0 and end and end > start and unit == "count":
                # Select one device per day (Watch, then iPhone, then stable
                # lexical source order) and merge overlapping intervals within it.
                days[_local_date(start, tz)]["steps"].append((start, end, value, source_name))
            elif typ == "HKQuantityTypeIdentifierBodyMass":
                kg = _kg(value, unit)
                if kg is not None and valid_weight_kg(kg) is not None: days[_local_date(start, tz)]["weight"].append((start, kg, unit, source_name))
            elif typ == "HKQuantityTypeIdentifierRestingHeartRate":
                hr = valid_resting_hr_bpm(value)
                if hr is not None and unit in {"count/min", "bpm"}: days[_local_date(start, tz)]["rhr"].append((start, hr, unit, source_name))
            elif typ == "HKQuantityTypeIdentifierHeartRate" and unit in {"count/min", "bpm"} and 25 <= value <= 240:
                days[_local_date(start, tz)]["heart_rate"].append((start, value, unit, source_name))
            elif typ == "HKQuantityTypeIdentifierOxygenSaturation":
                if unit == "%": pct = valid_spo2_pct(value)
                elif unit == "1": pct = valid_spo2_pct(value * 100)
                else: pct = None
                if pct is not None: days[_local_date(start, tz)]["spo2"].append((start, pct, "%", source_name))
            elif typ == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN" and unit in {"ms", "s"}:
                # Keep SDNN provenance and unit; do not merge into generic HRV readings.
                sdnn_ms = value * 1000 if unit == "s" else value
                if 0 < sdnn_ms <= 1000: days[_local_date(start, tz)]["sdnn"].append((start, sdnn_ms, "ms", source_name))
    finally:
        xml.close()
        zf.close()

    discipline_ids = dict((await session.execute(select(Discipline.name, Discipline.id))).all())
    imported_activities = 0
    for w in workouts:
        start, end = _timestamp(w.get("startDate")), _timestamp(w.get("endDate"))
        if not start or not end or end <= start or (end - start).total_seconds() > 86400:
            continue
        raw_sport = w.get("workoutActivityType", "unknown")
        sport = _sport_name(raw_sport)
        provider_id = w.get("id") or w.get("workoutUUID") or w.get("uuid")
        identity = "|".join((w.get("sourceName", ""), str(provider_id))) if provider_id else "|".join((
            w.get("sourceName", ""), w.get("sourceVersion", ""), start.isoformat(), end.isoformat(), raw_sport
        ))
        digest = hashlib.sha256(identity.encode()).hexdigest()
        link = await session.scalar(select(ActivitySourceLink).where(
            ActivitySourceLink.user_id == user.id, ActivitySourceLink.source == IMPORT_SOURCE,
            ActivitySourceLink.external_id == digest))
        distance = calories = avg_hr = max_hr = None
        for stat in w.get("statistics", []):
            typ = stat.get("type", "").rsplit(".", 1)[-1]
            prefix = "hkquantitytypeidentifier"
            if typ.lower().startswith(prefix): typ = typ[len(prefix):]
            amount, unit = _number(stat.get("sum")), stat.get("unit", "")
            if typ == "HeartRate":
                average, maximum = _number(stat.get("average")), _number(stat.get("maximum"))
                if average is not None and 25 <= average <= 240: avg_hr = round(average)
                if maximum is not None and 25 <= maximum <= 240: max_hr = round(maximum)
            elif amount is not None and typ in {"DistanceWalkingRunning", "DistanceCycling", "DistanceSwimming"}:
                distance = _distance_m(amount, unit)
            elif amount is not None and typ == "ActiveEnergyBurned" and unit.lower() == "kcal": calories = amount
        workout_values = {
            "discipline_id": discipline_ids.get(sport),
            "start_time": start,
            "start_tz_offset_minutes": int((start.utcoffset().total_seconds() if start.utcoffset() else 0) // 60),
            "local_date": _local_date(start, tz),
            "duration_s": int((end - start).total_seconds()),
            "distance_m": Decimal(str(distance)) if distance is not None else None,
            "elevation_gain_m": None,
            "calories": round(calories) if calories is not None else None,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "avg_power": None,
            "np_power": None,
            "training_load": None,
            "data_completeness": "manual",
        }
        apple_workout_metrics = {
            "workout_type": raw_sport,
            "device": w.get("sourceName"),
            "device_version": w.get("sourceVersion"),
        }
        if link is not None:
            activity = await session.get(Activity, link.activity_id)
            if activity is None:
                raise AppleHealthImportError("Apple workout source link points to a missing activity")
            from app.connectors.reconciliation import activity_has_other_selected_main
            preserve_main = await activity_has_other_selected_main(session, activity, IMPORT_SOURCE)
            other_sources = await session.scalar(select(ActivitySourceLink.id).where(
                ActivitySourceLink.activity_id == activity.id,
                ActivitySourceLink.source != IMPORT_SOURCE,
            ).limit(1))
            preserve_populated = preserve_main or other_sources is not None
            for field, value in workout_values.items():
                if field in {"discipline_id", "start_time", "start_tz_offset_minutes", "local_date", "data_completeness"}:
                    continue
                if value is not None and (not preserve_populated or getattr(activity, field) is None):
                    setattr(activity, field, value)
            link.raw_ingest_id = raw_reference.id
        else:
            candidate = None
            discipline_id = workout_values["discipline_id"]
            if discipline_id is not None:
                from app.connectors.reconciliation import find_reconcilable_activity, reconcile_activity
                candidate = await find_reconcilable_activity(
                    session,
                    user_id=user.id,
                    start_time=start,
                    discipline_id=discipline_id,
                    source=IMPORT_SOURCE,
                )
            if candidate is not None:
                metadata = dict(candidate.source_metrics or {})
                metadata[SOURCE] = {**dict(metadata.get(SOURCE) or {}), **apple_workout_metrics}
                candidate.source_metrics = metadata
                from app.connectors.reconciliation import reconcile_activity
                await reconcile_activity(
                    session,
                    existing=candidate,
                    incoming_values=workout_values,
                    source=IMPORT_SOURCE,
                    external_id=digest,
                    raw_ingest_id=raw_reference.id,
                )
                activity = candidate
            else:
                activity = Activity(user_id=user.id, **workout_values)
                session.add(activity)
                await session.flush()
                session.add(ActivitySourceLink(
                    user_id=user.id,
                    activity_id=activity.id,
                    source=IMPORT_SOURCE,
                    external_id=digest,
                    raw_ingest_id=raw_reference.id,
                ))
        # Merge only Apple-owned metadata; keep metadata from every other source.
        metrics = dict(activity.source_metrics or {})
        metrics[SOURCE] = {**dict(metrics.get(SOURCE) or {}), **apple_workout_metrics}
        activity.source_metrics = metrics
        imported_activities += 1

    days_updated = 0
    for day_date, vals in days.items():
        bio = await session.scalar(select(DailyBiometric).where(DailyBiometric.user_id == user.id, DailyBiometric.date == day_date))
        if bio is None:
            bio = DailyBiometric(user_id=user.id, date=day_date); session.add(bio)
        metrics = dict(bio.source_metrics or {})
        apple = dict(metrics.get(SOURCE) or {})
        steps, step_source = _step_total(vals["steps"])
        if steps:
            if bio.steps is None: bio.steps = round(steps)
            apple["steps"] = {"value": round(steps), "unit": "count", "method": "sum_nonoverlapping_intervals_selected_source", "source": step_source, "samples": len(vals["steps"])}
        weight, weight_source = _priority_samples(vals["weight"])
        if weight:
            sample = max(weight, key=lambda row: row[0])
            if bio.weight_kg is None: bio.weight_kg = Decimal(str(sample[1]))
            apple["weight_kg"] = {"value": sample[1], "unit": "kg", "method": "latest_sample_unit_converted", "source": weight_source, "original_unit": sample[2], "measured_at": sample[0].isoformat()}
        rhr, rhr_source = _priority_samples(vals["rhr"])
        if rhr:
            sample = max(rhr, key=lambda row: row[0])
            if bio.resting_hr is None: bio.resting_hr = int(sample[1])
            apple["resting_hr_bpm"] = {"value": sample[1], "unit": "bpm", "method": "latest_sample", "source": rhr_source, "measured_at": sample[0].isoformat()}
        spo2, spo2_source = _priority_samples(vals["spo2"])
        if spo2:
            mean = sum(row[1] for row in spo2) / len(spo2)
            if bio.spo2_avg is None: bio.spo2_avg = Decimal(str(mean))
            apple["spo2_pct"] = {"value": round(mean, 2), "unit": "%", "method": "mean_samples_selected_source", "source": spo2_source, "samples": len(spo2), "start": min(row[0] for row in spo2).isoformat(), "end": max(row[0] for row in spo2).isoformat()}
        sdnn, sdnn_source = _priority_samples(vals["sdnn"])
        if sdnn:
            apple["hrv_sdnn_ms"] = {"samples": len(sdnn), "mean": round(sum(row[1] for row in sdnn)/len(sdnn), 2), "unit": "ms", "method": "mean_sdnn_samples", "source": sdnn_source, "start": min(row[0] for row in sdnn).isoformat(), "end": max(row[0] for row in sdnn).isoformat()}
        heart, heart_source = _priority_samples(vals["heart_rate"])
        if heart:
            apple["heart_rate_samples_bpm"] = {"samples": len(heart), "mean": round(sum(row[1] for row in heart)/len(heart), 1), "unit": "bpm", "method": "mean_samples", "source": heart_source, "start": min(row[0] for row in heart).isoformat(), "end": max(row[0] for row in heart).isoformat()}
        if apple:
            metrics[SOURCE] = apple
            bio.source_metrics = metrics
        days_updated += 1

    sleep_count = 0
    episodes: list[list[tuple[datetime, datetime, str]]] = []
    for entry in sorted(sleeps, key=lambda row: row[0]):
        if not episodes or (entry[0] - max(row[1] for row in episodes[-1])).total_seconds() >= 2 * 60 * 60:
            episodes.append([entry])
        else:
            episodes[-1].append(entry)
    for entries in episodes:
        # Exclude in-bed-only spans when choosing the activity window.
        sleep_entries = [row for row in entries if _sleep_priority(row[2])[0] > 1]
        if not sleep_entries: continue
        start = min(x[0] for x in sleep_entries); end = max(x[1] for x in sleep_entries)
        local_day = _local_date(end, tz)
        existing = await session.scalar(select(SleepSession.id).where(SleepSession.user_id == user.id, SleepSession.start_time == start))
        if existing: continue
        secs = _sleep_totals(entries)
        total = secs["deep"] + secs["core"] + secs["rem"] + secs["asleep"]
        session.add(SleepSession(user_id=user.id, local_date=local_day, start_time=start, end_time=end,
                                 total_sleep_s=total or None, deep_s=secs["deep"] or None,
                                 light_s=secs["core"] or None, rem_s=secs["rem"] or None,
                                 awake_s=secs["awake"] or None))
        sleep_count += 1
    return {"file_hash": sha, "already_imported": False, "records_seen": seen,
            "activities_imported": imported_activities, "days_updated": days_updated,
            "sleep_sessions_imported": sleep_count}
