"""Garmin API client factory. Password sessions are no longer supported.

Credentials are encrypted on the owning integration row. Construction performs
no provider I/O and never falls back to server-wide credentials.
"""
from typing import Any
from app.connectors.garmin.transport import GarminTransport

class GarminAuthError(Exception):
    """Reconnect the owning account using its Garmin API key."""

GarminClient = GarminTransport

def build_live_client(credentials: dict[str, Any] | None) -> GarminTransport:
    if not isinstance(credentials, dict) or credentials.get("auth_type") != "personal_api_key":
        raise GarminAuthError("Reconnect Garmin API with a Personal API key; password sessions are no longer supported")
    from app.connectors.garmin.personal import GarminPersonalClient
    return GarminPersonalClient(credentials)
