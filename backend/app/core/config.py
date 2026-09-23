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

    # --- Technogym connector (§5, §11, §23 Phase 6) ---
    # §24: what the registered client may actually call (incl. prescription
    # push, §11b) only resolves when the owner registers at
    # developer.technogym.com and connects manually. Every endpoint is
    # therefore env-tunable — fix the URLs from the developer console at
    # registration time without touching code. Defaults follow the
    # enduser-to-enduser OAuth2 authorization-code sample.
    technogym_client_id: str = ""
    technogym_client_secret: str = ""
    technogym_redirect_uri: str = "http://localhost:8000/integrations/technogym/callback"
    technogym_oauth_authorize_url: str = "https://oauth.mywellness.com/Authorize/Authorize"
    technogym_oauth_token_url: str = "https://token.mywellness.com/oauth2/token"
    technogym_api_base: str = "https://api.mywellness.com/v4"
    technogym_scope: str = ""
    # §19 note: same reasoning as Garmin — paginated remote calls are paced.
    technogym_page_delay_seconds: float = 2.0
    technogym_activity_page_size: int = 50

    # --- Whoop connector (official Developer API v2, 2026-09 spec) ---
    # The owner registers an app at developer.whoop.com ("Create an app",
    # user OAuth type) and sets WHOOP_CLIENT_ID/SECRET; the redirect URI
    # registered there must equal WHOOP_REDIRECT_URI. Endpoint URLs below are
    # straight from the published OpenAPI spec (still env-tunable per §24 in
    # case Whoop revisions them). `offline` in the scope list is what makes
    # Whoop hand out a refresh token.
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_redirect_uri: str = "http://localhost:8000/integrations/whoop/callback"
    whoop_oauth_authorize_url: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
    whoop_oauth_token_url: str = "https://api.prod.whoop.com/oauth/oauth2/token"
    whoop_api_base: str = "https://api.prod.whoop.com/developer/v2"
    whoop_scope: str = (
        "offline read:profile read:body_measurement read:cycles "
        "read:recovery read:sleep read:workout"
    )
    # Whoop caps collections at 25 records/page — pages are cheap and paced
    # like every other connector (§19).
    whoop_page_size: int = 25
    whoop_page_delay_seconds: float = 0.5

    # --- Strava connector (official REST API v3) ---
    # Owner registers an API application at strava.com/settings/api; the
    # authorization flow is the standard OAuth2 authorization-code grant.
    # Strava enforces rate limits (100 requests / 15 min, 1000 / day) so
    # backfills page at 100 activities/request and sleep between pages.
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/integrations/strava/callback"
    strava_oauth_authorize_url: str = "https://www.strava.com/oauth/authorize"
    strava_oauth_token_url: str = "https://www.strava.com/oauth/token"
    strava_api_base: str = "https://www.strava.com/api/v3"
    strava_scope: str = "activity:read_all"
    strava_page_delay_seconds: float = 2.0
    strava_activity_page_size: int = 100

    # --- Oura connector (official API v2 — personal apps ARE allowed, so the
    # owner can register this one in minutes at cloud.ouraring.com) ---
    # Sleep stages (the ring's core advantage: 30s-class hypnogram), HRV,
    # temperature deviation, SpO2. Same normalization law: canonical columns
    # only where unit+semantics match Garmin; ring-specific values stay in
    # source_metrics.
    oura_client_id: str = ""
    oura_client_secret: str = ""
    oura_redirect_uri: str = "http://localhost:8000/integrations/oura/callback"
    oura_oauth_authorize_url: str = "https://cloud.ouraring.com/oauth/authorize"
    oura_oauth_token_url: str = "https://api.ouraring.com/oauth/token"
    oura_api_base: str = "https://api.ouraring.com/v2/usercollection"
    oura_scope: str = "daily sleep heartrate personal spo2 temperature"
    oura_page_size: int = 25
    oura_page_delay_seconds: float = 0.5

    # --- COROS connector (Open API, doc-first shell) ---
    # COROS requires a manual developer-portal application review before any
    # live key exists, so this ships as an approved-scope shell: config,
    # OAuth URLs, sync driver skeleton — owner applies, fills env, flow is
    # already wired.
    coros_client_id: str = ""
    coros_client_secret: str = ""
    coros_redirect_uri: str = "http://localhost:8000/integrations/coros/callback"
    coros_oauth_authorize_url: str = "https://open.coros.com/oauth2/authorize"
    coros_oauth_token_url: str = "https://open.coros.com/oauth2/token"
    coros_api_base: str = "https://open.coros.com"
    coros_scope: str = "base"

    # --- Telegram bot (§5, §10: long polling, no webhook secret this round) ---
    telegram_bot_token: str = ""

    # --- LLM providers (§5, §8.1, §9): env-var swappable, no code change ---
    llm_provider_cheap: str = "glm-4.7-flash"
    llm_provider_powerful: str = "glm-5.2"
    glm_api_key: str = ""
    # OpenAI-compatible chat-completions endpoint for the GLM family.
    glm_api_base: str = "https://open.bigmodel.cn/api/paas/v4"

    # Harness v3 (2026-09): per-tier endpoints so the MAIN model can be a
    # different vendor than the strategic one. Owner decision: DeepSeek is the
    # main (cheap) model. Empty values inherit glm_api_base/glm_api_key — one
    # key still runs the whole stack.
    llm_api_key_cheap: str = ""
    llm_api_base_cheap: str = ""      # e.g. https://api.deepseek.com/v1
    llm_api_key_powerful: str = ""
    llm_api_base_powerful: str = ""

    # Optional clinical tier (MedGemma or any OpenAI-compatible medical model).
    # Disabled by default; when enabled it only serves lab/medical intent and
    # always degrades to 'powerful' with a disclaimer prefix on any failure.
    medical_tier_enabled: bool = False
    llm_provider_medical: str = "medgemma-27b-it"
    llm_api_base_medical: str = ""
    llm_api_key_medical: str = ""

    # --- STT (§2, §5: OpenAI Whisper — voice notes are short) ---
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    whisper_model: str = "whisper-1"

    # --- Cost governance (§8.6): the daily budget task sums the day's
    # estimated token_usage cost per user; crossing this fires an
    # informational budget_warning alert (not a hard stop). <=0 disables.
    daily_token_budget_usd: float = 0.25

    # --- Weather connector (§5, §14, §23 Phase 7) ---
    # Open-Meteo is free and keyless; the only configuration it needs is WHERE
    # to ask about. Home coordinates are env-tunables (same §24 pattern as the
    # Technogym endpoints) — set WEATHER_HOME_LAT/WEATHER_HOME_LON in .env and
    # the forecast refresh starts producing rows; unset (0) disables the
    # scheduled refresh with a logged note instead of failing a beat tick.
    weather_home_lat: float = 0.0
    weather_home_lon: float = 0.0
    # §14: the cache exists to answer "when is a good training window" — seven
    # days of daily rows per refresh is the useful horizon.
    weather_forecast_days: int = 7
    # §14 nudge ("worth building once the pieces exist"): tomorrow's forecast
    # crosses the good-window test AND latest readiness >= threshold → one
    # proactive Telegram nudge per user per day. <=0 disables the nudge.
    weather_nudge_readiness_threshold: float = 70.0

    # --- Backups (§22.7, §19): nightly pg_dump, encrypted with a key DEDICATED
    # to backups (independent from ENCRYPTION_KEY so a leaked app key cannot
    # open backups and vice versa), retained 14 daily + 6 monthly archives.
    # Unset key => the nightly task logs an honest skip instead of writing a
    # plaintext dump (an unencrypted dump of health data must not exist).
    backup_encryption_key: str = ""
    backup_dir: str = str(REPO_ROOT / "backups")
    # Restore path needs a pg_dump/pg_restore-capable toolchain in PATH; overridable
    # for sandboxes and containers where the binary lives elsewhere.
    pg_dump_bin: str = "pg_dump"
    psql_bin: str = "psql"
    backup_retain_daily: int = 14
    backup_retain_monthly: int = 6

    # --- B2 offsite (§22.7: Backblaze B2 free tier) ---
    # Unset => uploads are skipped with a logged note; local encrypted copies
    # still happen so the restore drill never depends on a remote service.
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket: str = ""

    # --- Tunables (spec defaults) ---
    environment: str = "dev"
    # §15 remote access: when the app sits behind Tailscale Funnel / Caddy on
    # the same host, the TLS terminator forwards X-Forwarded-Proto/For over
    # plain HTTP. On (and only from loopback peers) the app adopts them —
    # see infra/tailscale-funnel-setup.md.
    trust_proxy_headers: bool = False
    # §22: session cookies are short-lived with sliding expiry.
    session_ttl_minutes: int = 720
    # §22.2 / STACK.md: Secure-flagged cookie for the TLS paths (Cloudflare
    # Tunnel / Tailscale serve / Caddy). Plain-HTTP LAN installs set
    # COOKIE_SECURE=false once in .env — browsers drop Secure cookies on
    # http:// origins, which would make login impossible there.
    cookie_secure: bool = True
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
