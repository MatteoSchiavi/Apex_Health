# Personal Health & Performance Control Center — MASTER SPECIFICATION (Production Revision)

This is the single source of truth. It supersedes every earlier document from this project's planning. This revision is a full pre-production audit: five real correctness gaps found in the prior draft are fixed in place (not patched around), and the production-hardening sections a "check everything" pass turns up (scheduled jobs, testing, observability, security) are now included. Nothing here needs a cross-reference to another file.

---

## 0. Instructions to the Building Agent

- Build phase by phase, in the order in Section 23. Don't start a phase until the previous one's acceptance criteria are demonstrably met.
- Section 6's DDL is authoritative. If exact TimescaleDB/pgvector syntax needs minor adjustment to run, adjust the syntax but preserve the structure.
- Section 17's constraints are hard requirements — they exist because earlier versions of this project shipped subtle bugs from violating exactly these rules.
- Anything marked configurable must actually be implemented as configurable, not hardcoded to one vendor.
- Section 24 lists items that need a human decision. Don't resolve them with a guess.
- This is a single-user-becomes-small-friend-group project. Don't add complexity (horizontal scaling, multi-region, elaborate admin tooling) that isn't asked for here.
- Seed data (Section 6.1) is loaded via an Alembic data migration, not invented ad hoc by whichever part of the app first needs a discipline row.

---

## 1. Project Vision & Scope

A self-hosted platform unifying Garmin biometrics, Technogym gym sessions, blood-donation lab panels, subjective journaling (including Telegram voice notes), gear maintenance, and weather/conditions data into one database. A feature engine computes Whoop/Oura/Strava/Garmin-style derived metrics without needing those subscriptions. An API-based AI layer (tiered by cost, tool-using) provides chat, scheduled reports, and adaptive guidance. A React web dashboard and a Garmin Connect IQ watch companion serve as the interfaces. Hosted on the owner's own hardware, reachable securely without port forwarding, extendable to a small group of friends, under €5/month total recurring cost (AI tokens + any other service, electricity excluded).

---

## 2. Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI (async) |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic, from commit 1 |
| Database | PostgreSQL 16 + TimescaleDB + pgvector |
| Task queue | Celery + Redis |
| Frontend | React 18 + TypeScript + Vite + Tailwind + shadcn/ui, custom design system (Section 16) |
| Charts | Recharts (default) or visx for the custom radial gauges |
| Bot | `python-telegram-bot` (async, v21+), webhook route on the FastAPI app |
| LLM (runtime) | Provider-agnostic client abstraction. Default: GLM-5.2 (powerful tier, reasoning-effort tuned), GLM-4.7-Flash (free/cheap tier), Claude Haiku 4.5 as paid fallback. See Section 9. |
| STT | OpenAI Whisper API |
| Embeddings | **OpenAI `text-embedding-3-small` (1536-dim) is the pinned default** — see Section 6.2 for why this can't be freely swapped like the LLM can |
| Weather | Open-Meteo (free, no API key) |
| Watch app | Garmin Connect IQ SDK, Monkey C |
| Reverse proxy | Caddy — serves the built frontend as static files and proxies `/api/*` to FastAPI, same origin |
| Hosting | Self-hosted, single always-on machine, Docker Compose |
| Remote access | Tailscale Funnel (free, Personal plan) |
| Auth | Invite-only multi-user accounts, server-side sessions |

---

## 3. System Architecture — Data Flow

```
Garmin Connect ──┐
Technogym ────────┤
Strava/MFP ───────┼─▶ [1] Ingestion Workers ─▶ [2] Raw Store (JSONB) ─▶ [3] Normalizer/ETL
Weather (Open-Meteo)│      (Celery beat, Section 19) (audit/replay)        (typed tables,
Manual (journal,   │                                                       idempotent upsert)
 labs, supplements,│
 gear service)  ───┘
                                                                                   │
                                                                                   ▼
                                                              [4] Feature Engine (nightly batch)
                                                                                   │
                                                                                   ▼
                                                              [5] AI Layer (RAG + tool-calling,
                                                                  tiered by cost — Section 9)
                                                                                   │
                                                        ┌──────────────────────────┴───────────────────────┐
                                                        ▼                                                    ▼
                                            [6a] FastAPI ─▶ React Dashboard                    [6b] FastAPI ─▶ Connect IQ Watch App
                                            (behind session auth, via Caddy,                       (phone-tethered sync)
                                             reachable via Tailscale Funnel)
                                                        │
                                                        ▼
                                            [6c] Telegram Bot (per-user linked chats — Section 10.2)
```

---

## 4. Repository Structure

```
/health-control-center
  /backend
    /app
      /api            # routers — see Section 18 for the resource groups
      /agent          # LLM client abstraction, tool registry, agent loop
      /queries        # shared read functions used by BOTH the agent tools and report generation (Section 8.2)
      /auth           # session handling, invite codes, password hashing, rate limiting
      /connectors
        /garmin
        /technogym
        /telegram
        /weather
      /feature_engine # pure functions + golden-dataset tests
      /gear
      /models
      /schemas
      /tasks          # Celery tasks — schedule in Section 19
      /core           # config, encryption, LLM/embedding/STT adapters, structured logging setup
    /alembic
      /versions       # includes the Section 6.1 seed-data migration
    /tests
      /golden_dataset
      /fixtures       # recorded connector payloads for integration tests (no live API calls in CI)
  /frontend
    /src
      /design-system
      /pages
      /components
      /api
    /e2e              # Playwright specs, run against the seeded demo dataset
  /connectiq
  /infra
    Caddyfile
    tailscale-funnel-setup.md
    docker-compose.yml
  .env.example
  README.md
```

---

## 5. Environment Variables

```
DATABASE_URL=
REDIS_URL=
SESSION_SECRET=
ENCRYPTION_KEY=

GARMIN_EMAIL=
GARMIN_PASSWORD=

TECHNOGYM_CLIENT_ID=
TECHNOGYM_CLIENT_SECRET=
TECHNOGYM_REDIRECT_URI=

TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
# no per-user chat ID here anymore — see Section 10.2, chats are linked in-app per user

LLM_PROVIDER_CHEAP=
LLM_PROVIDER_POWERFUL=
GLM_API_KEY=
ANTHROPIC_API_KEY=

OPENAI_API_KEY=                  # embeddings + Whisper STT

DAILY_TOKEN_BUDGET_USD=
BACKUP_ENCRYPTION_KEY=           # separate from ENCRYPTION_KEY, for backup archives (Section 19)
B2_APPLICATION_KEY_ID=
B2_APPLICATION_KEY=
```

