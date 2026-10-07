"""CSV import — Apple Health / Google Fit Takeout / generic CSV (§3 ingest).

Owner feature (from the connector inventory: Apple Health / Google Fit CSV
import). No OAuth, no developer portal: a user exports their history from
another service and imports it here.

Two shapes are recognized by header sniffing:
  1. WORKOUTS: a row per activity (Apple Health "Workout Summary" style or
     any CSV with start/end/sport columns) -> canonical `activities`
     (data_completeness='manual', source='csv_import').
  2. DAILY: a row per day with metric columns (steps, weight_kg,
     body_fat_pct, resting_hr, spo2_avg, hrv_ms) -> `daily_biometrics`
     field-merge (populated canonical fields are never degraded) and
     hrv_ms -> `hrv_readings` overnight_avg at 07:00 local.

Header names are matched case-insensitively with an alias table so both
Apple Health export vocab ("Workout Type", "Start Time", "Energy Burned
(kcal)") and plain normalized vocab ("sport", "start_time", "calories")
work. Importing is idempotent (per-file external_id hash) and unknown
rows are skipped with a counted reason — never partial-visible.
"""

import csv
import hashlib
import io
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink, Discipline
from app.models.wellness import DailyBiometric, HrvReading
from app.services.biometric_provenance import set_biometric
from app.connectors.validation import (
    valid_body_fat_pct, valid_hrv_ms, valid_resting_hr_bpm,
    valid_spo2_pct, valid_weight_kg,
)

logger = logging.getLogger("services.csv_import")

SOURCE = "csv_import"

# ---- header aliases (lowercased, stripped) ----------------------------------

_WORKOUT_HEADERS = {
    "start": ["start time", "start_time", "start_date", "start", "date"],
    "end": ["end time", "end_time", "end_date", "end"],
    "sport": ["workout type", "workout_type", "sport", "sport_type", "type", "activity"],
    "duration": ["duration_s", "duration (s)", "duration (min)", "duration", "elapsed_time", "elapsed time (min)", "elapsed time"],
    "distance": ["distance (km)", "distance_km", "distance_m", "distance", "distance (m)"],
    "calories": ["energy burned (kcal)", "energy burned", "calories", "calories (kcal)", "active energy (kcal)"],
    "avg_hr": ["average heart rate (bpm)", "avg_hr", "average heart rate", "avg heart rate"],
    "max_hr": ["max heart rate (bpm)", "max_hr", "maximum heart rate", "max heart rate"],
}

_DAILY_HEADERS = {
    "steps": ["steps", "step count", "step_count"],
    "weight": ["weight (kg)", "weight_kg", "weight", "body mass (kg)"],
    "body_fat": ["body fat (%)", "body_fat_pct", "body fat percentage", "body fat"],
    "resting_hr": ["resting heart rate (bpm)", "resting_hr", "resting heart rate"],
    "spo2": ["spo2 (%)", "spo2_avg", "spo2", "oxygen saturation (%)", "blood oxygen (%)"],
    "hrv": ["hrv (ms)", "hrv_ms", "hrv", "heart rate variability (ms)"],
    "sleep_min": ["sleep (min)", "sleep_minutes", "sleep duration (min)", "time asleep (min)"],
}


@dataclass
class ImportReport:
    rows_seen: int = 0
    activities_upserted: int = 0
    biometrics_upserted: int = 0
    hrv_upserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "rows_seen": self.rows_seen,
            "activities_upserted": self.activities_upserted,
            "biometrics_upserted": self.biometrics_upserted,
            "hrv_upserted": self.hrv_upserted,
            "skipped": self.skipped,
            "errors": self.errors[:20],
        }


def _norm_header(h: str) -> str:
    return " ".join(h.strip().lower().split())


def _map_headers(headers: list[str], table: dict[str, list[str]]) -> dict[str, str]:
    """canonical field -> actual column name (alias table, case-insensitive)."""
    lookup = {_norm_header(h): h for h in headers}
    found: dict[str, str] = {}
    for canonical, aliases in table.items():
        for alias in aliases:
            if alias in lookup:
                found[canonical] = lookup[alias]
                break
    return found


