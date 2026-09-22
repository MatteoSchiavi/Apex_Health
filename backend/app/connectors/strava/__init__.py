"""Strava connector (official REST API v3) — activity source #2.

Strava is the community/GPS companion: Whoop has no GPS/distance and no
public activity feed, so friends connect Strava for rides and runs while
Whoop carries recovery/sleep/strain. Annotation laws are identical to the
Whoop connector (§17): only unit-and-semantics-compatible fields land in
canonical columns — Strava's `relative_effort` is NOT comparable to
training_load and lives in source_metrics.

Rate limits (100 req/15min, 1000/day) are honored by pacing pages.
"""

from app.connectors.strava.client import (
    LiveStravaClient,
    StravaAuthError,
    build_authorize_url,
    build_live_client,
)
from app.connectors.strava.fetch import SOURCE, store_raw
from app.connectors.strava.sync import sync_user_strava

__all__ = [
    "SOURCE",
    "LiveStravaClient",
    "StravaAuthError",
    "build_authorize_url",
    "build_live_client",
    "store_raw",
    "sync_user_strava",
]