---

## 6. Database Schema — Full DDL

### 6.1 Seed data
`disciplines` is populated via an Alembic **data migration**, not left for the application to invent values for. Seed exactly: `enduro, road_cycling, skiing, sailing, kitesurf, windsurf, tennis, wakeboard, snowboard, surf, sim_racing, running, strength, gym_general` — categories `endurance`/`technical`/`strength` assigned per the obvious mapping (skiing/snowboard/surf/sim_racing are `technical`; strength/gym_general are `strength`; the rest are `endurance`).

### 6.2 A note on the embeddings column
`embeddings.embedding` is `VECTOR(1536)`, matching OpenAI `text-embedding-3-small`. Unlike the LLM completion layer, **this is not freely provider-swappable**: different embedding models output different vector dimensions, and pgvector columns have a fixed dimension. If the embedding provider is ever changed, that requires an explicit migration (`ALTER COLUMN embedding TYPE vector(N)`) *and* re-embedding every existing row — it is not a drop-in config change like `LLM_PROVIDER_POWERFUL` is. `text-embedding-3-small` is the pinned default specifically to avoid this surprising anyone later.

### 6.3 DDL

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

-- ===================== IDENTITY, AUTH & INTEGRATIONS =====================

CREATE TABLE users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL,
    dob             DATE,
    sex             TEXT,
    height_cm       NUMERIC,
    weight_goal_direction TEXT CHECK (weight_goal_direction IN ('gain','maintain','lose')),
    timezone        TEXT NOT NULL DEFAULT 'Europe/Rome',   -- IANA tz — governs day-boundary rules, Section 17
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auth_credentials (
    user_id         BIGINT PRIMARY KEY REFERENCES users(id),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,             -- argon2
    role            TEXT NOT NULL DEFAULT 'friend' CHECK (role IN ('owner','friend')),
    ai_access_tier  TEXT NOT NULL DEFAULT 'cheap_only' CHECK (ai_access_tier IN ('cheap_only','full')),
    share_segments  BOOLEAN NOT NULL DEFAULT false,
    failed_login_count SMALLINT NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE invites (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    created_by    BIGINT NOT NULL REFERENCES users(id),
    used_by       BIGINT REFERENCES users(id),
    expires_at    TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id),
    token_hash    TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL
);

-- one row per user who has linked a Telegram chat — replaces a single hardcoded chat id,
-- which would only have worked for one person. Linking flow in Section 10.2.
CREATE TABLE telegram_links (
    user_id     BIGINT PRIMARY KEY REFERENCES users(id),
    chat_id     BIGINT NOT NULL UNIQUE,
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE integrations (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                 BIGINT NOT NULL REFERENCES users(id),
    provider                TEXT NOT NULL CHECK (provider IN ('garmin','technogym','strava','myfitnesspal','telegram')),
    status                  TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','error','revoked')),
    credentials_encrypted   BYTEA,
    consecutive_failures    SMALLINT NOT NULL DEFAULT 0,   -- drives the sync_failure alert, Section 21
    last_synced_at          TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider)
);

CREATE TABLE raw_ingest (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id),
    source        TEXT NOT NULL,
    payload_type  TEXT NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json      JSONB NOT NULL,
    processed     BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_raw_ingest_unprocessed ON raw_ingest (source, processed) WHERE NOT processed;
-- retention: keep indefinitely at this project's scale; revisit archiving only if disk pressure
-- actually becomes a problem — not a Phase 0-11 concern.

-- ===================== DISCIPLINES & GEAR =====================

CREATE TABLE disciplines (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL CHECK (category IN ('endurance','technical','strength')),
    ftp_model_type TEXT
);

CREATE TABLE gear (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                BIGINT NOT NULL REFERENCES users(id),
    name                   TEXT NOT NULL,
    gear_type              TEXT NOT NULL,
    acquired_date          DATE,
    service_interval_hours NUMERIC,
    service_interval_km    NUMERIC,
    hours_since_service    NUMERIC NOT NULL DEFAULT 0,
    km_since_service       NUMERIC NOT NULL DEFAULT 0,
    active                 BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE gear_service_logs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gear_id       BIGINT NOT NULL REFERENCES gear(id),
    service_type  TEXT NOT NULL,
    performed_at  TIMESTAMPTZ NOT NULL,
    notes         TEXT
);

CREATE TABLE discipline_gear_defaults (
    user_id       BIGINT NOT NULL REFERENCES users(id),
    discipline_id BIGINT NOT NULL REFERENCES disciplines(id),
    gear_id       BIGINT NOT NULL REFERENCES gear(id),
    PRIMARY KEY (user_id, discipline_id)
);

-- ===================== ACTIVITIES =====================

