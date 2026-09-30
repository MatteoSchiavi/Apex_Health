"""Oura connector — official API v2 (cloud.ouraring.com).

The ring's differentiators vs a watch: continuous night HRV at high
resolution, sleep staging good enough for a hypnogram, skin temperature
deviation, SpO2. Personal OAuth applications are allowed (no B2B gate),
so the owner registers once at cloud.ouraring.com and every user connects
through the standard authorization-code flow (shared oauth2 machinery).

Normalization law (annotation canon): values land in canonical columns only
where unit AND semantics match Garmin (seconds of sleep by stage, overnight
rMSSD HRV, SpO2 %). Oura-only quantities (temperature deviation delta,
readiness/sleep contribution splits) stay in source_metrics.oura — never
folded into unit-compatible columns with different meanings.
"""

from app.connectors.oura.client import OuraAuthError, OuraClient
from app.connectors.oura.flow import (
    OAuthFlowError,
    complete_authorization,
    create_pending_authorization,
    flow_settings_ready,
)
from app.connectors.oura.sync import run_user_sync_with_oura, sync_user_oura

__all__ = [
    "OuraAuthError",
    "OuraClient",
    "OAuthFlowError",
    "complete_authorization",
    "create_pending_authorization",
    "flow_settings_ready",
    "sync_user_oura",
    "run_user_sync_with_oura",
]
