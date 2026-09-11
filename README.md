# Apex Health — Personal Health & Performance Control Center

Backend for a self-hosted platform unifying Garmin biometrics, Technogym gym
sessions, blood-donation lab panels, subjective journaling (Telegram voice
notes), gear maintenance, and weather data — with a derived-metrics feature
engine and a tiered, tool-using AI layer. Single source of truth:
[`MASTER_SPEC.md`](./MASTER_SPEC.md).

**Out of scope this build round** (per the spec): web dashboard (Appendix A)
and friend onboarding.

## Stack

Python 3.12 · FastAPI (async) · SQLAlchemy 2.0 (async) + Alembic ·
PostgreSQL 16 + TimescaleDB + pgvector · Celery + Redis · Telegram long
polling (from Phase 3) · Docker Compose.

## Layout

```
backend/          FastAPI app, Alembic migrations, tests
  app/api         REST routers (§18) — built now, not publicly exposed yet
  app/auth        sessions, owner bootstrap, login rate limiting
  app/core        config, db/redis, security, logging, middleware
  app/models      ORM models (grow phase by phase)
  app/connectors  per-source connectors (garmin in Phase 1; technogym/telegram/weather later)
  app/features    derived-metrics engine (§7) — loads, scores, discipline math
  app/schemas     Pydantic boundary schemas
  app/tasks       Celery tasks (§19 schedule lands with its phases)
  tools           owner-only operational CLIs (garmin connection)
infra/            docker-compose.yml
scripts/          reset-dev.sh — rebuild dev DB/Redis from a clean slate
```

## Quickstart (host with Docker)

```bash
cp .env.example .env          # fill in values
docker compose -f infra/docker-compose.yml up -d --build
curl http://localhost:8000/health
```

## Development without Docker

The same engine (PostgreSQL 16 + TimescaleDB + pgvector, Redis) must be
reachable at the URLs in `.env`. Then:

```bash
cd backend && uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000
uv run celery -A app.tasks.celery_app worker --loglevel=INFO
```

## Temporary web UI (Grafana)

Until the real dashboard is designed (spec-deferred, Appendix A), a full
read-only Grafana UI serves every feature above: overview, training,
recovery/sleep, nutrition/supplements, labs/blood health, AI & agent
observability, journal, and system/sync health — provisioned as versioned
dashboard JSON talking SELECT-only to the dev database.

```bash
bash scripts/start_dev_env.sh   # dev stack first
grafana/run_grafana.sh          # → http://127.0.0.1:3001 (anonymous viewer; admin/apex-demo)
```

Optional deterministic demo data for the UI:
`cd backend && .venv/bin/python -m tools.seed_demo_data` (synthetic 180-day
dataset — see `grafana/README.md` for coverage and maintenance).

## Garmin connector (Phase 1)

Sync runs every 6 hours via Celery beat (§19): activities (+ streams), sleep,
HRV, stress, and daily biometrics. Every payload is stored raw before
normalization (§3/§17); all writes are idempotent upserts keyed
`(source, external_id)` (§17). Connecting the real account is the owner's
manual step (§23 Phase 1) — automated tests only ever use recorded fixtures
in `backend/tests/fixtures/garmin/`.

```bash
cd backend
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=... \
    uv run python -m tools.garmin_sync connect      # login, store tokens encrypted, full backfill
uv run python -m tools.garmin_sync sync             # incremental sync now
uv run python -m tools.garmin_sync sync --backfill  # re-walk full history
uv run python -m tools.garmin_sync status
```

`connect` logs in once via the unofficial `garminconnect` client; session
tokens are stored app-layer-encrypted in `integrations.credentials_encrypted`
(§17) and the password is never persisted. Three consecutive sync failures
fire a `sync_failure` alert (§21).

## Feature engine (Phase 2)

The nightly Celery beat task (`features.nightly`, dispatched hourly, run for
each user whose local wall clock reads 03:00 — §19) computes the previous
LOCAL day's `daily_features` and `discipline_features` (§17 day-boundary
rule). Blend weights live in `feature_weights` (§6.4 selection rule: latest
`effective_from` <= start of local day); the seeded v1 rows are epoch-stamped
so historical dates stay reproducible. Days with missing sensor inputs are
flagged `data_completeness='partial'`, never silently scored (§17).

