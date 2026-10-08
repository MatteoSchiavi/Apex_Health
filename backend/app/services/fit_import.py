"""Original FIT import. Preserve bytes, sport boundaries and recorded channels."""

import io
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.core.encryption import encrypt_bytes
from app.models.activity import Activity, ActivitySourceLink, ActivityStream, Discipline
from app.models.integration import RawIngest
from app.models.lab import LabDocument
from app.services.evidence import EvidenceError, scope_lock
from app.services.fit_enrichment import parse_fit_laps, upsert_laps

SPORTS = {
    "running": "running",
    "cycling": "road_cycling",
    "swimming": "swimming",
    "training": "strength",
    "alpine_skiing": "alpine_skiing",
    "sailing": "sailing",
}


def parse_original(content):
    import fitdecode

    sessions, records = [], []
    try:
        with fitdecode.FitReader(
            io.BytesIO(content), check_crc=fitdecode.CrcCheck.RAISE
        ) as reader:
            for frame in reader:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name not in ("session", "record"):
                    continue
                fields = {f.name: f.value for f in frame.fields if f.value is not None}
                if frame.name == "session":
                    sessions.append(fields)
                else:
                    records.append(fields)
                if len(sessions) > 32 or len(records) > 100000:
                    raise EvidenceError(
                        "INVALID_ARGUMENTS", "FIT import exceeds session/sample limits"
                    )
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError(
            "INVALID_ARGUMENTS",
            "Invalid FIT file or CRC; original bytes were not imported",
        ) from None
    if not sessions:
        raise EvidenceError(
            "INVALID_ARGUMENTS", "FIT file has no activity session summary"
        )
    for item in sessions:
        start, duration = item.get("start_time"), item.get("total_timer_time")
        if (
            not isinstance(start, datetime)
            or duration is None
            or not math.isfinite(float(duration))
            or not 1 <= float(duration) <= 86400
        ):
            raise EvidenceError(
                "INVALID_ARGUMENTS",
                "FIT session requires a start and recorded duration of at most 24 hours",
            )
    return sessions, records, parse_fit_laps(content)