CREATE TABLE activities (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    discipline_id    BIGINT NOT NULL REFERENCES disciplines(id),
    start_time       TIMESTAMPTZ NOT NULL,
    start_tz_offset_minutes INTEGER NOT NULL,
    local_date       DATE NOT NULL,              -- derived at write time: calendar date of start_time in start_tz_offset_minutes — see Section 17
    duration_s       INTEGER NOT NULL,
    distance_m       NUMERIC,
    elevation_gain_m NUMERIC,
    avg_hr           INTEGER,
    max_hr           INTEGER,
    avg_power        NUMERIC,
    np_power         NUMERIC,
    calories         INTEGER,
    training_load    NUMERIC,
    data_completeness TEXT NOT NULL DEFAULT 'full' CHECK (data_completeness IN ('full','partial','manual')),
    weather_snapshot JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_activities_user_time ON activities (user_id, start_time);
CREATE INDEX idx_activities_user_local_date ON activities (user_id, local_date);

CREATE TABLE activity_source_links (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activity_id   BIGINT NOT NULL REFERENCES activities(id),
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    raw_ingest_id BIGINT REFERENCES raw_ingest(id),
    UNIQUE (source, external_id)
);

CREATE TABLE activity_gear_links (
    activity_id   BIGINT NOT NULL REFERENCES activities(id),
    gear_id       BIGINT NOT NULL REFERENCES gear(id),
    PRIMARY KEY (activity_id, gear_id)
);

-- NOTE ON SCALE: this table takes one row per sample (commonly 1Hz) per activity. Across years
-- of endurance activities this is the single largest table in the schema by a wide margin. It is
-- NOT a TimescaleDB hypertable because its time column (t_offset_s) is relative to each activity,
-- not an absolute timestamp — hypertable partitioning needs an absolute time/range column, so
-- partitioning here on t_offset_s would not meaningfully distribute the data. If this table's size
-- becomes a real problem in practice, the two realistic fixes are: (a) add a derived absolute
-- `sample_time` column (activities.start_time + t_offset_s) and hypertable-partition on that, or
-- (b) switch to one-row-per-activity with the stream stored as a compressed array/JSONB column.
-- Not needed at Phase 1 scale — noted here so it isn't a surprise later, not so it's built now.
CREATE TABLE activity_streams (
    activity_id  BIGINT NOT NULL REFERENCES activities(id),
    t_offset_s   INTEGER NOT NULL,
    hr           INTEGER,
    power        NUMERIC,
    cadence      NUMERIC,
    speed        NUMERIC,
    altitude     NUMERIC,
    lat          NUMERIC,
    lon          NUMERIC,
    PRIMARY KEY (activity_id, t_offset_s)
);

CREATE TABLE segments (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    discipline_id BIGINT NOT NULL REFERENCES disciplines(id),
    name          TEXT NOT NULL,
    geo_polyline  TEXT
);

CREATE TABLE segment_efforts (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    segment_id     BIGINT NOT NULL REFERENCES segments(id),
    activity_id    BIGINT NOT NULL REFERENCES activities(id),
    elapsed_time_s INTEGER NOT NULL,
    rank           INTEGER,
    is_pr          BOOLEAN NOT NULL DEFAULT false
);

-- ===================== SLEEP & RECOVERY SIGNALS =====================
-- Hypertable criterion used throughout this schema: a table becomes a TimescaleDB hypertable
-- only when it has genuinely sub-daily-frequency inserts on an absolute timestamp column
-- (sleep/HRV/stress readings). Daily-grain tables (daily_features, daily_biometrics, rollups)
-- use a plain (user_id, date) primary key instead — hypertable partitioning would add overhead
-- with no benefit at one row per user per day.

CREATE TABLE sleep_sessions (
    id               BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    local_date       DATE NOT NULL,          -- calendar date of end_time (wake-up) in the user's timezone — Section 17
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ NOT NULL,
    total_sleep_s    INTEGER,
    deep_s           INTEGER,
    light_s          INTEGER,
    rem_s            INTEGER,
    awake_s          INTEGER,
    sleep_score      NUMERIC,
    respiration_avg  NUMERIC,
    spo2_avg         NUMERIC,
    restlessness     NUMERIC,
    PRIMARY KEY (id, start_time)
);
SELECT create_hypertable('sleep_sessions', 'start_time');

CREATE TABLE hrv_readings (
    id               BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    "timestamp"      TIMESTAMPTZ NOT NULL,
    hrv_ms           NUMERIC NOT NULL,
    reading_type     TEXT NOT NULL CHECK (reading_type IN ('overnight_avg','5min')),
    rolling_baseline_ms NUMERIC,
    PRIMARY KEY (id, "timestamp")
);
SELECT create_hypertable('hrv_readings', 'timestamp');

CREATE TABLE stress_readings (
    id           BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    "timestamp"  TIMESTAMPTZ NOT NULL,
    stress_level NUMERIC,
    body_battery NUMERIC,
    PRIMARY KEY (id, "timestamp")
);
SELECT create_hypertable('stress_readings', 'timestamp');

CREATE TABLE daily_biometrics (
    user_id       BIGINT NOT NULL REFERENCES users(id),
    date          DATE NOT NULL,          -- user's local date, not UTC date — Section 17
    resting_hr    INTEGER,
    weight_kg     NUMERIC,
    body_fat_pct  NUMERIC,
    vo2max        NUMERIC,
    steps         INTEGER,
    floors        INTEGER,
    spo2_avg      NUMERIC,
    hydration_ml  INTEGER,
    PRIMARY KEY (user_id, date)
);

-- ===================== MEDICAL / LAB =====================

CREATE TABLE lab_panels (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id),
    date              DATE NOT NULL,
    panel_type        TEXT NOT NULL,
    donation_type     TEXT CHECK (donation_type IN ('whole_blood','plasma','platelets')),
    hemoglobin_g_dl   NUMERIC,
    hematocrit_pct    NUMERIC,
    ferritin_ng_ml    NUMERIC,
    iron              NUMERIC,
    wbc               NUMERIC,
    plt               NUMERIC,
    next_eligible_date DATE,
    source            TEXT,
    notes             TEXT,
    -- encrypted at the application layer (ENCRYPTION_KEY) before it hits disk
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE lab_metrics (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lab_panel_id  BIGINT NOT NULL REFERENCES lab_panels(id),
    metric_name   TEXT NOT NULL,
    value         NUMERIC NOT NULL,
    unit          TEXT,
    ref_low       NUMERIC,
    ref_high      NUMERIC
);

-- ===================== SUBJECTIVE / LIFESTYLE =====================

CREATE TABLE journal_entries (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                   BIGINT NOT NULL REFERENCES users(id),
    date                      DATE NOT NULL,      -- user's local date — Section 17
    mood_score                NUMERIC,
    energy_score              NUMERIC,
    motivation_score          NUMERIC,
    soreness_score            NUMERIC,
    stress_subjective         NUMERIC,
    sleep_quality_subjective  NUMERIC,
    free_text_notes           TEXT,
    tags                      TEXT[],
    source                    TEXT NOT NULL DEFAULT 'web' CHECK (source IN ('web','telegram_voice','telegram_text')),
    raw_transcript            TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE nutrition_logs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id),
    "timestamp"   TIMESTAMPTZ NOT NULL,
    source        TEXT,
    calories      INTEGER,
    protein_g     NUMERIC,
    carbs_g       NUMERIC,
    fat_g         NUMERIC,
    water_ml      INTEGER,
    alcohol_units NUMERIC,
    caffeine_mg   NUMERIC
);