The engine is pinned by a golden-dataset regression suite
(`backend/tests/fixtures/golden/` — 35 days spanning the 2025-03-30 EU DST
change, expectations hand-computed). Any functional-form change that moves a
number fails the suite.

Correcting a weight version or source data? Re-run the affected range —
upserts by primary key make it a safe idempotent backfill (§6.4):

```bash
cd backend && uv run python -c "
import asyncio
from datetime import date
from app.core.db import sessionmaker
from app.features.engine import compute_user_range
from app.models.user import User

async def main():
    async with sessionmaker() as s:
        user = await s.get(User, 1)
        print(await compute_user_range(s, user, date(2025, 4, 1), date(2025, 4, 11)))

asyncio.run(main())
"
```

## Telegram bot (Phase 3)

Long polling (§10.1): the bot process asks Telegram for updates — outbound-only,
no webhook, no public port, no tunnel. Added as the `bot` compose service.

- **Linking (§10.3):** `/link` issues a one-time code (Redis, 15-minute TTL,
  printed to the server log); `/confirm <code>` binds the chat to the owner
  account in `telegram_links`. Every other update from an unlinked chat is
  told to link first (§23 Phase 3 AC).
- **Voice notes (§10.2):** ack → Celery hand-off (`telegram.process_voice`) →
  `.ogg` download → Whisper STT → free-tier structured extraction → a
  **pending draft** with ✅ Save / ✏️ Edit buttons. Save writes
  `journal_entries` (source `telegram_voice`, §17 local date, activity-window
  context); Edit re-extracts from a corrections text message. Never
  auto-commits.
- **Commands (§10.3):** `/status` (integrations + daily snapshot), `/donate`
  (last donation, eligibility, iron flag), `/report` (templated daily summary
  — deliberately no LLM, §9.2), `/gear` (usage vs service intervals). Reads go
  through the shared query layer `app/queries` (§8.2).
- **Free text:** routed to `app/agent/entrypoint.py` — a real, data-grounded
  response built on a compact snapshot (latest features, 7-day trend, open
  alerts), logged to `ai_chat_sessions`/`ai_chat_messages` with the §6.4
  30-minute session boundary. The full tool-using harness, tier routing and
  token accounting land in Phase 5 (§23) inside the same entrypoint.
- **Alert push (§21):** alert-creating code paths commit the row then call
  `push_alert` — delivered to the linked chat with severity icons.

Running live needs `TELEGRAM_BOT_TOKEN` (§5); the voice pipeline additionally
needs `OPENAI_API_KEY` (Whisper) and `GLM_API_KEY` on the worker, and the
Celery worker must be running for voice drafts:

```bash
docker compose --project-directory infra up -d db redis worker bot
# or without Docker:
cd backend && uv run python -m app.connectors.telegram.polling
```

Automated tests and demos never touch the live Bot API, LLM, or STT — they run
against recorded fixtures only (§0/§20).

## Medical, lifestyle & gear (Phase 4)

- **Lab panels (§6.4, §17):** `POST /labs` records a panel — standard markers
  as structured columns, every marker mirrored into `lab_metrics` with unit
  and the lab's reference range, free-text notes encrypted at the application
  layer before they touch disk. `GET /labs` / `GET /labs/{id}` read panels
  back (notes decrypted in the service layer only). Session-protected;
  POST requires the CSRF header.
- **Low-ferritin alert (§23 Phase 4 AC1):** a ferritin value below the
  lab-provided reference low (or `LOW_FERRITIN_NG_ML`, default 30 ng/mL)
  fires a `low_ferritin` alert row, then pushes to the linked chat (§21).
- **Lifestyle:** nutrition logs and supplement protocols/intake ingest
  through `app/medical/lifestyle.py`.