def _parse_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _parse_dt(value: object, tz: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = (
        "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M", "%Y-%m-%d",
    )
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed
    return None


def _sniff_kind(headers: list[str]) -> str:
    w = _map_headers(headers, _WORKOUT_HEADERS)
    d = _map_headers(headers, _DAILY_HEADERS)
    if "start" in w and ("sport" in w or "end" in w or "duration" in w):
        return "workouts"
    if "date" in {_norm_header(h) for h in headers} and d:
        return "daily"
    if d:
        return "daily"
    return "unknown"


def _external_id(*parts: object) -> str:
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return digest[:40]


_CSV_SPORT_ALIASES = {
    "run": "running",
    "running": "running",
    "trailrun": "running",
    "hike": "hiking",
    "hiking": "hiking",
    "walk": "walking",
    "walking": "walking",
    "ride": "road_cycling",
    "roadbike": "road_cycling",
    "roadcycling": "road_cycling",
    "cycling": "road_cycling",
    "gravelride": "gravel_cycling",
    "gravelcycling": "gravel_cycling",
    "mountainbikeride": "mountain_biking",
    "mountainbiking": "mountain_biking",
    "mountainbike": "mountain_biking",
    "emountainbikeride": "mountain_biking",
    "downhillbiking": "mountain_biking",
    "gravelbike": "gravel_cycling",
    "swim": "swimming",
    "swimming": "swimming",
    "lapswimming": "swimming",
    "poolswimming": "swimming",
    "openwaterswimming": "swimming",
    "row": "rowing",
    "rowing": "rowing",
    "yoga": "yoga",
    "pilates": "pilates",
    "strengthtraining": "strength",
    "weighttraining": "strength",
    "weightlifting": "strength",
    "gym": "gym_general",
    "gymgeneral": "gym_general",
    "workout": "gym_general",
    "strength": "strength",
    "skiing": "skiing",
    "tennis": "tennis",
    "surf": "surf",
    "snowboard": "snowboard",
    "kitesurf": "kitesurf",
    "windsurf": "windsurf",
    "wakeboard": "wakeboard",
    "sail": "sailing",
    "sailing": "sailing",
    "skitour": "skiing",
    "alpineski": "skiing",
    "nordicski": "skiing",
    "surfing": "surf",
    "snowboarding": "snowboard",
    "kitesurfing": "kitesurf",
    "windsurfing": "windsurf",
    "wakeboarding": "wakeboard",
    "enduro": "enduro",
    "enduromotorcycling": "enduro",
}


def _csv_discipline_name(sport: str | None) -> str | None:
    if not sport:
        return None
    key = re.sub(r"[^a-z0-9]", "", sport.strip().lower())
    return _CSV_SPORT_ALIASES.get(key)


# ---------------------------------------------------------------- workouts


async def _import_workouts(
    session: AsyncSession,
    user_id: int,
    rows: list[dict[str, str]],
    tz: ZoneInfo,
    report: ImportReport,
    filename: str,
) -> None:
    headers = list(rows[0].keys()) if rows else []
    cols = _map_headers(headers, _WORKOUT_HEADERS)
    discipline_rows = await session.execute(select(Discipline.name, Discipline.id))
    discipline_index = dict(discipline_rows.all())
    for idx, row in enumerate(rows):
        report.rows_seen += 1
        start = _parse_dt(row.get(cols.get("start")), tz)
        if start is None:
            report.skipped += 1
            report.errors.append(f"workouts row {idx + 2}: unparsable start time")
            continue
        end = _parse_dt(row.get(cols.get("end")), tz)
        duration_s: int | None = None
        if end is not None and end > start:
            duration_s = int((end - start).total_seconds())
        elif "duration" in cols:
            duration = _parse_number(row.get(cols["duration"]))
            if duration is not None and duration > 0:
                header = _norm_header(cols["duration"])
                # Explicit minute columns are minutes; generic duration and
                # elapsed_time follow canonical seconds. Never guess by size.
                duration_s = int(duration * 60) if "(min)" in header else int(duration)
        if duration_s is None or duration_s <= 0:
            report.skipped += 1
            report.errors.append(f"workouts row {idx + 2}: no duration")
            continue
        sport_value = row.get(cols.get("sport")) if cols.get("sport") else None
        sport = sport_value.strip() if sport_value and sport_value.strip() else None
        discipline_name = _csv_discipline_name(sport)
        distance = _parse_number(row.get(cols.get("distance")))
        distance_header = _norm_header(cols.get("distance", ""))
        distance_m = None if distance is None else round(
            distance * 1000 if distance_header in {"distance (km)", "distance_km"} else distance
        )
        calories = _parse_number(row.get(cols.get("calories")))
        avg_hr = _parse_number(row.get(cols.get("avg_hr")))
        max_hr = _parse_number(row.get(cols.get("max_hr")))

        external_id = _external_id(
            filename, start.isoformat(), sport, duration_s, distance_m
        )
        link = await session.scalar(
            select(ActivitySourceLink).where(
                ActivitySourceLink.source == SOURCE,
                ActivitySourceLink.external_id == external_id,
                ActivitySourceLink.user_id == user_id,
            )
        )
        if link is not None:
            report.skipped += 1  # already imported
            continue
        activity = Activity(
            user_id=user_id,
            discipline_id=discipline_index.get(discipline_name),
            start_time=start,
            start_tz_offset_minutes=(
                int(start.utcoffset().total_seconds() // 60) if start.utcoffset() else 0
            ),
            local_date=start.astimezone(tz).date(),
            duration_s=duration_s,
            distance_m=distance_m,
            elevation_gain_m=None,
            avg_hr=int(avg_hr) if avg_hr is not None else None,
            max_hr=int(max_hr) if max_hr is not None else None,
            calories=int(calories) if calories is not None else None,
            training_load=None,
            data_completeness="manual",
            source_metrics={"csv_import": {"sport_raw": sport, "file": filename}},
        )
        session.add(activity)
        await session.flush()
        session.add(
            ActivitySourceLink(
                user_id=user_id,
                activity_id=activity.id,
                source=SOURCE,
                external_id=external_id,
            )
        )
        report.activities_upserted += 1


# ------------------------------------------------------------------- daily


async def _import_daily(
    session: AsyncSession,
    user_id: int,
    rows: list[dict[str, str]],
    tz: ZoneInfo,
    report: ImportReport,
) -> None:
    headers = list(rows[0].keys()) if rows else []
    cols = _map_headers(headers, _DAILY_HEADERS)
    date_col_actual = next(
        (h for h in headers if _norm_header(h) in ("date", "day")), None
    )
    if date_col_actual is None:
        report.errors.append("daily CSV: no date column found")
        return
    for idx, row in enumerate(rows):
        report.rows_seen += 1
        day = _parse_dt(row.get(date_col_actual), tz)
        if day is None:
            report.skipped += 1
            report.errors.append(f"daily row {idx + 2}: unparsable date")
            continue
        day_d = day.date()

        steps = _parse_number(row.get(cols.get("steps")))
        weight = _parse_number(row.get(cols.get("weight")))
        body_fat = _parse_number(row.get(cols.get("body_fat")))
        rhr = _parse_number(row.get(cols.get("resting_hr")))
        spo2 = _parse_number(row.get(cols.get("spo2")))
        hrv = _parse_number(row.get(cols.get("hrv")))
        weight = valid_weight_kg(weight)
        body_fat = valid_body_fat_pct(body_fat)
        rhr = valid_resting_hr_bpm(rhr)
        spo2 = valid_spo2_pct(spo2)
        hrv = valid_hrv_ms(hrv)
        if steps is not None and steps < 0:
            steps = None

        if all(v is None for v in (steps, weight, body_fat, rhr, spo2, hrv)):
            report.skipped += 1
            continue

        bio = await session.scalar(
            select(DailyBiometric).where(
                DailyBiometric.user_id == user_id, DailyBiometric.date == day_d
            )
        )
        if bio is None:
            bio = DailyBiometric(user_id=user_id, date=day_d)
            session.add(bio)
        if steps is not None and bio.steps is None:
            set_biometric(bio, "steps", int(steps), "csv_import")
        if weight is not None and bio.weight_kg is None:
            set_biometric(bio, "weight_kg", Decimal(str(weight)), "csv_import")
        if body_fat is not None and bio.body_fat_pct is None:
            set_biometric(bio, "body_fat_pct", Decimal(str(body_fat)), "csv_import")
        if rhr is not None and bio.resting_hr is None:
            set_biometric(bio, "resting_hr", int(rhr), "csv_import")
        if spo2 is not None and bio.spo2_avg is None:
            set_biometric(bio, "spo2_avg", Decimal(str(spo2)), "csv_import")
        report.biometrics_upserted += 1

        if hrv is not None and hrv > 0:
            ts = datetime.combine(day_d, time(7, 0), tzinfo=tz)
            existing = await session.scalar(
                select(HrvReading).where(
                    HrvReading.user_id == user_id,
                    HrvReading.timestamp == ts,
                    HrvReading.reading_type == "unspecified",
                    HrvReading.origin == "csv_import",
                )
            )
            if existing is None:
                session.add(
                    HrvReading(
                        user_id=user_id,
                        timestamp=ts,
                        hrv_ms=hrv,
                        reading_type="unspecified",
                        origin="csv_import",
                        method=None,
                        rolling_baseline_ms=None,
                    )
                )
                report.hrv_upserted += 1


# ------------------------------------------------------------------- entry


async def import_csv(
    session: AsyncSession,
    user_id: int,
    filename: str,
    content: str | bytes,
    timezone_name: str = "Europe/Rome",
) -> ImportReport:
    from app.services.evidence import scope_lock
    await scope_lock(session, user_id, "changes")
    tz = ZoneInfo(timezone_name)
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    report = ImportReport()
    rows = []
    try:
        for row in reader:
            if None in row:
                report.skipped += 1
                report.errors.append("CSV row contains more values than headers")
                continue
            if any((v or "").strip() for v in row.values()):
                rows.append(row)
    except csv.Error:
        report.errors.append("Invalid CSV or a field exceeds the allowed size")
        return report
    if not rows:
        report.errors.append("CSV has no data rows")
        return report
    kind = _sniff_kind(list(rows[0].keys()))
    if kind == "workouts":
        await _import_workouts(session, user_id, rows, tz, report, filename)
    elif kind == "daily":
        await _import_daily(session, user_id, rows, tz, report)
    else:
        report.errors.append(
            "unrecognized CSV shape — need workout columns (start/end/sport) "
            "or a daily metrics CSV with a date column"
        )
    return report
