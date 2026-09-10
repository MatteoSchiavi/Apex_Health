Personal Health & Performance Control Center — MASTER SPECIFICATION (Restart Revision)
This is the single source of truth. It supersedes every earlier document, including the first MASTER_SPEC.md that the first build attempt worked from. This revision exists because that attempt was restarted — not primarily because the spec was wrong, but because the execution environment (an ephemeral sandbox with no Docker, no root, and at least one full reprovision that wiped local git history) proved unreliable. Sections 0 and 16 exist specifically to prevent that class of failure from costing real work again. This revision also suspends the web dashboard from this build round (the owner wants to explore more design direction before it's built) and adds rationale — the "why," not just the "what" — behind the decisions that most need it for an agent to extend correctly.
---
0. Instructions to the Building Agent
Read this section first, every session, even a resumed one.
Verify state before doing anything. At the start of every session — and always after any restart — run `git log --oneline -10`, `git status`, `git remote -v`, and confirm whether a database/migration state already exists. Never assume prior work survived because you remember doing it. Confirm it on disk and in git, every single time.
Commit and push after every acceptance criterion you demonstrate — not just at the end of a phase. A crash should cost minutes, not a rebuilt phase. If no git remote is configured, stop and ask for one before writing any code — do not proceed on local-only commits.
One phase at a time. Finish it, demonstrate its acceptance criteria live, commit, push, then stop and wait for explicit confirmation before starting the next phase. Do not bundle a recovery/rebuild with the next phase's work in the same unconfirmed batch.
The web dashboard (Appendix A) is out of scope for this build round. Do not build it, do not scaffold its frontend beyond what Section 4 lists as present. If a phase's original acceptance criteria assumed a UI, this document has already adjusted them — follow the adjusted version, not your own workaround.
Automated tests and phase demonstrations use recorded fixtures only — for Garmin, Technogym, or any third-party account. Connecting a real account and running a live first-sync is a manual step performed by the human, once you've declared the fixture-based implementation complete. Do not attempt repeated live authentication against a real account while debugging — an unofficial API responding to retries from a buggy loop is exactly how an account gets rate-limited or locked, and that's not a reversible mistake.
You are the implementation layer, not the architecture layer. The decisions in this file are final unless a section explicitly says otherwise (Section 24's open items, or a place marked "your judgment call, document it"). If something is ambiguous or seems to contradict itself, stop and ask rather than silently resolving it or re-deciding it your own way.
Section 17's constraints are hard requirements, not style preferences — they exist because earlier versions of this project shipped subtle bugs from violating exactly these rules, and the schema-level fixes in Section 6 exist because a full audit already caught five real correctness gaps in an earlier draft.
This is a personal project for one owner, soon a small group of friends. Don't add complexity (horizontal scaling, multi-region, elaborate admin tooling) that isn't asked for here.
---
1. Project Vision & Scope
A self-hosted platform unifying Garmin biometrics, Technogym gym sessions, blood-donation lab panels, subjective journaling (including Telegram voice notes), gear maintenance, and weather/conditions data into one database. A feature engine computes Whoop/Oura/Strava/Garmin-style derived metrics without needing those subscriptions. An API-based AI layer (tiered by cost, tool-using) provides chat, scheduled reports, and adaptive guidance — reachable via Telegram in this build round, since the web dashboard is deferred (Appendix A). Hosted on the owner's own hardware, under €5/month total recurring cost (AI tokens + any other service, electricity excluded).
Explicitly out of scope for this build round: the web dashboard and its design system (Appendix A — provisional, being revisited for design direction separately), and friend onboarding (which depends on having a UI for friends to actually use — see Section 15).
---
2. Tech Stack
Layer	Choice	Why
Backend	Python 3.12, FastAPI (async)	one language across connectors, feature engine, and API keeps the surface small for a project one person maintains
ORM / migrations	SQLAlchemy 2.0 (async) + Alembic, from commit 1	schema will evolve; retrofitting migrations later is worse than starting with them
Database	PostgreSQL 16 + TimescaleDB + pgvector	one engine covers relational integrity, time-series hypertables, and vector search — a second database (e.g. a dedicated vector store) would be another moving part and another monthly cost for no real benefit at this scale
Task queue	Celery + Redis	the Telegram voice pipeline needs background processing so it can acknowledge instantly (Section 10) — this isn't optional infrastructure, it's load-bearing from Phase 0
LLM (runtime)	Provider-agnostic client abstraction. Default: GLM-5.2 (powerful tier, reasoning-effort tuned), GLM-4.7-Flash (free/cheap tier), Claude Haiku 4.5 as paid fallback	GLM-5.2 is dramatically cheaper than Claude/GPT-class models at comparable quality, which is what makes the €5/month target realistic — see Section 9
STT	OpenAI Whisper API	cheap, reliable, and voice notes are short — cost is negligible regardless of provider choice here
Embeddings	OpenAI `text-embedding-3-small` (1536-dim), pinned	unlike the LLM, this is NOT freely swappable — see Section 6.2
Weather	Open-Meteo (free, no API key)	keeps a real feature inside the €5/month budget instead of trading it away
Watch app	Garmin Connect IQ SDK, Monkey C	deferred by phase order (Section 23) — not urgent to decide further right now
Bot transport	Telegram long polling, not a webhook	with the dashboard deferred, there's no other reason to expose anything publicly yet. Polling is outbound-only, exactly like the Garmin/Technogym sync jobs — no tunnel, no public port, no webhook secret to manage this round
Hosting	Self-hosted, single always-on machine, Docker Compose	the whole point is data staying under your control and cost staying near zero
Auth	Invite-only multi-user accounts, server-side sessions	built now for the owner account regardless, since the API needs protecting either way — friend rollout itself is deferred, Section 15
---
3. System Architecture — Data Flow
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
                                                                                   ▼
                                                              [6] Telegram Bot — polling, in-process
                                                                  calls into app/queries + the agent
                                                                  harness (no HTTP round-trip to itself)

[not built this round] FastAPI REST endpoints (Section 18) exist for when the web dashboard
                        (Appendix A) resumes — they are not the bot's dependency.
```
Why the raw store matters: `garminconnect` and the Technogym API are either unofficial or narrowly scoped. Storing every raw payload before normalizing means an upstream schema change breaks the parser, not the history — reprocess from raw JSON, don't lose data.
Why the bot calls functions in-process instead of over HTTP: it lives in the same codebase and the same deployment. Routing its own requests through the REST API would be a self-referential network hop with no benefit — the shared query layer (Section 8.2) exists precisely so both the bot and the (future) web API call the same logic without duplicating it.
---
4. Repository Structure
```
/health-control-center
  /backend
    /app
      /api            # FastAPI routers (Section 18) — built now, not yet publicly exposed
      /agent          # LLM client abstraction, tool registry, agent loop
      /queries        # shared read functions — used by the agent tools, report generation, AND the bot
      /auth           # session handling, invite codes, password hashing, rate limiting
      /connectors
        /garmin
        /technogym
        /telegram     # polling loop, not a webhook route
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
      /fixtures       # recorded connector payloads — the ONLY thing automated tests talk to
  /scripts
    reset-dev.sh      # tears down and recreates the local dev DB/Redis state from a clean slate
  /infra
    docker-compose.yml
  .env.example
  README.md

# NOT built this round (Appendix A): /frontend, Caddyfile, tailscale-funnel-setup.md, /connectiq
```
---
5. Environment Variables
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
# polling mode — no webhook secret needed this round; see Section 10

LLM_PROVIDER_CHEAP=
LLM_PROVIDER_POWERFUL=
GLM_API_KEY=
ANTHROPIC_API_KEY=

OPENAI_API_KEY=                  # embeddings + Whisper STT

DAILY_TOKEN_BUDGET_USD=
BACKUP_ENCRYPTION_KEY=
B2_APPLICATION_KEY_ID=
B2_APPLICATION_KEY=

OWNER_EMAIL=
OWNER_PASSWORD=
```
---
6. Database Schema — Full DDL
6.1 Seed data
`disciplines` is populated via an Alembic data migration: `enduro, road_cycling, skiing, sailing, kitesurf, windsurf, tennis, wakeboard, snowboard, surf, sim_racing, running, strength, gym_general` — categories `endurance`/`technical`/`strength` per the obvious mapping.
6.2 A note on the embeddings column
`embeddings.embedding` is `VECTOR(1536)`, matching OpenAI `text-embedding-3-small`. Unlike the LLM completion layer, this is not freely provider-swappable — different embedding models output different vector dimensions, and pgvector columns have a fixed dimension. Changing providers later requires an explicit migration (`ALTER COLUMN embedding TYPE vector(N)`) and re-embedding every existing row.
6.3 Historical backfill policy
On first connecting any historical-data source (Garmin, Technogym), the connector backfills the full available history, paginated to respect rate limits — not an arbitrary recent window. This product's value is long-term trend analysis; starting the record 30 days back would undercut the entire point. Ongoing sync (Section 19) then only needs to fetch what's new since `integrations.last_synced_at`.
6.4 DDL
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

-- one row per user who has linked a Telegram chat. Still exactly right under polling mode —
-- this table is about WHO is talking to the bot, not about how the bot receives messages.
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
    local_date       DATE NOT NULL,              -- calendar date of local start_time — Section 17
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

-- SCALE NOTE: one row per sample (commonly 1Hz) per activity — the largest table in this schema
-- by a wide margin over years of use. NOT a hypertable: t_offset_s is relative to each activity,
-- not absolute time, so hypertable partitioning on it wouldn't meaningfully distribute the data.
-- If size becomes a real problem later: add a derived absolute `sample_time` column and
-- hypertable-partition on that, or move to one-row-per-activity with a compressed array/JSONB
-- stream column. Not needed at current scale — noted so it isn't a surprise later.
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
-- Hypertable criterion: a table becomes a TimescaleDB hypertable only when it has genuinely
-- sub-daily-frequency inserts on an absolute timestamp column. Daily-grain tables use a plain
-- (user_id, date) primary key instead — hypertable overhead has no payoff at one row/user/day.

CREATE TABLE sleep_sessions (
    id               BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    local_date       DATE NOT NULL,          -- calendar date of end_time (wake-up) in local time — Section 17
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
    date          DATE NOT NULL,          -- user's local date, not UTC — Section 17
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
    source                    TEXT NOT NULL DEFAULT 'telegram_text' CHECK (source IN ('web','telegram_voice','telegram_text')),
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
-- SELECTION RULE: for a given (feature_name, component_name) and computation date D, use the row
-- with the latest effective_from <= D. This makes historical daily_features reproducible using the
-- weights that were actually active then, not today's weights. Changing feature_weights does NOT
-- retroactively rewrite past daily_features rows. A correction is: fix the feature_weights row,
-- then manually re-run the nightly feature-engine task for the affected date range — it upserts by
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
    source_feature_ids  TEXT[]              -- audit list of metric-name/date identifiers, NOT a foreign key
                                             -- (daily_features has a composite key, not a single id)
);

ALTER TABLE training_plans
    ADD CONSTRAINT fk_training_plans_source_report
    FOREIGN KEY (source_ai_report_id) REFERENCES ai_reports(id);

CREATE TABLE ai_chat_sessions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()
    -- SESSION BOUNDARY RULE: a new row is created when a user messages the bot after more than
    -- 30 minutes since last_activity_at; otherwise messages append to the existing session.
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
    session_id  BIGINT REFERENCES ai_chat_sessions(id),   -- nullable: also used by scheduled report
                                                            -- generation reusing the same query
                                                            -- functions (Section 8.2); NULL means
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
    embedding       VECTOR(1536),      -- pinned to text-embedding-3-small — Section 6.2
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
7. Feature Engine — Derived Metrics
Recovery Score — HRV deviation from rolling personal baseline, resting-HR deviation, sleep quality/duration, prior day's strain. 0–100.
Strain Score — cumulative daily cardiovascular load from HR-zone time (TRIMP-style), normalized against a personal ceiling.
Readiness Score — blends recovery, sleep architecture, and ACWR. The single most important daily number this product produces.
Sleep Architecture Score — REM%, deep%, efficiency, latency, circadian regularity vs. personal baseline.
ACWR — 7-day rolling load ÷ 28-day rolling load. Why one metric for both windows: mixing load metrics between the two windows was a real bug in an earlier draft of this project — the ratio is meaningless if the numerator and denominator aren't measuring the same thing.
Aerobic Decoupling — first half vs. second half of steady-state effort, arrays aligned by time offset, not sample count (an earlier bug misaligned these by count when sampling rate varied).
Illness Risk Score — HRV drop + resting-HR elevation + elevated respiration + journal soreness/fatigue, weights from `feature_weights` (selection rule: Section 6.4 comment).
FTP/Threshold Estimation — validated protocol/model only, never ad hoc regression (an earlier draft did this and produced physiologically implausible numbers).
Cross-Discipline Fatigue Index — load aggregated across active disciplines with discipline-specific decay — genuinely useful for a multi-sport athlete, since single-sport platforms can't see one discipline's fatigue bleeding into another.
Iron/Hematological Recovery Index — ferritin/hemoglobin depletion + recovery curve post-donation.
Gear Wear — cumulative hours/km since last service vs. configured interval (Section 13).
---
8. Agent Harness
8.1 LLM client abstraction
One interface (`app/core/llm.py`): `complete(messages, tools, system, cache_blocks, tier) -> Response`, implemented once per provider. Nothing else touches a provider SDK directly — this is what makes the tier/provider choice in Section 9 an env-var change, not a code change.
8.2 Shared query layer
Every tool below is a thin wrapper over a function in `app/queries/` — the same functions the scheduled report-generation tasks (Section 19) and the Telegram bot (Section 10) call directly, without going through the LLM agent loop when they don't need to. This exists so "get my ACWR trend" has exactly one implementation, not three that can silently drift apart. `agent_tool_calls.session_id` is nullable specifically because non-chat callers log there too.
8.3 Tool registry
Tool	Type	Inputs	Behavior
`get_metric_trend`	read	metric, start_date, end_date, discipline_id?	`daily_features`/`discipline_features`, compact table output
`get_lab_trend`	read	marker, start_date, end_date	`lab_panels`/`lab_metrics`
`get_activity_summary`	read	start_date, end_date, discipline_id?	aggregates from `activities`
`get_journal_entries`	read	start_date, end_date, tags?	`journal_entries`
`search_context`	read	query, top_k=5	pgvector cosine search over `embeddings`
`get_training_plan`	read	status?	current/active plan + `planned_sessions`
`get_donation_status`	read	—	next eligible date, days since last donation, iron flag
`get_gear_status`	read	gear_id?	usage vs. interval per gear item
`propose_training_plan`	write, confirmation required	week_start, sessions[]	creates `training_plans` (draft) + `planned_sessions`
`propose_supplement_change`	write, confirmation required	protocol changes	drafts, does not apply
`sync_plan_to_technogym`	write, confirmation required, only on a `confirmed` plan	training_plan_id	Section 11
8.4 Agent loop
Build the request: cached system block (profile, baselines, feature weights) + recent-detail window (7–14 days) + tool definitions.
Send to the tier selected by Section 9's routing rule.
Tool calls: execute via `app/queries/`, log to `agent_tool_calls`, loop (max 8 iterations, return best partial answer if not converged).
Final response: write `ai_chat_messages.referenced_data` and `model_tier`.
Tool errors return as tool results, not exceptions that kill the loop.
8.5 Write-tool confirmation flow
`propose_*` tools write a `draft`/`pending` row and return it — never commit directly. Why: these are AI-generated recommendations touching training decisions and, eventually, an external system (Technogym) — a plausible-looking wrong plan committed automatically is worse than one that waits a tap. Confirmation happens via a Telegram inline button this round (the dashboard confirm UI is deferred with everything else in Appendix A). Only a `confirmed` plan can sync to Technogym.
8.6 Cost governance
Every LLM/embedding call writes to `token_usage` (with user and tier). A daily task sums the day's cost; crossing `DAILY_TOKEN_BUDGET_USD` fires a `budget_warning` alert to Telegram — informational, not a hard stop.
---
9. AI Model Routing & Cost Engineering
9.1 Tiers
Tier	Used for	Default	Rate (per 1M tokens, in/out)
Free	Transcript structuring, routine classification, the router itself	GLM-4.7-Flash	$0
Cheap	Simple chat lookups, fallback if free tier is rate-limited	Claude Haiku 4.5	$1 / $5
Powerful	Weekly/monthly reports, plan generation, strategic chat	GLM-5.2, high/xhigh reasoning effort	$1.40 / $4.40 (cached $0.26)
9.2 Routing logic
Check `auth_credentials.ai_access_tier`. If `cheap_only`, the request is capped at free/cheap regardless of step 2 — powerful tier is simply unreachable for that account. This is the per-friend cost control valve, relevant once friend accounts exist (Section 15).
If `full`: a free-tier classification call tags the message `lookup` (→ free/cheap) or `strategic` (→ powerful).
Scheduled generation is hardcoded, not classified: daily summaries are templated (no LLM call); weekly/monthly reports are always powerful tier via the batch API where supported.
9.3 Realistic monthly cost
Item	Est. cost
Daily summaries (templated)	$0.00
Weekly + monthly reports	~$0.09
Voice extraction	~$0.00–0.05
Whisper STT	~$0.36
Chat (lookups + strategic)	~$0.00–0.52
Embeddings	~$0.05
Infra	$0.00
Total	≈ $0.60–1.05/month (≈ €0.55–1.00)
Large margin under the €5 target — `token_usage` + the budget alert is the actual safety net, not this estimate.
---
10. Telegram Bot Integration
10.1 Transport: long polling
The bot process runs `Application.run_polling()` (or equivalent) as its own long-running Celery-managed process — it asks Telegram's servers for updates rather than receiving pushed webhooks. Why: with the dashboard deferred, there's no other reason to expose anything to the public internet yet, and polling needs none — no tunnel, no public port, no webhook secret. This can be revisited when the dashboard (and its Tailscale Funnel exposure) comes back into scope; polling forever is also a perfectly legitimate permanent choice for a personal bot at this scale.
10.2 Message flow
Voice message → handler acknowledges, hands off to Celery.
Worker downloads the `.ogg`, sends to Whisper.
Transcript → free/cheap tier, structured extraction (discipline, mood/energy/soreness if mentioned, summary, tags; gear mentions override `discipline_gear_defaults`).
Bot replies with the draft + inline buttons (✅ Save / ✏️ Edit) — never auto-commits.
On confirm: written to `journal_entries`, linked to an existing activity if the timestamp falls in its window.
Plain text that isn't a recognized command routes to the full agent harness (Section 8), not just structured extraction — with the web Chat page deferred, Telegram is the only chat interface that exists this round, so it needs to carry the whole feature, not a subset.
10.3 Per-user linking
Since there's no web Settings page yet to generate a link code this round, linking is bot-initiated: `/link` sent by a not-yet-linked chat replies with a one-time code the user then confirms was them via a second factor — simplest workable version for one owner: the code is also printed to the server log/CLI on request, and the owner confirms it themselves via `/confirm <code>`. This is intentionally minimal since only the owner exists as a user until friend onboarding resumes (Section 15). `telegram_links(user_id, chat_id)` is written on confirmation.
Also supports: `/status`, `/donate`, `/report`, `/gear`. Alerts push to the linked user's chat as they trigger.
---
11. Technogym Integration
Available today: an enduser-to-enduser OAuth scenario (`developer.technogym.com` / `apidocs.mywellness.com`) with an official Python sample demonstrating auth + FIT/TCX activity upload — solidly achievable via self-serve registration. Pushing a plan as a prescribed program on equipment is documented under the Technogym Enterprise API, which reads as partner/facility-tier — uncertain for an individual account until actually registered and checked (Section 24).
Two stages, same manual-connection rule as Garmin (Section 0):
11a (build regardless): OAuth flow, pull completed sessions into `raw_ingest` → `activities` (full history, Section 6.3), optional FIT/TCX upload. Automated tests use fixtures; the real OAuth connection is run by the human.
11b (contingent): `sync_plan_to_technogym` once the real access tier is confirmed. Fallback if prescription-push isn't available: the plan reaches the user via `/plan today` in Telegram, followed manually.
---
12. Multi-Source Activity Reconciliation
On ingesting an activity, check for an existing row for the same user with `start_time` within ±10 minutes and a compatible discipline.
If found: no new `activities` row — add an `activity_source_links` entry, merge fields preferring the richer source per field (Garmin for HR/GPS, Technogym for machine power/resistance/incline), never overwrite a populated field with NULL.
If not found: create the row plus its first `activity_source_links` entry.
---
13. Gear Tracking
Auto-link via `discipline_gear_defaults` at ingestion (Telegram voice can override). Nightly job sums `duration_s`/`distance_m` since the last `gear_service_logs.performed_at` into `hours_since_service`/`km_since_service`. Crossing the configured interval fires `gear_service_due`, pushed to Telegram. Logging a new service resets the counters. This job is idempotent — re-running it must not double-count (Section 17).
---
14. Weather & Sport Dashboard
Open-Meteo (free, no key). `activities.weather_snapshot` populated at ingestion. `forecast_cache` refreshed on a schedule (Section 19). Without the dashboard this round, the primary access point is a `/forecast` bot command rather than a browsable page — the data collection and caching logic is identical either way, so building it now isn't wasted even though the visual "Sport Dashboard page" (Appendix A) waits. Worth building once the pieces exist: cross-reference a good forecast window with a high readiness score for a proactive Telegram nudge.
---
15. Multi-User & Remote Access
In scope now: the auth backend (`auth_credentials`, `sessions`, `invites`) — needed regardless of user count, since the API needs protecting even for an owner-only system. The owner account is bootstrapped from `OWNER_EMAIL`/`OWNER_PASSWORD` at startup.
Deferred alongside the dashboard: actually inviting and onboarding friends. Why these are linked: a friend has no way to meaningfully use this product without a UI — the web dashboard is what they'd actually look at, and asking a friend to interact purely through Telegram commands on someone else's bot is a much rougher onboarding than this project should ship. Revisit invites when Appendix A resumes.
Deferred alongside the dashboard: Tailscale Funnel / public exposure generally. Nothing needs to be publicly reachable this round — Telegram uses polling (Section 10.1), and there's no web frontend to serve.
---
16. Development Environment & Process Discipline
This section exists because the first build attempt lost committed work to an unreliable execution environment. It is as load-bearing as any schema table.
A git remote must exist before any code is written. The owner creates an empty private repository and provides the URL at the start of the session — do not proceed on a local-only repository, and do not attempt to create the remote yourself.
Commit and push after every acceptance criterion demonstrated, not just at phase end. If a phase has four acceptance criteria, that's up to four commits, each pushed immediately.
Verify, don't assume, at the start of every session: `git log`, `git status`, `git remote -v`, current Alembic revision if a database exists. If the environment was reprovisioned, this is how you find out before wasting time building on an assumption.
Docker parity is unverified until proven on the real host. If the working environment lacks Docker (as the first attempt's did), building the identical engine stack from source to demonstrate acceptance criteria with real output is acceptable — but say so plainly every time, and treat `docker compose up -d --build` succeeding on the owner's actual machine as a separate, required confirmation before considering any phase truly done, not a formality.
`/scripts/reset-dev.sh` tears down and recreates the local dev database/Redis state from nothing. Build this in Phase 0 — it turns "the environment is in a weird state" from a multi-hour debugging session into a one-command fix.
Repository is private. This is a personal health platform; the code that will eventually handle real credentials and real medical data has no reason to be public, even before any secrets or real data actually touch it.
Real third-party accounts are connected by the human, never by the agent unsupervised (Section 0, Section 11) — this is the process fix for the specific risk of an iterative debugging loop hammering a real account.
---
17. Non-Negotiable Engineering Constraints
Every timestamp is `timestamptz`, stored UTC; converted to local only at presentation. `activities` also stores `start_tz_offset_minutes`.
Day-boundary rule: every `date`/`local_date` column is derived using `users.timezone`, not UTC. A sleep session's date is the calendar date of its end_time (wake-up) in local time; an activity's date is the calendar date of its local start_time. Why: several tables key on "date," and without this rule a late-night or pre-dawn session gets silently miscategorized by a UTC boundary that doesn't match the athlete's actual day.
Efficiency-factor and decoupling math is always scoped by `discipline_id`, never pooled.
ACWR uses exactly one load metric for both windows.
FTP estimation uses a validated protocol/model only.
Feature weights live in `feature_weights`, versioned, selected by the rule in Section 6.4 — never hardcoded constants.
Every external source (Garmin, Technogym, weather) writes to `raw_ingest` before normalization.
All sync/ingest operations are idempotent upserts, keyed on `(source, external_id)`.
Days with incomplete sensor data are flagged (`data_completeness`), never silently scored as complete.
`lab_panels` is encrypted at the application layer before it touches disk.
Write-tools never commit directly — draft, then explicit confirm.
No route is reachable without a valid session except `/health` and the bootstrap/auth endpoints — moot for public exposure this round (Section 15), but true regardless.
Gear/weather/rollup accumulation jobs are idempotent — re-running must not double-count.
`disciplines` seed data comes from the Alembic migration in Section 6.1, never invented ad hoc.
Automated tests never make live calls to a real third-party account (Section 0, Section 16.7).
---
18. API Surface
Built this round even though nothing consumes it externally yet — the shared query layer (Section 8.2) needs these boundaries defined regardless, and it's what Appendix A's frontend will call when it resumes.
Resource	Base path	Notes
Auth	`/auth/login`, `/auth/logout`, `/auth/invite/redeem`	session cookie set on login
Activities	`/activities`, `/activities/{id}`	
Metrics	`/metrics/trend`, `/metrics/rollup`	
Labs	`/labs`, `/labs/{id}`	
Journal	`/journal`, `/journal/{id}`	
Training Plans	`/training-plans`, `/training-plans/{id}/confirm`	
Gear	`/gear`, `/gear/{id}/service`	
Weather	`/weather/forecast`	
Chat	`/chat/sessions`, `/chat/sessions/{id}/message`	mirrors what the Telegram bot already does in-process
Alerts	`/alerts`, `/alerts/{id}/ack`	
Settings	`/settings/integrations`, `/settings/invites`, `/settings/users/{id}/ai-tier`	owner-only, enforced by `role`
Health	`/health`	public — DB + Redis connectivity
---
19. Scheduled Jobs (Celery beat)
Job	Cadence	Notes
Garmin sync	every 6 hours	not real-time — an unofficial client polled continuously raises ban risk
Technogym sync	every 6 hours	same reasoning
Forecast refresh	every 6 hours	upserts `forecast_cache`
Nightly feature engine	1×/day, 03:00 user-local	prior local day, per Section 17's day-boundary rule
Gear accumulation	1×/day, right after feature engine	
Weekly rollups	Monday 03:30	
Monthly rollups	1st of month, 04:00	
Weekly AI report	Monday 06:00, batch API	
Monthly AI report	1st of month, 06:00, batch API	
Daily budget check	1×/day	
Database backup	nightly, 02:00	Section 22.7
Sync-failure escalation	after every sync task attempt	3 consecutive failures → `sync_failure` alert
---
20. Testing Strategy
Backend: pytest. Unit tests per module; the feature engine runs the golden-dataset regression (Section 7) as a required check. Connector tests run only against recorded fixtures in `/tests/fixtures` — no live third-party API calls in CI, ever (Section 0, Section 17).
CI: GitHub Actions runs pytest on every push. The golden-dataset regression failing blocks merge.
Frontend/e2e testing is deferred with the dashboard (Appendix A).
---
21. Observability & Error Handling
Structured JSON logging to stdout, captured by Docker's logging driver with rotation configured in `docker-compose.yml`.
`alerts` (DB-backed, user-facing, pushed to Telegram) and application logs (developer-facing) are distinct — don't conflate them.
Every connector sync task increments `integrations.consecutive_failures` on exception; three in a row fires `sync_failure` instead of failing silently.
`/health` checks DB and Redis connectivity.
---
22. Security Hardening
Login rate limiting: 5 failed attempts per email per 15 minutes → temporary lockout, Redis-backed sliding window.
Session cookies: `Secure`, `HttpOnly`, `SameSite=Lax`, short-lived with sliding expiry.
CSRF: state-changing requests require a custom header cross-origin requests can't attach.
CORS: moot with nothing publicly exposed this round — configure narrowly, not permissively, whenever that changes.
Secrets: `.env`, gitignored, restrictive file permissions; never logged, never echoed in API errors.
Input validation: Pydantic schemas at every API boundary; all DB access through the ORM's parameterized queries.
Backups: nightly `pg_dump`, encrypted with `BACKUP_ENCRYPTION_KEY`, uploaded to Backblaze B2's free tier. Retain 14 daily + 6 monthly archives. Test an actual restore once after Phase 0 — an untested backup is a hope, not a backup.
---
23. Phase-by-Phase Build Plan
Phase	Focus	Acceptance criteria
0	Repo scaffold (with remote configured, Section 16.1), Docker Compose, Alembic migration + seed data, FastAPI skeleton with `/health`, Celery+Redis, owner auth, baseline security middleware, `/scripts/reset-dev.sh`	`docker compose up` brings up all services; `/health` returns 200; owner login works; every Section 6 table exists with seed data; reset script proven to work
1	Garmin connector: auth, raw ingestion, normalizer, idempotent upsert, full historical backfill (Section 6.3), 6-hourly scheduled sync	fixture-based sync populates normalized tables; running it twice does not duplicate rows; real-account connection performed manually by the owner, not automated
2	Feature engine + golden-dataset regression tests, `feature_weights` seeded	tests pass; nightly task populates `daily_features`/`discipline_features` respecting the day-boundary rule
3	Telegram bot: polling loop, `/link` flow, voice/text handlers (including free-text → agent harness), confirm/edit, commands, alert push	a linked chat's voice note produces a confirmable draft; free text gets a real agent response; an unlinked chat is told to link first
4	Medical/lifestyle module + Gear tracking	low-ferritin entry fires an alert; a synthetic 15h-since-service gear item fires `gear_service_due`
5	Agent harness + AI layer: tools, loop, routing, `token_usage`, templated summaries, batch reports	a ≥2-tool-call query answers correctly and logs to `agent_tool_calls`; a `cheap_only` account never reaches the powerful tier
6	Technogym connector — Stage 11a always, 11b if access confirms	OAuth completes (manual connection); reconciliation (Section 12) prevents a duplicate against a same-window Garmin entry
7	Weather module	`weather_snapshot` populated on ingestion; forecast cache refreshes on schedule, reachable via `/forecast`
8	Testing/observability/security hardening pass, backup restore drill, remaining connectors	a restore-from-backup has been actually tested once
Deferred, not numbered as an active phase: the web dashboard and friend onboarding (Appendix A, Section 15). Revisit together once design direction is settled.
---
24. Open Items — Need a Human Decision
Technogym access tier: only resolves by registering and checking what's actually granted, before Phase 6's Stage 11b.
Data export/portability endpoint: not specced — reasonable post-launch, not blocking.
Web dashboard direction: intentionally open — Appendix A is provisional pending further design exploration, not a decision to implement yet.
Execution environment for this restart: whether GLM 5.2 runs somewhere persistent this time, or the same class of ephemeral sandbox — see Section 0. Not resolvable from this document; worth settling before Phase 0 starts.
---
25. Readiness Verdict
Ready to restart, on this revision. What changed and why: the web dashboard and friend onboarding are explicitly out of scope this round rather than silently assumed; Telegram moved to polling, removing a dependency (public exposure) that no longer has a reason to exist yet; real-account connections are now a manual, human-performed step rather than something an autonomous loop could do to a real account mid-debug; and Section 16 encodes the actual lesson from the last attempt — the spec wasn't what failed, the environment was, so the process rules now say so explicitly and require proof of state at every session start. Everything else — schema, feature engine, agent harness, cost engineering — was re-checked against these changes and holds. Start at Phase 0, in whatever environment you've settled on per the open item above.
---
Appendix A — Web UI Direction (Provisional, Not Yet In Scope)
Do not build this. It exists to preserve prior design thinking while more inspiration is gathered — treat everything below as a draft to be revisited, not a spec to implement.
Direction so far: an instrument-panel aesthetic (motorsport telemetry software, aviation glass cockpits, dive computers, rally roadbooks) rather than Whoop/Oura's soft rounded cards or a generic SaaS dashboard template. A token system (near-black base, amber primary readout/CTA, cyan secondary data channel, red reserved strictly for alerts, monospace numerals, condensed-grotesk UI text) and a page-by-page spec (Cockpit, Trends/Explorer, Activities, Labs & Donation, Journal, Training Plan, Gear, Sport Dashboard, Chat, Settings) with a four-state requirement (loading/empty/error/populated) per page were drafted previously. All of it is subject to change once further design exploration happens — none of it should be treated as final until this appendix is explicitly promoted back into the active spec.