- **Gear (§13):** ingested activities auto-inherit the discipline's default
  gear (`discipline_gear_defaults`, idempotent via PK). The nightly
  `gear.accumulate_all` task (beat :15, runs inside the 03:00-03:59 local
  window right after the feature engine, §19) RECOMPUTES
  `hours_since_service`/`km_since_service` from linked activities — a
  recompute, never an increment, so re-runs never double-count (§17).
  Crossing a configured interval fires ONE `gear_service_due` alert per gear
  and pushes it; logging a service (`POST /gear/{id}/service` endpoint shape,
  §18) resets the counters and resolves the open alert.
- **Shared reads (§8.2):** `get_lab_trend`, `get_donation_status`,
  `get_gear_status` now run on the Phase 4 ORM models — the same functions
  the bot, future agent tools, and report tasks call.

## Agent harness & AI layer (Phase 5)

- **Tool loop (§8.4):** free text now runs the full harness — the model sees
  a cached system block (profile, active feature weights, a 14-day feature
  window, open alerts) plus the §8.3 tool registry, and can call tools for
  up to 8 iterations before returning the best partial answer. Tool errors
  come back as results, never as crashes. Every tool execution is audited to
  `agent_tool_calls` (with `session_id`; scheduled callers log NULL).
- **Tool registry (§8.3):** all eleven tools — `get_metric_trend`,
  `get_lab_trend`, `get_activity_summary`, `get_journal_entries`,
  `search_context`, `get_training_plan`, `get_donation_status`,
  `get_gear_status`, plus the write tools `propose_training_plan`,
  `propose_supplement_change`, `sync_plan_to_technogym` — are thin wrappers
  over the §8.2 query layer.
- **Write-tool confirmation (§8.5):** propose tools only DRAFT (plan row at
  `status='draft'`, supplement proposal at `active=false`); the bot attaches
  inline ✅/❌ buttons and only a human tap confirms — confirming a plan
  (prerequisite for §11b sync) or activating a supplement protocol (which
  ends the one it replaces). Rejection deletes the draft.
- **Routing (§9.2):** an account with `ai_access_tier='cheap_only'` can never
  reach the powerful tier — the request is capped regardless of content.
  `full` accounts get a free-tier classification call tagging the message
  `lookup` (→ cheap) or `strategic` (→ powerful). Fail-closed everywhere:
  missing credential rows cap, unparsable classifications downgrade to cheap.
- **Cost governance (§8.6):** every LLM/embedding call writes `token_usage`
  with a §9.1 rate-table cost estimate; the daily `budget.daily_check` task
  (beat 23:45 UTC) sums each account's day and fires an informational
  `budget_warning` alert (once per user per UTC day) over
  `DAILY_TOKEN_BUDGET_USD`. Whisper STT is not an LLM/embedding call — its
  per-minute cost is out of §8.6's letter and lands with the Phase 8
  observability pass.
- **Reports (§19, §9.2):** the daily summary is TEMPLATED — zero LLM cost,
  `model_used` NULL (§6.4) — persisted at :45 inside each user's 03:00-03:59
  local window (after the feature engine and gear accumulation; §19 does not
  schedule it explicitly, this is the documented judgment call). Weekly
  (Monday 06:00 local) and monthly (1st 06:00 local) reports are always
  POWERFUL tier over a §8.2 data pack, audited with `session_id=NULL`, and
  pushed to linked chats. All report rows upsert idempotently per period.
- **Semantic search (§6.2, §8.3):** journal entries (on save) and report
  content (on generation) are embedded with the PINNED
  `text-embedding-3-small`; `search_context` runs pgvector cosine over them,
  scoped to the caller via the source rows (§6.4's embeddings table has no
  user_id). Without `OPENAI_API_KEY` the tool degrades to a readable
  "unavailable" result.

## Technogym connector (Phase 6)

