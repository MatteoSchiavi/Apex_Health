"""Official web UI foundation: user preferences, main-device law, chat
titles, activity laps.

Owner request (2026-09 session): the UI is now the product. Users choose
language (en/it) and theme at account creation or in Settings, so those
preferences live on the account itself — the choice follows the user across
browsers and devices instead of hiding in localStorage.

Device priority law: each user may designate ONE connected integration as the
MAIN device. It wins every metric where it carries data; secondary devices
fill missing days/fields, and a secondary's ACTIVITY overrides the timeframe
when the main device recorded none (services/device_merge.py owns the rule).
`users.main_integration_id` is the declaration; NULL means "first connected
wins" (legacy behaviour for existing accounts).

ai_chat_sessions.title: the web chat needs a resumable session list; titles
are generated from the first user message (cheap model, local fallback).

activity_laps: FIT enrichment (services/fit_enrichment.py) parses lap records
out of Garmin FIT files — splits, per-lap HR/power/duration — that Garmin
Connect's JSON API does not expose. Rows are keyed (activity_id, lap_index)
and upserted idempotently like every ingest path.

integrations.provider CHECK gains 'oura' and 'coros' (Oura API v2 cloud, COROS
Open API) — same drop/re-add pattern migration 0006 used for 'whoop'.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users: UI preferences + main device declaration --------------------
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locale TEXT "
        "NOT NULL DEFAULT 'en' CHECK (locale IN ('en','it'))"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS theme TEXT "
        "NOT NULL DEFAULT 'dark' CHECK (theme IN ('dark','light'))"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS units TEXT "
        "NOT NULL DEFAULT 'metric' CHECK (units IN ('metric','imperial'))"
    )
    # NOTE: deliberately NO database-level FK to integrations. The reference
    # is validated in the API layer (api/me.py) and services/device_merge.py.
    # A users→integrations FK reverses the TRUNCATE ... CASCADE topology the
    # test helpers (and reset tooling) rely on: truncating integrations would
    # cascade into users/auth_credentials and wipe every account.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS main_integration_id BIGINT"
    )

    # --- chat session titles (resumable web chat list) -----------------------
    op.execute("ALTER TABLE ai_chat_sessions ADD COLUMN IF NOT EXISTS title TEXT")

    # --- activity laps (FIT enrichment output) -------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS activity_laps (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            activity_id     BIGINT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            lap_index       INTEGER NOT NULL,
            start_time      TIMESTAMPTZ,
            duration_s      INTEGER,
            distance_m      NUMERIC,
            avg_hr          INTEGER,
            max_hr          INTEGER,
            avg_power       NUMERIC,
            calories        INTEGER,
            extras          JSONB,
            UNIQUE (activity_id, lap_index)
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_activity_laps_activity "
        "ON activity_laps(activity_id)"
    )

    # --- providers: Oura + COROS join the CHECK ------------------------------
    op.execute(
        "ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check"
    )
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram','whoop','oura','coros'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE integrations DROP CONSTRAINT integrations_provider_check"
    )
    op.execute(
        "ALTER TABLE integrations ADD CONSTRAINT integrations_provider_check "
        "CHECK (provider IN ('garmin','technogym','strava','myfitnesspal',"
        "'telegram','whoop'))"
    )
    op.execute("DROP TABLE IF EXISTS activity_laps")
    op.execute("ALTER TABLE ai_chat_sessions DROP COLUMN IF EXISTS title")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS main_integration_id"
    )
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS units")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS theme")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locale")