async def import_original(session, user, filename, content, parsed):
    import hashlib

    sha = hashlib.sha256(content).hexdigest()
    await scope_lock(session, user.id, "changes")
    await scope_lock(session, user.id, "fit_import")
    existing = (
        await session.scalars(
            select(ActivitySourceLink).where(
                ActivitySourceLink.user_id == user.id,
                ActivitySourceLink.source == "fit",
                ActivitySourceLink.external_id.like(sha + ":%"),
            )
        )
    ).all()
    if existing:
        return {
            "activity_ids": [r.activity_id for r in existing],
            "already_imported": True,
            "file_hash": sha,
        }
    source = LabDocument(
        user_id=user.id,
        filename=filename[:200],
        media_type="application/vnd.ant.fit",
        content_hash=sha,
        ciphertext=encrypt_bytes(content),
        status="source_file",
    )
    session.add(source)
    await session.flush()
    summaries, records, laps = parsed
    tz, ids = ZoneInfo(user.timezone), []
    for number, summary in enumerate(summaries):
        start = (
            summary["start_time"].replace(tzinfo=UTC)
            if summary["start_time"].tzinfo is None
            else summary["start_time"].astimezone(UTC)
        )
        duration = round(summary["total_timer_time"])
        sport = str(summary.get("sport", "unknown"))
        raw = RawIngest(
            user_id=user.id,
            source="fit",
            payload_type="original_session",
            fetched_at=datetime.now(UTC),
            raw_json={
                "original_document_id": source.id,
                "file_hash": sha,
                "sport": sport,
                "summary": {
                    k: str(v) if isinstance(v, (datetime, bytes)) else v
                    for k, v in summary.items()
                },
            },
            processed=True,
        )
        session.add(raw)
        await session.flush()
        discipline = await session.scalar(
            select(Discipline.id).where(Discipline.name == SPORTS.get(sport, sport))
        )
        activity = Activity(
            user_id=user.id,
            discipline_id=discipline,
            start_time=start,
            start_tz_offset_minutes=int(
                start.astimezone(tz).utcoffset().total_seconds() / 60
            ),
            local_date=start.astimezone(tz).date(),
            duration_s=duration,
            distance_m=summary.get("total_distance"),
            avg_hr=summary.get("avg_heart_rate"),
            max_hr=summary.get("max_heart_rate"),
            avg_power=summary.get("avg_power"),
            np_power=summary.get("normalized_power"),
            calories=summary.get("total_calories"),
            elevation_gain_m=summary.get("total_ascent"),
            data_completeness="partial",
            source_metrics={"fit": {"sport": sport, "file_hash": sha}},
        )
        candidates = (
            (
                await session.scalars(
                    select(Activity)
                    .where(
                        Activity.user_id == user.id,
                        Activity.discipline_id == discipline,
                        Activity.start_time.between(
                            start - timedelta(seconds=2), start + timedelta(seconds=2)
                        ),
                        func.abs(Activity.duration_s - duration)
                        <= max(5, duration * 0.01),
                    )
                    .with_for_update()
                )
            ).all()
            if discipline is not None
            else []
        )
        if len(candidates) == 1:
            from app.connectors.reconciliation import reconcile_activity

            candidate = candidates[0]
            values = {
                k: getattr(activity, k)
                for k in (
                    "distance_m",
                    "elevation_gain_m",
                    "avg_hr",
                    "max_hr",
                    "avg_power",
                    "np_power",
                    "calories",
                )
            }
            await reconcile_activity(
                session,
                existing=candidate,
                incoming_values=values,
                source="fit",
                external_id=f"{sha}:{number}",
                raw_ingest_id=raw.id,
            )
            candidate.source_metrics = {
                **(candidate.source_metrics or {}),
                "fit": {"sport": sport, "file_hash": sha},
            }
            activity = candidate
        else:
            session.add(activity)
            await session.flush()
            session.add(
                ActivitySourceLink(
                    user_id=user.id,
                    activity_id=activity.id,
                    source="fit",
                    external_id=f"{sha}:{number}",
                    raw_ingest_id=raw.id,
                )
            )
        ids.append(activity.id)
        if SPORTS.get(sport, sport) == "strength":
            from app.services.exercise_catalog import fit_exercises

            exercises = fit_exercises(content, start, summary.get("timestamp") or start + timedelta(seconds=duration))
            activity.source_metrics = {
                **(activity.source_metrics or {}),
                "fit": {**(activity.source_metrics or {}).get("fit", {}), "exercises": exercises},
            }
        samples = {}
        end = summary.get("timestamp")
        for record in records:
            stamp = record.get("timestamp")
            if not isinstance(stamp, datetime):
                continue
            stamp = stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp
            offset = round((stamp - start).total_seconds())
            # Session elapsed time can include pauses; keep original offsets.
            if offset < 0 or offset > 86400 or (end and stamp > end):
                continue
            if (
                number + 1 < len(summaries)
                and stamp >= summaries[number + 1]["start_time"]
            ):
                continue
            row = {
                "activity_id": activity.id,
                "t_offset_s": offset,
                **dict.fromkeys(
                    ("hr", "power", "cadence", "speed", "altitude", "lat", "lon")
                ),
            }
            for src, dest in (
                ("heart_rate", "hr"),
                ("power", "power"),
                ("cadence", "cadence"),
                ("enhanced_speed", "speed"),
                ("enhanced_altitude", "altitude"),
            ):
                value = record.get(src, record.get(src.removeprefix("enhanced_")))
                if (
                    isinstance(value, (int, float))
                    and math.isfinite(value)
                    and (dest == "altitude" or value >= 0)
                ):
                    row[dest] = value
            for src, dest in (("position_lat", "lat"), ("position_long", "lon")):
                if isinstance(record.get(src), (int, float)):
                    row[dest] = record[src] * 180 / (2**31)
            samples[offset] = row
        if samples:
            activity.data_completeness = "full"
        for offset in range(0, len(samples), 1000):
            await session.execute(
                insert(ActivityStream)
                .values(list(samples.values())[offset : offset + 1000])
                .on_conflict_do_nothing()
            )
        owned_laps = [
            l
            for l in laps
            if l.get("start_time")
            and l["start_time"] >= start
            and (not end or l["start_time"] < end)
        ]
        for i, lap in enumerate(owned_laps):
            lap["lap_index"] = i + 1
        await upsert_laps(session, activity.id, owned_laps)
    return {
        "activity_ids": ids,
        "already_imported": False,
        "file_hash": sha,
        "original_document_id": source.id,
    }