- **Stage 11a (built regardless, §11):** OAuth2 authorization-code flow per
  the enduser-to-enduser sample on developer.technogym.com — authorize URL
  with a single-use Redis-backed `state`, code exchange, single-flight token
  refresh on sync (rotated tokens are re-encrypted back into
  `integrations.credentials_encrypted`). Workout pulls go raw-first into
  `raw_ingest` (`workout` + `workout_detail:{id}` payload types), then the
  normalizer upserts `activities` keyed on `(source='technogym',
  external_id)` — full history backfill on first sync, ±10 min-window
  incremental afterwards, every remote call paced like Garmin (§19).
- **Multi-source reconciliation (§12, Phase 6 AC):** when an ingested
  session lands within ±10 minutes of an existing row for the same user and
  the SAME seeded discipline, no duplicate `activities` row is created — the
  new source is attached via `activity_source_links` and fields merge per
  the richer-source-per-field rule (Garmin for HR/GPS-derived, Technogym for
  machine power), and a populated field is NEVER overwritten with NULL.
  Candidates already linked to the incoming source are excluded, so two
  Technogym machine sessions five minutes apart stay two workouts. The rule
  runs symmetrically — Garmin arrivals reconcile into Technogym rows too.
  Judgment calls are documented in `app/connectors/reconciliation.py`.
- **Manual connection (§0/§16.7, Phase 6 AC):** the owner connects the real
  account themselves — either `POST /settings/integrations/technogym/authorize`
  then open the returned URL (provider redirects to
  `/integrations/technogym/callback`, which the single-use state
  authenticates), or the CLI:

  ```bash
  cd backend
  TECHNOGYM_CLIENT_ID=... TECHNOGYM_CLIENT_SECRET=... \
      uv run python tools/technogym_connect.py start   # prints URL + state
  # provider redirect completes automatically; otherwise paste the code:
  uv run python tools/technogym_connect.py complete <code> <state>
  uv run python tools/technogym_connect.py sync [--backfill]
  uv run python tools/technogym_connect.py status
  ```
- **Stage 11b (contingent, §24):** `sync_plan_to_technogym` still validates
  the confirmed-plan precondition and returns the documented fallback until
  the owner registers and confirms what the individual access tier grants.
  The fallback delivery path is now real: `/plan today` in Telegram shows
  the day's confirmed-plan sessions (drafts never show) with the
  follow-manually note. Fixture payloads are recorded-shape placeholders —
  the first real manual sync captures live payloads, and raw-first design
  means any shape drift is a parser fix, never data loss (§3).
- **Schedule (§19):** `technogym.sync_all` runs every 6 hours, staggered at
  :10 off the Garmin :00 tick (load-spreading judgment call); §21
  escalation (3 consecutive failures -> `sync_failure` alert) is now a
  shared helper both connectors use.

## Reset dev state

```bash
scripts/reset-dev.sh           # -f to skip the confirmation prompt
```

## Auth & API notes

- Owner account is bootstrapped at startup from `OWNER_EMAIL`/`OWNER_PASSWORD` (§15).
- `POST /auth/login` returns a `Secure`, `HttpOnly`, `SameSite=Lax` session cookie (§22.2).
- Every state-changing request must send `X-CSRF-Token: <any-value>` (§22.3) —
  a custom header cross-origin requests cannot attach without a preflight.
- Five failed logins per email per 15 minutes lock the account temporarily (§22.1).
- `GET /health` is the only public route (§17).

## Weather module (Phase 7)

- **Source (§2, §14):** Open-Meteo — free, no API key, which is the spec's
  exact reason for choosing it. Two endpoints: the forecast API (future days
  plus up to 92 past days) and the archive API (full history, lagging a few
  days behind real time). Raw-first per §3/§17: every upstream payload lands
  in `raw_ingest` (`source='open-meteo'`, `payload_type='forecast' |
  'archive'`) before normalization.
- **Forecast cache (§19 AC):** `weather.refresh_all` runs every 6 hours on
  beat (staggered at :20, right after both connector syncs) and upserts
  `forecast_cache` on its `UNIQUE (lat, lon, date)` key. The cache key uses
  the coordinates we asked for, not the grid-snapped values Open-Meteo
  echoes back — echoed values drift a grid cell between refreshes and would
  quietly multiply near-duplicate rows. Re-running rewrites the same rows:
  the scheduled refresh never double-counts (§17).