CREATE TABLE supplement_protocols (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    supplement_name TEXT NOT NULL,
    dose            TEXT,
    schedule_cron   TEXT,
    active          BOOLEAN NOT NULL DEFAULT true,
    start_date      DATE,
    end_date        DATE,
    reason          TEXT
);

CREATE TABLE supplement_logs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    protocol_id   BIGINT NOT NULL REFERENCES supplement_protocols(id),
    taken_at      TIMESTAMPTZ NOT NULL,
    adherence     BOOLEAN NOT NULL
);

-- ===================== FEATURE ENGINE OUTPUT =====================

CREATE TABLE feature_weights (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature_name   TEXT NOT NULL,
    component_name TEXT NOT NULL,
    weight         NUMERIC NOT NULL,
    version        INTEGER NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- SELECTION RULE (there was previously no stated rule for this — now explicit):
-- for a given (feature_name, component_name) and a computation date D, the feature engine uses
-- the row with the latest effective_from that is <= D. This makes historical daily_features
-- reproducible using the weights that were actually active on that date, not today's weights.
-- Changing feature_weights going forward does NOT retroactively rewrite past daily_features rows
-- — those are computed once, at nightly batch time, and stand as the historical record. If a
-- weight was wrong and needs correcting, fix the feature_weights row, then manually re-run the
-- nightly feature-engine task for the affected date range — it upserts daily_features by
-- (user_id, date), so this is a safe, idempotent backfill.

CREATE TABLE daily_features (
    user_id                        BIGINT NOT NULL REFERENCES users(id),
    date                           DATE NOT NULL,      -- user's local date — Section 17
    recovery_score                 NUMERIC,
    strain_score                   NUMERIC,
    readiness_score                NUMERIC,
    training_load_acute            NUMERIC,
    training_load_chronic          NUMERIC,
    acwr                           NUMERIC,
    sleep_architecture_score       NUMERIC,
    hrv_deviation_from_baseline    NUMERIC,
    illness_risk_score             NUMERIC,
    injury_risk_score              NUMERIC,
    iron_status_flag               TEXT,
    cross_discipline_fatigue_index NUMERIC,
    data_completeness              TEXT NOT NULL DEFAULT 'full' CHECK (data_completeness IN ('full','partial')),
    PRIMARY KEY (user_id, date)
);

CREATE TABLE discipline_features (
    user_id                BIGINT NOT NULL REFERENCES users(id),
    discipline_id          BIGINT NOT NULL REFERENCES disciplines(id),
    date                   DATE NOT NULL,
    estimated_ftp          NUMERIC,
    aerobic_decoupling_pct NUMERIC,
    efficiency_factor      NUMERIC,
    PRIMARY KEY (user_id, discipline_id, date)
);

CREATE TABLE weekly_rollups (
    user_id      BIGINT NOT NULL REFERENCES users(id),
    week_start   DATE NOT NULL,
    metric_name  TEXT NOT NULL,
    mean_value   NUMERIC,
    min_value    NUMERIC,
    max_value    NUMERIC,
    trend_slope  NUMERIC,
    PRIMARY KEY (user_id, week_start, metric_name)
);

CREATE TABLE monthly_rollups (
    user_id      BIGINT NOT NULL REFERENCES users(id),
    month_start  DATE NOT NULL,
    metric_name  TEXT NOT NULL,
    mean_value   NUMERIC,
    min_value    NUMERIC,
    max_value    NUMERIC,
    trend_slope  NUMERIC,
    PRIMARY KEY (user_id, month_start, metric_name)
);

-- ===================== TRAINING PLANS =====================

CREATE TABLE training_plans (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id),
    discipline_id       BIGINT REFERENCES disciplines(id),
    created_by          TEXT NOT NULL CHECK (created_by IN ('ai','manual')),
    week_start          DATE NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed','active','completed')),
    source_ai_report_id BIGINT,     -- FK added below, after ai_reports exists
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE planned_sessions (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    training_plan_id      BIGINT NOT NULL REFERENCES training_plans(id),
    date                  DATE NOT NULL,
    discipline_id         BIGINT REFERENCES disciplines(id),
    session_type          TEXT,
    target_duration_min   INTEGER,
    target_load           NUMERIC,
    description           TEXT,
    technogym_program_id  TEXT
);

CREATE TABLE technogym_sync_log (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id              BIGINT NOT NULL REFERENCES users(id),
    training_plan_id     BIGINT REFERENCES training_plans(id),
    sync_direction       TEXT NOT NULL CHECK (sync_direction IN ('push','pull')),
    status               TEXT NOT NULL,
    synced_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    external_program_id  TEXT,
    raw_response         JSONB
);

-- ===================== AI LAYER =====================

CREATE TABLE ai_reports (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id),
    report_type         TEXT NOT NULL CHECK (report_type IN ('daily','weekly','monthly')),
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_md          TEXT NOT NULL,
    model_used          TEXT,               -- NULL for templated (non-LLM) daily summaries
    source_feature_ids  TEXT[]              -- audit list of metric-name/date identifiers referenced —
                                             -- NOT a foreign key (daily_features has a composite key, not a single id)
);

-- now that ai_reports exists, wire up the FK left open above:
ALTER TABLE training_plans
    ADD CONSTRAINT fk_training_plans_source_report
    FOREIGN KEY (source_ai_report_id) REFERENCES ai_reports(id);

CREATE TABLE ai_chat_sessions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()
    -- SESSION BOUNDARY RULE: a new row is created when a user opens the Chat page after more
    -- than 30 minutes since last_activity_at; otherwise messages append to the existing session.
);

