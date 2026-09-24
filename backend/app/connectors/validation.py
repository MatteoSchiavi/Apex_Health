"""Physiological plausibility validators (P-02 audit fix).

Sensor artifacts (firmware glitches, loose straps, malformed API responses)
that fall outside published physiological ranges are dropped at INGEST time
so they cannot corrupt daily aggregates, recovery scores, or illness alerts.
Raw rows are preserved in ``raw_ingest`` for replay — only the typed,
queryable columns are filtered.

Ranges are deliberately permissive (capture firmware glitches, not edge-case
athletes). A 2 ms floor on HRV tolerates severe illness; 400 ms tolerates
elite vagal tone. RHR 25–120 covers bradycardic athletes through tachycardic
illness. SpO₂ 70–100 covers everything short of cyanosis.

These validators are the single canonical source used by every connector's
normalizer — the audit (P-02) flags their absence across all normalize.py
files. Add new ranges here, never inline.
"""

from __future__ import annotations

from decimal import Decimal
from typing import SupportsFloat

# Physiological bounds — published clinical plausibility windows.
# Values outside these windows are sensor artifacts (firmware glitches, loose
# straps, malformed responses) and are dropped at ingest before they enter
# daily aggregates, recovery scores, or illness alerts.
PHYSIO_HRV_RANGE_MS: tuple[float, float] = (2.0, 400.0)
PHYSIO_RESTING_HR_RANGE_BPM: tuple[int, int] = (25, 120)
PHYSIO_SPO2_RANGE_PCT: tuple[float, float] = (70.0, 100.0)
PHYSIO_STRESS_RANGE: tuple[float, float] = (0.0, 100.0)
PHYSIO_BODY_BATTERY_RANGE: tuple[float, float] = (0.0, 100.0)
PHYSIO_SLEEP_SCORE_RANGE: tuple[float, float] = (0.0, 100.0)
PHYSIO_RESPIRATION_RANGE_BPM: tuple[float, float] = (5.0, 60.0)
PHYSIO_WEIGHT_RANGE_KG: tuple[float, float] = (25.0, 400.0)
PHYSIO_BODY_FAT_PCT_RANGE: tuple[float, float] = (3.0, 65.0)


def _to_float(value: object) -> float | None:
    """Coerce Decimal/int/float to float; None stays None. Non-numeric → None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, SupportsFloat):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _in_range(value: float, lo: float, hi: float) -> bool:
    """Inclusive bounds — boundary values are physiologically possible."""
    return lo <= value <= hi


def valid_hrv_ms(value: object) -> float | None:
    """Return ``value`` when physiologically plausible (2–400 ms), else None.

    P-02 audit: a 0.5 ms Oura glitch or a 9999 ms stuck reading must NOT
    enter daily HRV means — they would saturate recovery components and
    trigger simultaneous false illness alerts and false maximal recovery
    scores depending on the direction."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_HRV_RANGE_MS):
        return None
    return v


def valid_resting_hr_bpm(value: object) -> int | None:
    """Return ``value`` when physiologically plausible (25–120 bpm), else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_RESTING_HR_RANGE_BPM):
        return None
    return round(v)


def valid_spo2_pct(value: object) -> float | None:
    """Return ``value`` when physiologically plausible (70–100%), else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_SPO2_RANGE_PCT):
        return None
    return v


def valid_stress_level(value: object) -> float | None:
    """Return ``value`` when in (0–100) Garmin stress range, else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_STRESS_RANGE):
        return None
    return v


def valid_body_battery(value: object) -> float | None:
    """Return ``value`` when in (0–100) body-battery range, else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_BODY_BATTERY_RANGE):
        return None
    return v


def valid_sleep_score(value: object) -> float | None:
    """Return ``value`` when in (0–100) sleep-score range, else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_SLEEP_SCORE_RANGE):
        return None
    return v


def valid_respiration_bpm(value: object) -> float | None:
    """Return ``value`` when in (5–60) breaths-per-minute, else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_RESPIRATION_RANGE_BPM):
        return None
    return v


def valid_weight_kg(value: object) -> float | None:
    """Return ``value`` when in (25–400 kg), else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_WEIGHT_RANGE_KG):
        return None
    return v


def valid_body_fat_pct(value: object) -> float | None:
    """Return ``value`` when in (3–65%), else None."""
    v = _to_float(value)
    if v is None:
        return None
    if not _in_range(v, *PHYSIO_BODY_FAT_PCT_RANGE):
        return None
    return v


# SQL CHECK constraint snippets mirroring the validators above. These are
# applied by a new Alembic migration (0008_physio_check_constraints) so the
# DB layer is also defended — a row that bypasses Python (direct SQL, a
# future connector) is rejected at the column level too.
SQL_CHECK_CONSTRAINTS: dict[str, str] = {
    "hrv_readings.hrv_ms": "hrv_ms BETWEEN 2 AND 400",
    "daily_biometrics.resting_hr": "resting_hr IS NULL OR resting_hr BETWEEN 25 AND 120",
    "daily_biometrics.spo2_avg": "spo2_avg IS NULL OR spo2_avg BETWEEN 70 AND 100",
    "daily_biometrics.weight_kg": "weight_kg IS NULL OR weight_kg BETWEEN 25 AND 400",
    "daily_biometrics.body_fat_pct": "body_fat_pct IS NULL OR body_fat_pct BETWEEN 3 AND 65",
    "sleep_sessions.spo2_avg": "spo2_avg IS NULL OR spo2_avg BETWEEN 70 AND 100",
    "sleep_sessions.sleep_score": "sleep_score IS NULL OR sleep_score BETWEEN 0 AND 100",
    "sleep_sessions.respiration_avg": "respiration_avg IS NULL OR respiration_avg BETWEEN 5 AND 60",
    "stress_readings.stress_level": "stress_level IS NULL OR stress_level BETWEEN 0 AND 100",
    "stress_readings.body_battery": "body_battery IS NULL OR body_battery BETWEEN 0 AND 100",
}
