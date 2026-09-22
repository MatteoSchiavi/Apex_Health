"""Whoop connector (official Developer API v2) — a first-class PRIMARY device
alongside Garmin (owner decision, 2026-09).

Annotation law (§17, sharpened after the Whoop spec review): Whoop quantities
are only written into canonical columns where unit AND semantics match what
the Garmin connector already writes. Everything else lands in
`source_metrics` JSONB — never merged into Garmin-comparable columns:

| Whoop field                          | Canonical target                       |
|--------------------------------------|----------------------------------------|
| sleep stages (ms)                    | sleep_sessions stage columns (SECONDS) |
| sleep_performance_percentage (0-100) | sleep_sessions.sleep_score (0-100)     |
| respiratory_rate                     | sleep_sessions.respiration_avg         |
| recovery.hrv_rmssd_milli (ms)        | hrv_readings (ms, overnight_avg)       |
| recovery.resting_heart_rate          | daily_biometrics.resting_hr            |
| recovery.spo2_percentage             | daily_biometrics.spo2_avg              |
| body.weight_kilogram                 | daily_biometrics.weight_kg             |
| workout kilojoule / 4.184            | activities.calories (kcal)             |
| workout strain (0-21)                | activities.source_metrics — NOT training_load |
| cycle strain (day strain 0-21)       | daily_biometrics.source_metrics        |
| recovery.recovery_score (0-100)      | daily_biometrics.source_metrics        |

Whoop has NO steps, NO body battery, NO stress model — those canonical
columns are simply never touched by this connector.
"""

from app.connectors.whoop.client import (
    LiveWhoopClient,
    WhoopAuthError,
    build_authorize_url,
    build_live_client,
)
from app.connectors.whoop.fetch import SOURCE, store_raw
from app.connectors.whoop.sync import sync_user_whoop

__all__ = [
    "SOURCE",
    "LiveWhoopClient",
    "WhoopAuthError",
    "build_authorize_url",
    "build_live_client",
    "store_raw",
    "sync_user_whoop",
]
