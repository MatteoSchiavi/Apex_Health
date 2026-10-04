"""Source evidence, bounded analysis and application-owned changes. Frozen DDL."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE ai_reports DROP CONSTRAINT ai_reports_report_type_check")
    op.execute(
        "ALTER TABLE ai_reports ADD CONSTRAINT ai_reports_report_type_check CHECK (report_type IN ('daily','weekly','monthly','quarterly'))"
    )
    op.execute(
        """CREATE TABLE lab_observations (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            metric TEXT NOT NULL,
            value JSONB NOT NULL,
            unit TEXT,
            origin TEXT NOT NULL,
            acquisition TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            measured_at TIMESTAMP WITH TIME ZONE NOT NULL,
            local_date DATE NOT NULL,
            timezone TEXT NOT NULL,
            fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revision INTEGER NOT NULL,
            current BOOLEAN NOT NULL,
            availability TEXT NOT NULL,
            quality_flags JSONB NOT NULL,
            metadata_json JSONB NOT NULL,
            raw_ingest_id BIGINT,
            content_hash TEXT NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, origin, metric, source_record_id, revision),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY(raw_ingest_id) REFERENCES raw_ingest (id) ON DELETE SET NULL
        )"""
    )
    op.execute(
        "CREATE INDEX ix_lab_observations_local_date ON lab_observations (local_date)"
    )
    op.execute("CREATE INDEX ix_lab_observations_metric ON lab_observations (metric)")
    op.execute("CREATE INDEX ix_lab_observations_user_id ON lab_observations (user_id)")
    op.execute(
        """CREATE TABLE lab_feed_states (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            provider TEXT NOT NULL,
            feed TEXT NOT NULL,
            availability TEXT NOT NULL,
            last_attempt_at TIMESTAMP WITH TIME ZONE,
            last_success_at TIMESTAMP WITH TIME ZONE,
            latest_measurement_at TIMESTAMP WITH TIME ZONE,
            cursor JSONB NOT NULL,
            details JSONB NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, provider, feed),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_lab_feed_states_user_id ON lab_feed_states (user_id)")
    op.execute(
        """CREATE TABLE athlete_entries (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            kind TEXT NOT NULL,
            date DATE NOT NULL,
            payload JSONB NOT NULL,
            revision INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_athlete_entries_date ON athlete_entries (date)")
    op.execute("CREATE INDEX ix_athlete_entries_kind ON athlete_entries (kind)")
    op.execute("CREATE INDEX ix_athlete_entries_user_id ON athlete_entries (user_id)")
    op.execute(
        """CREATE TABLE change_drafts (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            status TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload JSONB NOT NULL,
            before JSONB NOT NULL,
            after JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            snapshot_revision TEXT NOT NULL,
            evidence_ids JSONB NOT NULL,
            reason TEXT NOT NULL,
            risk TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            approved_at TIMESTAMP WITH TIME ZONE,
            receipt JSONB,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_change_drafts_user_id ON change_drafts (user_id)")
    op.execute(
        """CREATE TABLE decision_records (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            snapshot_revision TEXT NOT NULL,
            output JSONB NOT NULL,
            outcome JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (user_id, date, snapshot_revision),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_decision_records_user_id ON decision_records (user_id)")
    op.execute(
        """CREATE TABLE lab_notifications (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            dedupe_key TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            payload JSONB NOT NULL,
            state TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            snoozed_until TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            UNIQUE (user_id, dedupe_key),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute(
        "CREATE INDEX ix_lab_notifications_user_id ON lab_notifications (user_id)"
    )
    op.execute(
        """CREATE TABLE analysis_results (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            recipe TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            snapshot_revision TEXT NOT NULL,
            result JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_analysis_results_user_id ON analysis_results (user_id)")
    op.execute(
        """CREATE TABLE change_audit (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            draft_id BIGINT,
            action TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY(draft_id) REFERENCES change_drafts (id) ON DELETE SET NULL
        )"""
    )
    op.execute("CREATE INDEX ix_change_audit_user_id ON change_audit (user_id)")
    op.execute(
        """CREATE TABLE lab_jobs (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            kind TEXT NOT NULL,
            state TEXT NOT NULL,
            parameters JSONB NOT NULL,
            progress JSONB NOT NULL,
            task_id TEXT,
            cancel_requested BOOLEAN NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_lab_jobs_user_id ON lab_jobs (user_id)")
    op.execute(
        """CREATE TABLE lab_documents (
            id BIGSERIAL NOT NULL,
            user_id BIGINT NOT NULL,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            ciphertext BYTEA NOT NULL,
            excerpt_ciphertext BYTEA,
            status TEXT NOT NULL,
            revision INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )"""
    )
    op.execute("CREATE INDEX ix_lab_documents_user_id ON lab_documents (user_id)")
    op.execute(
        "CREATE INDEX ix_observation_current ON lab_observations (user_id, metric, local_date) WHERE current = true"
    )
    op.execute(
        "ALTER TABLE agent_tool_calls ADD COLUMN user_id BIGINT REFERENCES users(id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX ix_agent_tool_calls_user_id ON agent_tool_calls(user_id)")


def downgrade():
    op.execute(
        "DELETE FROM embeddings WHERE source_table='ai_reports' AND source_id IN (SELECT id FROM ai_reports WHERE report_type='quarterly')"
    )
    op.execute("DELETE FROM ai_reports WHERE report_type='quarterly'")
    op.execute("ALTER TABLE ai_reports DROP CONSTRAINT ai_reports_report_type_check")
    op.execute(
        "ALTER TABLE ai_reports ADD CONSTRAINT ai_reports_report_type_check CHECK (report_type IN ('daily','weekly','monthly'))"
    )
    op.drop_index("ix_agent_tool_calls_user_id", table_name="agent_tool_calls")
    op.drop_column("agent_tool_calls", "user_id")
    op.drop_table("lab_documents")
    op.drop_table("lab_jobs")
    op.drop_table("change_audit")
    op.drop_table("analysis_results")
    op.drop_table("lab_notifications")
    op.drop_table("decision_records")
    op.drop_table("change_drafts")
    op.drop_table("athlete_entries")
    op.drop_table("lab_feed_states")
    op.drop_table("lab_observations")
