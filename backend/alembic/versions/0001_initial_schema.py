"""Initial schema — verbatim transcription of MASTER_SPEC §6.4 DDL.

Table order follows FK dependencies; the spec's own comments are preserved.
The training_plans -> ai_reports FK is added via ALTER after ai_reports
exists, exactly as in §6.4.

Revision ID: 0001
Revises:
Create Date: 2026-09-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOWNGRADE_DROPS = [
    "forecast_cache",
    "alerts",
    "telegram_messages",
    "watch_sync_log",
    "token_usage",
    "embeddings",
    "agent_tool_calls",
    "ai_chat_messages",
    "ai_chat_sessions",
    "technogym_sync_log",
    "planned_sessions",
    "training_plans",
    "ai_reports",
    "monthly_rollups",
    "weekly_rollups",
    "discipline_features",
    "daily_features",
    "feature_weights",
    "supplement_logs",
    "supplement_protocols",
    "nutrition_logs",
    "journal_entries",
    "lab_metrics",
    "lab_panels",
    "daily_biometrics",
    "stress_readings",
    "hrv_readings",
    "sleep_sessions",
    "segment_efforts",
    "segments",
    "activity_streams",
    "activity_gear_links",
    "activity_source_links",
    "activities",
    "discipline_gear_defaults",
    "gear_service_logs",
    "gear",
    "disciplines",
    "raw_ingest",
    "integrations",
    "telegram_links",
    "sessions",
    "invites",
    "auth_credentials",
    "users",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ===================== IDENTITY, AUTH & INTEGRATIONS =====================

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE invites (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code          TEXT NOT NULL UNIQUE,
            created_by    BIGINT NOT NULL REFERENCES users(id),
            used_by       BIGINT REFERENCES users(id),
            expires_at    TIMESTAMPTZ NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
        CREATE TABLE sessions (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id       BIGINT NOT NULL REFERENCES users(id),
            token_hash    TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at    TIMESTAMPTZ NOT NULL
        );
    """)

    # One row per user who has linked a Telegram chat. Still exactly right under
    # polling mode — this table is about WHO is talking to the bot, not about how
    # the bot receives messages.
    op.execute("""
        CREATE TABLE telegram_links (
            user_id     BIGINT PRIMARY KEY REFERENCES users(id),
            chat_id     BIGINT NOT NULL UNIQUE,
            linked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE raw_ingest (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id       BIGINT NOT NULL REFERENCES users(id),
            source        TEXT NOT NULL,
            payload_type  TEXT NOT NULL,
            fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            raw_json      JSONB NOT NULL,
            processed     BOOLEAN NOT NULL DEFAULT false
        );
    """)
    op.execute(
        "CREATE INDEX idx_raw_ingest_unprocessed ON raw_ingest (source, processed) WHERE NOT processed;"
    )

    # ===================== DISCIPLINES & GEAR =====================

    op.execute("""
        CREATE TABLE disciplines (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name          TEXT NOT NULL UNIQUE,
            category      TEXT NOT NULL CHECK (category IN ('endurance','technical','strength')),
            ftp_model_type TEXT
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE gear_service_logs (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            gear_id       BIGINT NOT NULL REFERENCES gear(id),
            service_type  TEXT NOT NULL,
            performed_at  TIMESTAMPTZ NOT NULL,
            notes         TEXT
        );
    """)

    op.execute("""
        CREATE TABLE discipline_gear_defaults (
            user_id       BIGINT NOT NULL REFERENCES users(id),
            discipline_id BIGINT NOT NULL REFERENCES disciplines(id),
            gear_id       BIGINT NOT NULL REFERENCES gear(id),
            PRIMARY KEY (user_id, discipline_id)
        );
    """)

    # ===================== ACTIVITIES =====================

    op.execute("""
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
    """)
    op.execute(
        "CREATE INDEX idx_activities_user_time ON activities (user_id, start_time);"
    )
    op.execute(
        "CREATE INDEX idx_activities_user_local_date ON activities (user_id, local_date);"
    )

    op.execute("""
        CREATE TABLE activity_source_links (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            activity_id   BIGINT NOT NULL REFERENCES activities(id),
            source        TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            raw_ingest_id BIGINT REFERENCES raw_ingest(id),
            UNIQUE (source, external_id)
        );
    """)

    op.execute("""
        CREATE TABLE activity_gear_links (
            activity_id   BIGINT NOT NULL REFERENCES activities(id),
            gear_id       BIGINT NOT NULL REFERENCES gear(id),
            PRIMARY KEY (activity_id, gear_id)
        );
    """)

    # SCALE NOTE: one row per sample (commonly 1Hz) per activity — the largest table in
    # this schema by a wide margin over years of use. NOT a hypertable: t_offset_s is
    # relative to each activity, not absolute time, so hypertable partitioning on it
    # wouldn't meaningfully distribute the data. If size becomes a real problem later:
    # add a derived absolute `sample_time` column and hypertable-partition on that, or
    # move to one-row-per-activity with a compressed array/JSONB stream column. Not
    # needed at current scale — noted so it isn't a surprise later.
    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE segments (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            discipline_id BIGINT NOT NULL REFERENCES disciplines(id),
            name          TEXT NOT NULL,
            geo_polyline  TEXT
        );
    """)

    op.execute("""
        CREATE TABLE segment_efforts (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            segment_id     BIGINT NOT NULL REFERENCES segments(id),
            activity_id    BIGINT NOT NULL REFERENCES activities(id),
            elapsed_time_s INTEGER NOT NULL,
            rank           INTEGER,
            is_pr          BOOLEAN NOT NULL DEFAULT false
        );
    """)

    # ===================== SLEEP & RECOVERY SIGNALS =====================
    # Hypertable criterion: a table becomes a TimescaleDB hypertable only when it has
    # genuinely sub-daily-frequency inserts on an absolute timestamp column. Daily-grain
    # tables use a plain (user_id, date) primary key instead — hypertable overhead has
    # no payoff at one row/user/day.

    op.execute("""
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
    """)
    op.execute("SELECT create_hypertable('sleep_sessions', 'start_time');")

    op.execute("""
        CREATE TABLE hrv_readings (
            id               BIGINT GENERATED ALWAYS AS IDENTITY,
            user_id          BIGINT NOT NULL REFERENCES users(id),
            "timestamp"      TIMESTAMPTZ NOT NULL,
            hrv_ms           NUMERIC NOT NULL,
            reading_type     TEXT NOT NULL CHECK (reading_type IN ('overnight_avg','5min')),
            rolling_baseline_ms NUMERIC,
            PRIMARY KEY (id, "timestamp")
        );
    """)
    op.execute("SELECT create_hypertable('hrv_readings', 'timestamp');")

    op.execute("""
        CREATE TABLE stress_readings (
            id           BIGINT GENERATED ALWAYS AS IDENTITY,
            user_id      BIGINT NOT NULL REFERENCES users(id),
            "timestamp"  TIMESTAMPTZ NOT NULL,
            stress_level NUMERIC,
            body_battery NUMERIC,
            PRIMARY KEY (id, "timestamp")
        );
    """)
    op.execute("SELECT create_hypertable('stress_readings', 'timestamp');")

    op.execute("""
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
    """)

    # ===================== MEDICAL / LAB =====================

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE lab_metrics (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            lab_panel_id  BIGINT NOT NULL REFERENCES lab_panels(id),
            metric_name   TEXT NOT NULL,
            value         NUMERIC NOT NULL,
            unit          TEXT,
            ref_low       NUMERIC,
            ref_high      NUMERIC
        );
    """)

    # ===================== SUBJECTIVE / LIFESTYLE =====================

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE supplement_logs (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            protocol_id   BIGINT NOT NULL REFERENCES supplement_protocols(id),
            taken_at      TIMESTAMPTZ NOT NULL,
            adherence     BOOLEAN NOT NULL
        );
    """)

    # ===================== FEATURE ENGINE OUTPUT =====================

    op.execute("""
        CREATE TABLE feature_weights (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            feature_name   TEXT NOT NULL,
            component_name TEXT NOT NULL,
            weight         NUMERIC NOT NULL,
            version        INTEGER NOT NULL,
            effective_from TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    # SELECTION RULE: for a given (feature_name, component_name) and computation date D,
    # use the row with the latest effective_from <= D. This makes historical
    # daily_features reproducible using the weights that were actually active then, not
    # today's weights. Changing feature_weights does NOT retroactively rewrite past
    # daily_features rows. A correction is: fix the feature_weights row, then manually
    # re-run the nightly feature-engine task for the affected date range — it upserts by
    # (user_id, date), so this is a safe, idempotent backfill.

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE discipline_features (
            user_id                BIGINT NOT NULL REFERENCES users(id),
            discipline_id          BIGINT NOT NULL REFERENCES disciplines(id),
            date                   DATE NOT NULL,
            estimated_ftp          NUMERIC,
            aerobic_decoupling_pct NUMERIC,
            efficiency_factor      NUMERIC,
            PRIMARY KEY (user_id, discipline_id, date)
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    # ===================== TRAINING PLANS =====================

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    # ===================== AI LAYER =====================

    op.execute("""
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
    """)

    op.execute("""
        ALTER TABLE training_plans
            ADD CONSTRAINT fk_training_plans_source_report
            FOREIGN KEY (source_ai_report_id) REFERENCES ai_reports(id);
    """)

    op.execute("""
        CREATE TABLE ai_chat_sessions (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id),
            started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()
            -- SESSION BOUNDARY RULE: a new row is created when a user messages the bot
            -- after more than 30 minutes since last_activity_at; otherwise messages
            -- append to the existing session.
        );
    """)

    op.execute("""
        CREATE TABLE ai_chat_messages (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            session_id      BIGINT NOT NULL REFERENCES ai_chat_sessions(id),
            role            TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
            content         TEXT NOT NULL,
            model_tier      TEXT CHECK (model_tier IN ('free','cheap','powerful')),
            referenced_data JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
        CREATE TABLE embeddings (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_table    TEXT NOT NULL,
            source_id       BIGINT NOT NULL,
            embedding       VECTOR(1536),      -- pinned to text-embedding-3-small — Section 6.2
            content_snippet TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);"
    )

    op.execute("""
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
    """)

    # ===================== WATCH, BOT & ALERTS =====================

    op.execute("""
        CREATE TABLE watch_sync_log (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id         BIGINT NOT NULL REFERENCES users(id),
            device_id       TEXT,
            sync_type       TEXT,
            synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload_summary JSONB
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    # ===================== WEATHER =====================

    op.execute("""
        CREATE TABLE forecast_cache (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            lat         NUMERIC NOT NULL,
            lon         NUMERIC NOT NULL,
            date        DATE NOT NULL,
            fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload     JSONB NOT NULL,
            UNIQUE (lat, lon, date)
        );
    """)


def downgrade() -> None:
    for table in _DOWNGRADE_DROPS:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
    op.execute("DROP EXTENSION IF EXISTS timescaledb;")
