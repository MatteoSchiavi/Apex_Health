"""Index WHOOP's compatible measurements with their own provider context."""

from app.connectors.validation import (
    valid_hrv_ms,
    valid_respiration_bpm,
    valid_resting_hr_bpm,
    valid_sleep_score,
    valid_spo2_pct,
    valid_weight_kg,
)
from app.connectors.whoop.normalize import _millis_to_s, _safe_dt
from app.services.evidence import METRICS, record_observation, update_feed


async def index_whoop_payload(session, raw, payload, tz):
    kind = raw.payload_type
    if kind not in {"sleep", "recovery", "body_measurement"}:
        return
    if kind == "sleep" and payload.get("nap") is True:
        return
    score = payload.get("score") or {}
    metrics = {
        "sleep": ("sleep_duration", "whoop_sleep_performance", "respiration"),
        "recovery": ("hrv_overnight_rmssd", "resting_hr", "spo2"),
        "body_measurement": ("weight",),
    }[kind]
    if payload.get("score_state") not in (None, "SCORED"):
        for metric in metrics:
            await update_feed(session, raw.user_id, "whoop", metric, "pending_sync", raw.fetched_at)
        return
    context = {
        "provider": "whoop", "api_version": "v2", "feed": kind,
        "device_id": payload.get("device_id") or payload.get("deviceId"),
        "aggregation_window": "provider-defined",
        "reading_context": "overnight" if kind in {"sleep", "recovery"} else "body_measurement",
        "provider_timezone_offset": payload.get("timezone_offset"),
    }
    if kind == "sleep":
        measured = _safe_dt(payload.get("end"))
        stages = score.get("stage_summary") or {}
        parts = [_millis_to_s(stages.get(key)) for key in (
            "total_light_sleep_time_milli", "total_slow_wave_sleep_time_milli", "total_rem_sleep_time_milli",
        )]
        records = {
            "sleep_duration": sum(parts) / 3600 if all(p is not None for p in parts) else None,
            "whoop_sleep_performance": valid_sleep_score(score.get("sleep_performance_percentage")),
            "respiration": valid_respiration_bpm(score.get("respiratory_rate")),
        }
        source_key = f"sleep:{payload.get('id') or payload.get('start')}"
        context.update({
            "sleep_start": payload.get("start"), "sleep_end": payload.get("end"),
            "sleep_id": payload.get("id"), "score_semantics": "WHOOP sleep performance percentage",
            "stage_seconds": {
                "light": parts[0], "deep": parts[1], "rem": parts[2],
                "awake": _millis_to_s(stages.get("total_awake_time_milli")),
                "no_data": _millis_to_s(stages.get("total_no_data_time_milli")),
            },
        })
    elif kind == "recovery":
        measured = _safe_dt(payload.get("sleep_end")) or _safe_dt(payload.get("cycle_start"))
        records = {
            "hrv_overnight_rmssd": valid_hrv_ms(score.get("hrv_rmssd_milli")),
            "resting_hr": valid_resting_hr_bpm(score.get("resting_heart_rate")),
            "spo2": valid_spo2_pct(score.get("spo2_percentage")),
        }
        source_key = f"recovery:{payload.get('cycle_id') or payload.get('sleep_id')}"
        context.update({
            "sleep_id": payload.get("sleep_id"), "cycle_id": payload.get("cycle_id"),
            "sleep_end": payload.get("sleep_end"), "cycle_start": payload.get("cycle_start"),
            "hrv_method": "RMSSD", "user_calibrating": score.get("user_calibrating"),
        })
    else:
        measured = raw.fetched_at
        records = {"weight": valid_weight_kg(payload.get("weight_kilogram"))}
        source_key = f"body_measurement:{measured.astimezone(tz).date()}"
        context["timestamp_kind"] = "retrieved_snapshot"
    if measured is None:
        return
    for metric, value in records.items():
        await update_feed(session, raw.user_id, "whoop", metric,
                          "available" if value is not None else "not_measured", raw.fetched_at, measured)
        await record_observation(
            session, user_id=raw.user_id, metric=metric, value=value,
            unit=METRICS[metric], origin="whoop", source_record_id=source_key,
            measured_at=measured, timezone=tz.key, fetched_at=raw.fetched_at,
            acquisition="official_api", raw_ingest_id=raw.id, metadata=context,
            quality_flags=["provider_calibrating"] if score.get("user_calibrating") else [],
        )