- **`weather_snapshot` on ingestion (§14 AC):** the same beat tick enriches
  every activity whose `weather_snapshot` is still NULL — coordinates from
  the activity's first positioned stream sample, falling back to the
  configured home coordinates. Recent dates ride the forecast API's past
  window; dates older than the archive lag go to the archive API. Only NULL
  columns are ever written (the pass never overwrites, so it is idempotent);
  the column is `none_as_null` so "not weathered yet" means SQL NULL for
  every writer.
- **Access points:** the `/forecast [days]` bot command (§14's primary access
  point while the dashboard is deferred) and `GET /weather/forecast?days=N`
  (§18) read the same cache through the same `get_forecast` query (§8.2 —
  one implementation per read, one WMO code table shared by both).
- **§14 nudge:** once per user per local day (07:00 local, hourly beat
  dispatch), when TOMORROW's cached forecast is a good training window
  (documented thresholds: max temp 5–28°C, rain probability ≤ 40%, wind
  ≤ 35 km/h) AND the latest readiness is at least
  `WEATHER_NUDGE_READINESS_THRESHOLD` (default 70), the user's linked chats
  get one proactive message. Redis SETNX dedup — a re-run the same day stays
  quiet.
- **Configuration (env tunables):** `WEATHER_HOME_LAT` / `WEATHER_HOME_LON`
  (unset/0 disables the refresh with a logged note instead of failing a beat
  tick), `WEATHER_FORECAST_DAYS` (default 7), `WEATHER_NUDGE_READINESS_THRESHOLD`
  (≤ 0 disables the nudge). Weather has no `integrations` row — the source is
  keyless, there are no credentials to store and no §21 escalation path;
  failures are logged and retried on the next tick.

## Backups & disaster recovery (Phase 8)

§22.7: nightly `pg_dump` at 02:00 UTC (§19), encrypted with a key **dedicated
to backups** (`BACKUP_ENCRYPTION_KEY` — independent from the app's
`ENCRYPTION_KEY` so one leaked key cannot open both), retained as 14 daily +
6 monthly archives (first-of-month snapshots are the monthly pool — judgment
call documented in `app/core/backups.py`).

- **Artifact format:** `hcc-YYYYMMDD-HHMMSS.{daily|monthly}.sql.gz.enc` —
  Fernet(gzip(plain-SQL pg_dump)). The dump is encrypted *before* it touches
  the backup directory; a plaintext dump of health data is never written
  anywhere, ever. `BACKUP_ENCRYPTION_KEY` unset ⇒ the nightly task logs an
  honest skip (never an unencrypted fallback).
- **Offsite (§22.7):** the artifact is pushed to Backblaze B2 when
  `B2_APPLICATION_KEY_ID`/`B2_APPLICATION_KEY`/`B2_BUCKET` are set (native v2
  API over httpx, no extra dependency). A failed upload never fails the local
  backup — it is reported honestly and retried the next night.
- **Restore:** `backend/tools/restore_backup.py <artifact> --target-dsn …`
  decrypts, gunzips and pipes the SQL into psql with `ON_ERROR_STOP` — stdin
  only, so no plaintext temp file ever hits disk. TimescaleDB hypertables
  restore under the documented `timescaledb_pre_restore()` /
  `timescaledb_post_restore()` wrapper; DSNs are redacted from any error
  output.
- **The restore drill (§22.7 AC):** `backend/tools/restore_drill.py` seeds
  marker data through the ORM (owner, activity, a `sleep_sessions`
  hypertable row, journal entry, Fernet-encrypted lab panel), snapshots every
  public table, runs the real backup pipeline, restores into a scratch
  `hcc_restore_drill` database and compares table-by-table — including
  `alembic_version` and proving the encrypted lab note still decrypts with
  the *app* key. First live run: **46/46 tables matched**. Rerun it on the
  real host after `docker compose up` parity is proven:

  ```bash
  BACKUP_ENCRYPTION_KEY=<key> uv run python tools/restore_drill.py
  ```

  `backups/` is gitignored — artifacts of real health data never enter git.