CREATE TABLE ai_chat_messages (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES ai_chat_sessions(id),
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
    content         TEXT NOT NULL,
    model_tier      TEXT CHECK (model_tier IN ('free','cheap','powerful')),
    referenced_data JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_tool_calls (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  BIGINT REFERENCES ai_chat_sessions(id),   -- nullable: also used by non-chat callers, e.g.
                                                            -- scheduled report generation reusing the same
                                                            -- query functions (Section 8.2) — NULL means
                                                            -- "not a chat-originated call"
    tool_name   TEXT NOT NULL,
    input_json  JSONB NOT NULL,
    output_json JSONB,
    error       TEXT,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE embeddings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_table    TEXT NOT NULL,
    source_id       BIGINT NOT NULL,
    embedding       VECTOR(1536),      -- pinned to text-embedding-3-small — see Section 6.2
    content_snippet TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE token_usage (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            BIGINT REFERENCES users(id),
    call_type          TEXT NOT NULL,
    tier               TEXT NOT NULL CHECK (tier IN ('free','cheap','powerful')),
    model              TEXT NOT NULL,
    tokens_in          INTEGER,
    tokens_out         INTEGER,
    cached_tokens      INTEGER,
    cost_estimate_usd  NUMERIC,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===================== WATCH, BOT & ALERTS =====================

CREATE TABLE watch_sync_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    device_id       TEXT,
    sync_type       TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_summary JSONB
);

CREATE TABLE telegram_messages (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id                  BIGINT NOT NULL,
    message_id               BIGINT NOT NULL,
    voice_file_id            TEXT,
    raw_transcript            TEXT,
    extracted_json            JSONB,
    status                   TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','rejected')),
    linked_journal_entry_id  BIGINT REFERENCES journal_entries(id),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    type         TEXT NOT NULL,     -- 'low_ferritin' | 'high_acwr' | 'poor_sleep_streak' | 'donation_eligible' |
                                     -- 'gear_service_due' | 'sync_failure' | 'budget_warning' | ...
    severity     TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    message      TEXT NOT NULL
);

-- ===================== WEATHER =====================

CREATE TABLE forecast_cache (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lat         NUMERIC NOT NULL,
    lon         NUMERIC NOT NULL,
    date        DATE NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload     JSONB NOT NULL,
    UNIQUE (lat, lon, date)
);
```

---

## 7. Feature Engine — Derived Metrics

- **Recovery Score** — HRV deviation from rolling personal baseline, resting-HR deviation, sleep quality/duration, prior day's strain. 0–100.
- **Strain Score** — cumulative daily cardiovascular load from HR-zone time (TRIMP-style), normalized against a personal ceiling.
- **Readiness Score** — blends recovery, sleep architecture, and ACWR. The Cockpit's signature gauge.
- **Sleep Architecture Score** — REM%, deep%, efficiency, latency, circadian regularity vs. personal baseline.
- **ACWR** — 7-day rolling load ÷ 28-day rolling load, one load metric for both windows, never mixed.
- **Aerobic Decoupling** — first half vs. second half of steady-state effort, arrays aligned by time offset, not sample count.
- **Illness Risk Score** — HRV drop + resting-HR elevation + elevated respiration + journal soreness/fatigue, weights from `feature_weights` (selection rule: Section 6.3 comment).
- **FTP/Threshold Estimation** — validated protocol/model only.
- **Cross-Discipline Fatigue Index** — load aggregated across active disciplines with discipline-specific decay.
- **Iron/Hematological Recovery Index** — ferritin/hemoglobin depletion + recovery curve post-donation.
- **Gear Wear** — cumulative hours/km since last service vs. configured interval (Section 13).

---

## 8. Agent Harness

### 8.1 LLM client abstraction
One interface (`app/core/llm.py`): `complete(messages, tools, system, cache_blocks, tier) -> Response`, implemented once per provider. Nothing else touches a provider SDK directly.

### 8.2 Shared query layer
Every tool in Section 8.3 is a thin wrapper over a function in `app/queries/` — the **same** functions the scheduled report-generation tasks (Section 19) call directly, without going through the LLM agent loop. This avoids two parallel implementations of "get my ACWR trend" ever drifting apart. `agent_tool_calls.session_id` is nullable specifically because report generation logs its calls there too, tagged with a NULL session.

### 8.3 Tool registry

| Tool | Type | Inputs | Behavior |
|---|---|---|---|
| `get_metric_trend` | read | metric, start_date, end_date, discipline_id? | `daily_features`/`discipline_features`, compact table output |
| `get_lab_trend` | read | marker, start_date, end_date | `lab_panels`/`lab_metrics` |
| `get_activity_summary` | read | start_date, end_date, discipline_id? | aggregates from `activities` |
| `get_journal_entries` | read | start_date, end_date, tags? | `journal_entries` |
| `search_context` | read | query, top_k=5 | pgvector cosine search over `embeddings` |
| `get_training_plan` | read | status? | current/active plan + `planned_sessions` |
| `get_donation_status` | read | — | next eligible date, days since last donation, iron flag |
| `get_gear_status` | read | gear_id? | usage vs. interval per gear item |
| `propose_training_plan` | write, **confirmation required** | week_start, sessions[] | creates `training_plans` (draft) + `planned_sessions` |
| `propose_supplement_change` | write, **confirmation required** | protocol changes | drafts, does not apply |
| `sync_plan_to_technogym` | write, **confirmation required**, only on a `confirmed` plan | training_plan_id | Section 11 |

### 8.4 Agent loop
1. Build the request: cached system block (profile, baselines, feature weights) + recent-detail window (7–14 days) + tool definitions.
2. Send to the tier selected by Section 9's routing rule.
3. Tool calls: execute via `app/queries/`, log to `agent_tool_calls`, loop (max 8 iterations, return best partial answer if not converged).
4. Final response: write `ai_chat_messages.referenced_data` and `model_tier`.
5. Tool errors return as tool results, not exceptions that kill the loop.

### 8.5 Write-tool confirmation flow
`propose_*` tools write a `draft`/`pending` row and return it — never commit directly. A confirm action (dashboard or Telegram button) flips status to `confirmed`. Only a `confirmed` plan can sync to Technogym.

### 8.6 Cost governance
Every LLM/embedding call writes to `token_usage` (with user and tier). A daily task sums the day's cost; crossing `DAILY_TOKEN_BUDGET_USD` fires a `budget_warning` alert — informational, not a hard stop.

---

## 9. AI Model Routing & Cost Engineering

### 9.1 Tiers
| Tier | Used for | Default | Rate (per 1M tokens, in/out) |
|---|---|---|---|
| Free | Transcript structuring, routine classification, the router itself | GLM-4.7-Flash | $0 |
| Cheap | Simple chat lookups, fallback if free tier is rate-limited | Claude Haiku 4.5 | $1 / $5 |
| Powerful | Weekly/monthly reports, plan generation, strategic chat | GLM-5.2, high/xhigh reasoning effort | $1.40 / $4.40 (cached $0.26) |

### 9.2 Routing logic, fully specified
1. Check `auth_credentials.ai_access_tier` for the requesting user. If `cheap_only`, the request is capped at free/cheap **regardless** of what step 2 decides — powerful tier is simply unreachable for that account. This is the per-friend cost control valve.
2. If the account is `full`: a free-tier classification call tags the message `lookup` (→ free/cheap) or `strategic` (→ powerful).
3. Scheduled generation is hardcoded, not classified: daily summaries are templated (no LLM call); weekly/monthly reports are always powerful tier, via the batch API where the provider supports it.

### 9.3 Realistic monthly cost
| Item | Assumptions | Est. cost |
|---|---|---|
| Daily summaries | templated | $0.00 |
| Weekly reports (×4) | ~6k in / 1.5k out, powerful | ~$0.06 |
| Monthly deep-dive (×1) | ~15k in / 3k out, powerful | ~$0.03 |
| Voice extraction (~30) | free tier | ~$0.00–0.05 |
| Whisper STT (~60 min) | $0.006/min | ~$0.36 |
| Chat lookups (~135) | free/cheap | ~$0.00–0.40 |
| Chat strategic (~15) | powerful | ~$0.12 |
| Embeddings | small volume | ~$0.05 |
| Infra (Tailscale, backups, no domain) | | $0.00 |
| **Total** | | **≈ $0.60–1.05/month (≈ €0.55–1.00)** |

Margin under the €5 target is large enough to absorb a few friend accounts at `cheap_only` default. `token_usage` + the budget alert (suggest a threshold around €3-equivalent) is the actual safety net, not this estimate.

---

## 10. Telegram Bot Integration

### 10.1 Voice/text flow
1. Voice message → webhook ACKs immediately, hands off to Celery.
2. Worker downloads the `.ogg`, sends to Whisper.
3. Transcript → free/cheap tier, structured extraction (discipline, mood/energy/soreness if mentioned, summary, tags; gear mentions override `discipline_gear_defaults`).
4. Bot replies with the draft + inline buttons (✅ Save / ✏️ Edit) — **never auto-commits.**
5. On confirm: written to `journal_entries`, linked to an existing activity if the timestamp falls in its window.

### 10.2 Per-user linking (multi-user fix)
A single hardcoded allowed chat ID only works for one person, which contradicts the multi-user goal. Instead: Settings generates a one-time link code for the logged-in user; the user sends `/link <code>` to the bot; the bot writes `telegram_links(user_id, chat_id)`. Every inbound message is resolved to a user via `telegram_links.chat_id` — an unlinked chat gets a "link your account first" reply and nothing else, no data is written on its behalf.

**Also supports:** text messages, `/status`, `/donate`, `/report`, `/gear`. Alerts push to the linked user's chat as they trigger.

**Security:** verify Telegram's webhook `secret_token` header on every request; an unresolvable `chat_id` is simply unauthenticated, not a special case to bypass.

---

## 11. Technogym Integration

**Available today:** an enduser-to-enduser OAuth scenario (`developer.technogym.com` / `apidocs.mywellness.com`) with an official Python sample demonstrating auth + FIT/TCX activity upload — solidly achievable via self-serve registration. Pushing a plan as a **prescribed program on equipment** is documented under the Technogym Enterprise API, which reads as partner/facility-tier — uncertain for an individual account until actually registered and checked.

**Two stages:**
- **11a (build regardless):** OAuth, pull completed sessions into `raw_ingest` → `activities`, optional FIT/TCX upload of sessions logged elsewhere.
- **11b (contingent):** `sync_plan_to_technogym` once the real access tier is confirmed. Fallback if prescription-push isn't available: the plan reaches the user via `/plan today` in Telegram, followed manually.

---

## 12. Multi-Source Activity Reconciliation

1. On ingesting an activity, check for an existing row for the same user with `start_time` within ±10 minutes and a compatible discipline.
2. If found: no new `activities` row — add an `activity_source_links` entry, merge fields preferring the richer source per field (Garmin for HR/GPS, Technogym for machine power/resistance/incline), never overwrite a populated field with NULL.
3. If not found: create the row plus its first `activity_source_links` entry.

---

## 13. Gear Tracking

Auto-link via `discipline_gear_defaults` at ingestion (Telegram voice can override). Nightly job sums `duration_s`/`distance_m` since the last `gear_service_logs.performed_at` into `hours_since_service`/`km_since_service`. Crossing the configured interval fires `gear_service_due`, pushed to Telegram. Logging a new service resets the counters. This job is idempotent — re-running it must not double-count (Section 17).

---

## 14. Weather & Sport Dashboard

Open-Meteo (free, no key). `activities.weather_snapshot` populated at ingestion from the activity's start lat/lon and time. `forecast_cache` refreshed on a schedule (Section 19), read by the Sport Dashboard's "good window" flags per discipline. Combined with segments/ACWR/route heatmaps, this is the Strava-Premium/Garmin-subscription replacement — no ongoing subscription needed. Worth building once live: cross-reference a good forecast window with a high readiness score for a proactive Telegram nudge.

---

## 15. Multi-User & Secure Remote Access

**Auth:** invite-only (`invites`), argon2-hashed credentials, server-side sessions via cookies that are `Secure`, `HttpOnly`, `SameSite=Lax` (Section 22 has the full security posture). Every query is scoped to the session's `user_id` at the API layer — never a client-supplied id. Friends' data is private by default; the only shared surface is `segment_efforts`, opt-in via `share_segments`. Each user (owner and friends alike) connects their **own** Garmin/Technogym/Telegram integrations independently — this is full per-user data isolation, not shared viewing of the owner's data.

**Remote access:** Tailscale Funnel, free on the Personal plan, no port forwarding, automatic TLS, visitors need neither a Tailscale account nor the app installed. Caddy serves the built frontend as static files and reverse-proxies `/api/*` to FastAPI from the same origin (this is also why CORS isn't a concern by default — see Section 22). Funnel points at Caddy's local port. Resulting URL: `https://<name>.<tailnet>.ts.net`, free. A custom domain via Cloudflare Tunnel is a possible later upgrade, not required.

---

## 16. Web UI — Design System & Page Specification

### 16.1 Direction
An instrument panel for someone who trains by telemetry. Reference world: motorsport telemetry software (MoTeC i2), aviation glass cockpits (Garmin G1000), dive computers, rally roadbooks — not Whoop/Oura's soft rounded cards, not a generic SaaS dashboard.

### 16.2 Token System
| Token | Hex | Use |
|---|---|---|
| `bg-base` | `#12141A` | app background |
| `bg-panel` | `#1B1E26` | panel surface |
| `accent-amber` | `#E8A33D` | primary readout, primary CTA, signature gauge needle |
| `accent-cyan` | `#4FD1C5` | secondary data channel — never mixed with amber on the same reading |
| `accent-red` | `#E5484D` | alerts only, never decorative |
| `text-primary` | `#EDEAE3` | warm off-white |
| `text-muted` | `#6B7280` | hairlines, secondary labels, units |

Type: JetBrains Mono / IBM Plex Mono for every big number; Archivo (condensed grotesk, not Inter) for UI/body; the mono face again, small/uppercase/wide-tracked, for unit captions.

Layout: flush hairline-divided panels, zero-to-minimal radius, no drop shadows, dense desktop grid collapsing to stacked gauges on mobile.

Signature element: an animated radial gauge (arc, red/amber/green zones, needle sweep) for Readiness on Cockpit — every other gauge is a quieter variant of the same component.

### 16.3 Pages
Every page implements loading / empty / error / populated states — not optional.

| Page | Purpose | Key components |
|---|---|---|
| Login | Auth entry | email+password, invite-only note |
| Cockpit | Today at a glance | signature Readiness gauge, Recovery/Strain/Sleep gauges, alerts strip, ACWR sparkline, donation countdown, weather strip |
| Trends/Explorer | Deep analysis | metric/discipline/range pickers, daily detail near-term, rollups further back |
| Activities | History + detail | list, per-activity detail with stream chart, decoupling, linked gear/weather |
| Labs & Donation | Panel history | timeline, ferritin/hemoglobin trend, countdown, iron recovery index |
| Journal | Subjective log | calendar heatmap, entry detail with source badge + expandable transcript |
| Training Plan | Plans | planned vs actual, draft/confirmed/active clearly distinct, Technogym sync status |
| Gear | Maintenance | wear gauges (same visual language), service log, log-a-service action |
| Sport Dashboard | Conditions | 7-day forecast with good-window flags, personal route heatmap |
| Chat | Assistant | conversation UI, tool-call chips, model-tier indicator |
| Settings | Admin | integration status, invite-friend (owner), per-user AI tier (owner), Telegram link code |

### 16.4 Quality floor
Responsive, visible focus states, reduced-motion respected on gauges. Every page ships against a seeded demo dataset covering a zero-data account, a partial-data day, an extreme outlier, and a long free-text entry.

---

## 17. Non-Negotiable Engineering Constraints

- Every timestamp is `timestamptz`, stored UTC; converted to local only at presentation. `activities` also stores `start_tz_offset_minutes`.
- **Day-boundary rule (previously unstated, now explicit):** every `date`/`local_date` column (`activities.local_date`, `sleep_sessions.local_date`, `daily_features.date`, `daily_biometrics.date`, `journal_entries.date`) is derived using `users.timezone`, not UTC. A sleep session's date is the calendar date of its **end_time** (wake-up) in local time; an activity's date is the calendar date of its local **start_time**. This prevents a late-night or pre-dawn session from being silently miscategorized by a UTC day boundary that doesn't match the user's actual day.
- Efficiency-factor and decoupling math is always scoped by `discipline_id`, never pooled.
- ACWR uses exactly one load metric for both windows.
- FTP estimation uses a validated protocol/model only.
- Feature weights live in `feature_weights`, versioned, selected by the rule in Section 6.3 — never hardcoded constants.
- Every external source (Garmin, Technogym, weather) writes to `raw_ingest` before normalization.
- All sync/ingest operations are idempotent upserts, keyed on `(source, external_id)`.
- Days with incomplete sensor data are flagged (`data_completeness`), never silently scored as complete.
- `lab_panels` is encrypted at the application layer before it touches disk.
- Write-tools never commit directly — draft, then explicit confirm.
- No route is reachable without a valid session except `/telegram/webhook` (secret-token verified), `/auth/login`, and `/health`.
- Gear/weather/rollup accumulation jobs are idempotent — re-running must not double-count.
- `disciplines` seed data comes from the Alembic migration in Section 6.1, never invented ad hoc.

---

## 18. API Surface

| Resource | Base path | Notes |
|---|---|---|
| Auth | `/auth/login`, `/auth/logout`, `/auth/invite/redeem` | session cookie set on login |
| Activities | `/activities`, `/activities/{id}` | |
| Metrics | `/metrics/trend`, `/metrics/rollup` | powers Trends/Explorer |
| Labs | `/labs`, `/labs/{id}` | |
| Journal | `/journal`, `/journal/{id}` | |
| Training Plans | `/training-plans`, `/training-plans/{id}/confirm` | confirm flips draft → confirmed |
| Gear | `/gear`, `/gear/{id}/service` | |
| Sport Dashboard | `/weather/forecast` | |
| Chat | `/chat/sessions`, `/chat/sessions/{id}/message` | |
| Alerts | `/alerts`, `/alerts/{id}/ack` | |
| Settings | `/settings/integrations`, `/settings/invites`, `/settings/users/{id}/ai-tier`, `/settings/telegram/link-code` | owner-only endpoints enforced server-side by `role` |
| Telegram | `/telegram/webhook` | public, secret-token verified, not session-authenticated |
| Health | `/health` | public liveness check — DB + Redis connectivity |

---

## 19. Scheduled Jobs (Celery beat)

| Job | Cadence | Notes |
|---|---|---|
| Garmin sync | every 6 hours | not real-time — an unofficial client polled continuously raises ban risk |
| Technogym sync | every 6 hours | same reasoning |
| Forecast refresh | every 6 hours | upserts `forecast_cache` for each active user's usual locations |
| Nightly feature engine | 1×/day, 03:00 user-local | computes `daily_features`/`discipline_features` for the prior local day |
| Gear accumulation | 1×/day, right after feature engine | usage-since-service sums, `gear_service_due` alerts |
| Weekly rollups | Monday 03:30 | |
| Monthly rollups | 1st of month, 04:00 | |
| Weekly AI report | Monday 06:00, batch API | |
| Monthly AI report | 1st of month, 06:00, batch API | |
| Daily budget check | 1×/day | compares `token_usage` sum to `DAILY_TOKEN_BUDGET_USD` |
| Database backup | nightly, 02:00 | Section 22.5 |
| Sync-failure escalation | after every sync task attempt | 3 consecutive failures on an `integrations` row → `sync_failure` alert |

---

## 20. Testing Strategy

- **Backend:** pytest. Unit tests per module; the feature engine specifically runs the golden-dataset regression (Section 7) as a required check, not optional. Connector tests run against recorded fixture payloads in `/tests/fixtures` — no live third-party API calls in CI.
- **Frontend:** Vitest for components; Playwright e2e specs run against the seeded demo dataset, exercising all four states (Section 16.4) for every page.
- **CI:** a GitHub Actions workflow runs backend pytest and frontend Vitest/Playwright on every push. The golden-dataset regression failing blocks merge.

---

## 21. Observability & Error Handling

- Structured JSON logging (Python `logging` + JSON formatter) to stdout, captured by Docker's logging driver with rotation (`max-size`/`max-file` in `docker-compose.yml`).
- `alerts` (DB-backed, user-facing, pushed to Telegram) and application logs (developer-facing, for debugging) are distinct — don't conflate them.
- Every connector sync task catches exceptions and increments `integrations.consecutive_failures`; three in a row fires a `sync_failure` alert instead of failing silently forever.
- `/health` checks DB and Redis connectivity — enough for an external cron-based uptime check at this scale; no need for a heavier monitoring stack.

---

## 22. Security Hardening

1. **Login rate limiting:** 5 failed attempts per email per 15 minutes → temporary lockout (`auth_credentials.failed_login_count`/`locked_until`, backed by Redis for the sliding window).
2. **Session cookies:** `Secure`, `HttpOnly`, `SameSite=Lax`, short-lived with sliding expiry on activity.
3. **CSRF:** `SameSite=Lax` covers most navigation-based CSRF; state-changing requests additionally require a custom header that cross-origin requests can't attach.
4. **CORS:** not needed in the default deployment — Caddy serves frontend and API from the same origin. If the frontend is ever split to a different origin, CORS must then be explicitly and narrowly configured, never left permissive.
5. **Secrets:** `.env`, gitignored, restrictive file permissions on the host; never logged, never echoed in API error responses.
6. **Input validation:** Pydantic schemas at every API boundary; all DB access through the ORM's parameterized queries — no raw string-interpolated SQL anywhere.
7. **Backups:** nightly `pg_dump`, encrypted with `BACKUP_ENCRYPTION_KEY`, uploaded to Backblaze B2's free tier (10GB is ample at this scale). Retain the last 14 daily archives plus the last 6 monthly archives; prune older ones on the same schedule. Test a restore at least once after Phase 0 — an untested backup is a hope, not a backup.

---

## 23. Phase-by-Phase Build Plan

| Phase | Focus | Acceptance criteria |
|---|---|---|
| 0 | Repo scaffold, Docker Compose, Alembic migration + seed data (Section 6.1), FastAPI skeleton with `/health`, Celery+Redis, session auth (owner account + login), baseline security middleware (rate limiting, cookie flags) | `docker compose up` brings up all services; `/health` returns 200; owner login works; every table in Section 6 exists with seed data loaded |
| 1 | Garmin connector: auth, raw ingestion, normalizer, idempotent upsert, 6-hourly scheduled sync | sync populates normalized tables; running it twice does not duplicate rows |
| 2 | Feature engine + golden-dataset regression tests, `feature_weights` seeded | tests pass; nightly task populates `daily_features`/`discipline_features` correctly, respecting the day-boundary rule (Section 17) |
| 3 | Telegram bot: webhook, `/link` flow (Section 10.2), voice/text handlers, confirm/edit, commands, alert push | a linked chat's voice note produces a confirmable draft; an unlinked chat is told to link first |
| 4 | Medical/lifestyle module + Gear tracking | low-ferritin entry fires an alert; a synthetic 15h-since-service gear item fires `gear_service_due` |
| 5 | Agent harness + AI layer: tools, loop, routing (Section 9.2), `token_usage`, templated summaries, batch reports, chat endpoint | a ≥2-tool-call chat query answers correctly and logs to `agent_tool_calls`; a `cheap_only` account never reaches the powerful tier even on a strategic question |
| 6 | Technogym connector — Stage 11a always, 11b if access confirms | OAuth completes; reconciliation (Section 12) prevents a duplicate against a same-window Garmin entry |
| 7 | Weather & Sport Dashboard | `weather_snapshot` populated on ingestion; forecast cache refreshes on schedule, not per page load |
| 8 | Web UI build-out: every page in Section 16.3, all four states, against the demo dataset | every page passes the Section 16.4 quality floor |
| 9 | Multi-user & remote access: invite flow, friend accounts, Tailscale Funnel | a friend redeems an invite, logs in over the Funnel URL, sees only their own data |
| 10 | Connect IQ watch app | glance shows today's readiness/recovery/strain |
| 11 | Testing/observability/security hardening pass (Sections 20–22) if not already fully in place, backup restore drill, remaining connectors | a restore-from-backup has been actually tested once |

---

## 24. Open Items — Need a Human Decision

- **Technogym access tier**: only resolves by registering at `developer.technogym.com` and checking what's actually granted, before Phase 6's Stage 11b.
- **Data export/portability endpoint**: not specced — reasonable to add post-launch, not launch-blocking, but worth a `/export/me` endpoint eventually given this holds personal medical data.

Backups, which were open in the prior draft, are resolved in Section 22.7 with a concrete default — not left open going into production.

---

## 25. Readiness Verdict

Ready, with this revision. The audit that produced this version found and fixed five real correctness gaps that would have caused actual bugs (a Telegram design that only worked for one person despite multi-user being a stated goal; an embeddings column whose dimension would silently break if the "swappable" embedding provider were ever swapped; no timezone/day-boundary rule despite several tables keying on "date"; a dangling foreign key; an unstated feature-weights selection rule) and closed nine production-readiness gaps that were genuinely missing (scheduled-job cadence, testing strategy, observability, and — given this is going out to a real reachable URL — login rate limiting, cookie security, CSRF, CORS posture, secrets handling, and a concrete backup policy). What's left in Section 24 isn't a blocker; it resolves by registering for Technogym access and seeing what comes back. Start at Phase 0.
