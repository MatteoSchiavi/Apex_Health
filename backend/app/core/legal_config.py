"""Public, deployment-specific facts used by the legal notices.

These are deliberately separate from secrets and cannot assert that a deployment
has completed a legal review merely because the page is reachable.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import REPO_ROOT


class LegalConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    legal_controller_name: str = ""
    legal_controller_address: str = ""
    legal_contact_email: str = ""
    legal_hosting_region: str = ""
    legal_effective_date: str = ""
    legal_account_basis: str = ""
    legal_health_basis: str = ""
    # A deployment must inspect its actual contracts and endpoint configuration.
    # These are human-readable public facts, not credentials or endpoint URLs.
    legal_ai_processor: str = ""
    legal_backup_location: str = ""
    legal_transfer_details: str = ""


@lru_cache
def get_legal_config() -> LegalConfig:
    return LegalConfig()