## Status

- Phase 0 (scaffold) — complete: schema + seed, `/health`, owner auth +
  security middleware, Celery wiring, reset script, CI.
- Phase 1 (Garmin connector) — complete: fixture-based sync acceptance met;
  real-account connection is the owner's manual `tools/garmin_sync.py connect` step.
- Phase 2 (feature engine) — complete: golden-dataset regression suite green;
  nightly task populates daily/discipline features respecting the day-boundary
  rule; `feature_weights` seeded (v1).
- Phase 3 (Telegram bot) — complete: polling loop, `/link` flow, voice
  pipeline with confirmable drafts, commands via the shared query layer,
  free-text agent entrypoint, alert push. Live bot needs `TELEGRAM_BOT_TOKEN`;
  fixtures only in tests/demos (§0).
- Phase 4 (medical/lifestyle/gear) — complete: lab panels + low-ferritin
  alert, nutrition/supplement ingestion, gear accumulation with
  `gear_service_due`, `/labs` + `/gear` APIs.
- Phase 5 (agent harness + AI layer) — complete: §8.3 tool registry, §8.4
  loop with `agent_tool_calls` audit, §9.2 per-account routing + free-tier
  classification, §8.6 `token_usage` + daily budget check, templated daily
  summaries, powerful-tier weekly/monthly reports, §8.5 Telegram
  confirmation flow, pgvector `search_context`. Live LLM calls need
  `GLM_API_KEY`; embeddings need `OPENAI_API_KEY` (§6.2 pinned model).
- Phase 6 (Technogym connector) — complete: Stage 11a OAuth2 flow with
  manual owner connection (API + `tools/technogym_connect.py`), raw-first
  workout ingestion with full-history backfill and 6-hourly sync, §12
  multi-source reconciliation (no duplicates against same-window Garmin
  entries), `/plan today` fallback for the contingent Stage 11b. Real
  connection needs `TECHNOGYM_CLIENT_ID/SECRET`; endpoints tunable via env
  until registration confirms the §24 access tier. Stage 11b
  prescription-push stays behind the §24 human decision.
- Phase 7 (weather module) — complete: Open-Meteo client (keyless), raw-first
  forecast refresh upserting `forecast_cache` every 6 hours (idempotent on
  lat/lon/date), §14 `activities.weather_snapshot` enrichment on ingestion
  (stream coords → home fallback, NULL-only writes), `/forecast` bot command
  + `GET /weather/forecast` over one shared query, §14 forecast × readiness
  nudge with per-day Redis dedup. Needs `WEATHER_HOME_LAT`/`WEATHER_HOME_LON`
  to produce data; tests/demos use recorded Open-Meteo fixtures only.
  Docker parity still unproven until `docker compose up -d --build` runs on
  the owner's host.
- Phase 8 (hardening, backups, remaining connectors) — complete: nightly
  encrypted backup pipeline + retention, B2 offsite upload, restore tooling,
  the §22.7 restore drill (tested for real — 46/46 tables match), and a
  hardening audit locking sliding sessions, the route-auth matrix and JSON
  logging (see "Backups & disaster recovery" above). Remaining connectors:
  all connectors the spec actually defines (Garmin, Technogym, weather,
  Telegram/STT/embeddings) are built; Strava/MFP have no integration
  sections — §1 substitutes them with the feature engine ("without needing
  those subscriptions"), and the only mentions are the §3 diagram and the
  `activity_source_links.provider` enum. Treated as deliberately out of
  scope rather than invented spec (§0: implementation layer, not
  architecture layer). Suite: 228 tests green.
- Temporary web UI (Grafana) — complete: 8 provisioned dashboards covering
  every table/feature of Phases 0-8 (read-only `grafana_ro` role, anonymous
  viewer, generated dashboard JSON + panel-SQL validator + deterministic
  180-day demo seeder). Stop-gap until the real dashboard style is chosen;
  see `grafana/README.md`. Docker parity still unproven (user-space dev
  stack, same as every phase above).
