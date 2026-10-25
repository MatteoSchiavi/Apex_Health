"""Safe connection metadata for the owner settings screens."""

from typing import Literal

from app.core.encryption import decrypt_json
from app.models.integration import Integration

GarminAuthMethod = Literal["personal_api_key", "garmin_connect"]


def garmin_auth_method(
    integration: Integration, *, is_owner: bool
) -> GarminAuthMethod | None:
    """Inspect only the owner's active Garmin credentials; never expose secrets."""
    if (not is_owner or integration.provider != "garmin"
            or integration.status != "active" or not integration.credentials_encrypted):
        return None
    try:
        credentials = decrypt_json(integration.credentials_encrypted)
    except Exception:
        # A damaged credential must not prevent the owner opening Settings
        # to replace it. No ciphertext or exception text belongs in logs.
        return None
    if not isinstance(credentials, dict):
        return None
    if credentials.get("auth_type") == "personal_api_key":
        return "personal_api_key"
    if credentials.get("di_token") or credentials.get("di_refresh_token"):
        return "garmin_connect"
    return None
