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

    # --- Garmin connector (§5, §23 Phase 1) ---
    garmin_email: str = ""
    garmin_password: str = ""
    # §19 note: an unofficial client polled continuously raises ban risk —
    # every paginated remote call is paced by this delay.
    garmin_page_delay_seconds: float = 2.0
    garmin_activity_page_size: int = 50
    # §6.3: backfill walks wellness history backwards until this many
    # consecutive data-empty days — the source's real history boundary.
    garmin_backfill_empty_gap_days: int = 10

    # --- Telegram bot (§5, §10: long polling, no webhook secret this round) ---
    telegram_bot_token: str = ""

    # --- LLM providers (§5, §8.1, §9): env-var swappable, no code change ---
    llm_provider_cheap: str = "glm-4.7-flash"
    llm_provider_powerful: str = "glm-5.2"
    glm_api_key: str = ""
    # OpenAI-compatible chat-completions endpoint for the GLM family.
    glm_api_base: str = "https://open.bigmodel.cn/api/paas/v4"

    # --- STT (§2, §5: OpenAI Whisper — voice notes are short) ---
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    whisper_model: str = "whisper-1"

    # --- Cost governance (§8.6): the daily budget task sums the day's
    # estimated token_usage cost per user; crossing this fires an
    # informational budget_warning alert (not a hard stop). <=0 disables.
    daily_token_budget_usd: float = 0.25

    # --- Tunables (spec defaults) ---
    environment: str = "dev"
    # §22: session cookies are short-lived with sliding expiry.
    session_ttl_minutes: int = 720
    # §22.1: 5 failed attempts per email per 15 minutes -> temporary lockout.
    login_window_minutes: int = 15
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    # §23 Phase 4 low-ferritin rule: ng/mL cutoff when a panel carries no
    # lab-provided reference low. A judgment call the spec leaves open —
    # surfaced here as the single documented tunable.
    low_ferritin_ng_ml: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
