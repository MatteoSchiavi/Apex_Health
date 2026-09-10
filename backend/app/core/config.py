"""Application settings (MASTER_SPEC §5). Reads .env at the repo root."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    database_url: str
    redis_url: str
    session_secret: str
    encryption_key: str

    # --- Owner bootstrap (§15) ---
    owner_email: str
    owner_password: str

    # --- Tunables (spec defaults) ---
    environment: str = "dev"
    # §22: session cookies are short-lived with sliding expiry.
    session_ttl_minutes: int = 720
    # §22.1: 5 failed attempts per email per 15 minutes -> temporary lockout.
    login_window_minutes: int = 15
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
