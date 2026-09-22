# ⚡ Apex Health — Personal Health & Performance Control Center

![CI](https://github.com/MatteoSchiavi/Apex_Health/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-TimescaleDB_·_pgvector-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Celery_broker-DC382D?logo=redis&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-long_polling-26A5E4?logo=telegram&logoColor=white)
![Tests](https://img.shields.io/badge/tests-269_green-73BF69)

A self-hosted backend that unifies **Garmin biometrics**, **blood-donation
lab panels**, **subjective journaling via
Telegram voice notes**, **gear maintenance** and **weather data** — runs a
derived-metrics **feature engine** on top (readiness, recovery, strain,
load, ACWR, risk scores), and serves it all through a **Telegram bot with a
tiered, tool-using AI coach** that can read your data and *draft* plans for
your explicit confirmation.

Single source of truth for product decisions:
[`MASTER_SPEC.md`](./MASTER_SPEC.md) (§ references throughout this README
point there). Installation guide: **[`docs/INSTALL.md`](./docs/INSTALL.md)**.
Data currently surfaces via the REST API and the Telegram bot; the real
full web UI is the next work item (spec Appendix A).

---

## Why it exists

Wearable apps each own a piece of the picture and none of them know about
your gym machine sessions, your donations, your subjective state, or your
shoe mileage. Apex Health is the **single local source of truth**: every
upstream payload is stored **raw-first** before normalization (§3), every
derived number is **reproducible and versioned** (§6.4), every AI write
**stays a draft until a human confirms it** (§8.5), and every query layer is
shared between the bot, the agent tools and the reports — **one
implementation per read** (§8.2).

## Feature map

| Domain | What it does | Access points |
|---|---|---|
| **Ingestion** | Garmin (activities + streams, sleep, HRV, stress, biometrics) every 6 h; raw-first into `raw_ingest`, idempotent upserts, ±10 min **multi-source reconciliation** so the same workout from two sources never duplicates (§12). Technogym's API is **B2B-only** (owner-confirmed) — the connector stays dormant, nothing to connect to | Celery beat; owner CLIs |
| **Feature engine** | Nightly derived metrics: readiness / recovery / strain, 7d/28d acute-chronic load + ACWR, HRV deviation from rolling baseline, sleep architecture score, illness / injury risk, per-discipline FTP, aerobic decoupling, efficiency factor — with versioned blend weights and `data_completeness` honesty flags (§7, §17) | `daily_features`, bot, agent |
| **Medical & labs** | Blood panels with per-marker reference ranges, app-layer-**encrypted free-text notes** (Fernet), donation eligibility countdown, low-ferritin alert (§12) | `POST/GET /labs`, `/donate` |
| **Lifestyle** | Nutrition logs (kcal, macros, water, caffeine, alcohol), supplement protocols + per-dose **adherence tracking** (§13) | ingest API |
| **Gear** | Activities auto-inherit discipline defaults; nightly **recompute** (never increment) of km/h since service; `gear_service_due` alert once per threshold crossing; logging a service resets + resolves (§13) | `POST /gear/...`, `/gear` bot command |
| **Weather** | Keyless Open-Meteo forecast + archive; 6-hourly cache refresh; **every activity enriched** with the weather it happened in (`weather_snapshot`); proactive "good window tomorrow" nudge gated on readiness (§14) | `/forecast [days]`, `GET /weather/forecast` |
| **Telegram bot** | Long polling (no public port): `/link` pairing, **voice notes → Whisper STT → structured draft → ✅ Save / ✏️ Edit**, commands, alert push with severity icons (§10) | the primary daily interface |
| **AI coach** | Tool-using agent over a compact data snapshot: 11 tools, ≤ 8 loop iterations with best-partial fallback, full audit of every call, three-tier model routing, hard daily token budget (§8) | free text in the bot |
| **Semantic memory** | Journal entries + reports embedded (pinned `text-embedding-3-small`), pgvector cosine `search_context` scoped to the caller (§6.2) | agent tool |
| **Reports** | Daily summary **templated at zero LLM cost**; weekly + monthly on the powerful tier; all idempotent per period (§9.2) | `/report`, scheduled push |
| **Security** | Owner bootstrap, HttpOnly + SameSite session cookies, CSRF header on every write, login rate-limit + lockout, sliding expiry, all routes 401/403 except `/health` (§22) | — |
| **Ops & backups** | JSON structured logs, `sync_failure` escalation after 3 consecutive connector failures, nightly **encrypted-before-disk** pg_dump + retention + B2 offsite + a real, rerunnable **restore drill** (§21, §22.7) | `tools/restore_drill.py` |

## Architecture

```
                ┌─────────────────────────── data sources ───────────────────────────┐
                │   Garmin Connect                     Open-Meteo (keyless weather)  │
                │   (Technogym: B2B-only API, connector dormant — no feed)           │
                └──────┬──────────────────────────────────────┬──────────────────────┘
                       │ 6h beat                              │ 6h beat (:20)
                ┌──────▼──────────────────────────────────────▼──────────────────────┐
                │  connectors/  — raw-first into raw_ingest, then idempotent         │
                │  normalizers → activities (+streams), sleep, HRV, stress,          │
                │  biometrics; ±10 min multi-source reconciliation (§12)             │
                └──────┬─────────────────────────────────────────────────────────────┘
                       │
                ┌──────▼─────────────────────────────────────────────────────────────┐
                │  PostgreSQL 16 + TimescaleDB + pgvector                            │
                │  raw_ingest → normalized tables → nightly feature engine (§7)      │
                │  → daily_features / discipline_features → alerts, rollups          │
                └──────┬──────────────────────────┬──────────────────────────────────┘
                       │                          │
                ┌──────▼───────────┐      ┌───────▼──────────────────────────────────┐
                │  REST API (§18)  │      │  Celery worker + beat (§19)              │
                │  labs/gear/integ │      │  syncs · features · gear · reports ·     │
                │  /weather /auth  │      │  budget · backups · voice · alerts       │
                └──────┬───────────┘      └───────▼──────────────────────────────────┘
                       │                          │
                ┌──────▼────────────────────────────────────────────────────────────┐
                │  Telegram bot (long polling §10) — commands, voice drafts,        │
                │  alert push, free text → AI agent (tools §8.3 · loop §8.4 ·       │
                │  routing §9.2 · budget §8.6 · confirm-before-write §8.5)          │
                └──────┬─────────────────────────────────────────────────────────────┘
                       │ reads
                ┌──────▼─────────────────────────────────────────────────────────────┐
                │  shared query layer app/queries (§8.2 — one implementation/read)   │
                │  consumed by bot · agent tools · reports · (future web UI)         │
                └────────────────────────────────────────────────────────────────────┘
```

**Every write is idempotent** (upserts keyed on natural or `(source,
external_id)` keys — §17): re-running any sync, feature range or report
never double-counts. **Every AI write is a draft** until confirmed with an
inline button.

## The AI layer

The AI is deliberately **grounded, frugal and supervised**:

- **Grounded** — free text reaches the agent with a compact system block
  (profile, active feature weights, 14-day feature window, open alerts) and
  the §8.3 tool registry: `get_metric_trend`, `get_lab_trend`,
  `get_activity_summary`, `get_journal_entries`, `search_context`,
  `get_training_plan`, `get_donation_status`, `get_gear_status`, plus the
  write tools `propose_training_plan`, `propose_supplement_change`,
  `sync_plan_to_technogym`. Tools are thin wrappers over the same
  `app/queries` layer everything else uses — the model cannot invent data it
  cannot query.
- **Frugal** — a free-tier classification call tags each message *lookup* or
  *strategic* and routes to the cheap or powerful tier (§9.2); accounts with
  `ai_access_tier='cheap_only'` are hard-capped. Every call writes
  `token_usage` with a §9.1 rate-table cost estimate; a daily check (23:45
  UTC) fires an informational `budget_warning` alert over
  `DAILY_TOKEN_BUDGET_USD` (default $0.25). The daily report is a pure
  template — $0.00.
- **Supervised** — propose tools only ever **draft**: a training plan lands
  at `status='draft'`, a supplement change at `active=false`, and the bot
  attaches ✅/❌ buttons. Nothing is written for real until a human taps
  confirm (§8.5). The loop gives the model at most 8 iterations and returns
  its best partial answer instead of failing (§8.4); tool errors are fed
  back as results, never crashes. Every tool execution is audited to
  `agent_tool_calls` with latency, input and output.
- **Local-first posture** — the platform itself is self-hosted (your
  Postgres, your Redis, your bot process, your encrypted backups). The only
  external AI dependencies are the GLM API (chat + structured extraction)
  and OpenAI embeddings + Whisper STT; both are optional and degrade
  honestly: without keys, search returns a readable "unavailable" result and
  templated reports keep working at zero cost. Swapping the LLM client to a
  self-hosted endpoint is a config change, not a refactor — the client is
  one module (`app/core/llm.py`) behind the routing layer.

## Quickstart (Docker)

```bash
cp .env.example .env          # fill in values — see docs/INSTALL.md
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
curl http://localhost:8000/health
```

That brings up `db · redis · api · worker(+beat)` — the API on **:8000**,
nightly encrypted backups into `./backups/` on the host, everything
`restart: unless-stopped` for headless servers. The Telegram bot joins via
`--profile telegram` once `TELEGRAM_BOT_TOKEN` is set. Migrating to a
homeserver over SSH:
[`docs/INSTALL.md` §9](./docs/INSTALL.md#9-migrating-to-a-homeserver-over-ssh-docker).

Full walkthrough (env-var reference, Telegram/LLM keys, real Garmin
connection, backups, restore drill, tests):
**[`docs/INSTALL.md`](./docs/INSTALL.md)**.

## Demo data

Optional deterministic demo data for a populated API/bot experience
(synthetic ~240-day story across every table):

```bash
docker compose -f infra/docker-compose.yml exec api \
    env PYTHONPATH=/app python tools/seed_demo_data.py --days 240
# owner login afterwards: owner@apexhealth.dev / demo-owner-1234
# (bare-metal: cd backend && PYTHONPATH=. .venv/bin/python tools/seed_demo_data.py --days 240)
```

## Implementation notes by phase

The sections below are the surviving engineering journal of the build —
each phase's judgment calls are documented where the code lives.

### Garmin connector (Phase 1)

Sync runs every 6 hours via Celery beat (§19): activities (+ streams),
sleep, HRV, stress, and daily biometrics. Every payload is stored raw before
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

### Feature engine (Phase 2)

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
upserts by primary key make it a safe idempotent backfill (§6.4) via
`app.features.engine.compute_user_range(session, user, start, end)`.

### Telegram bot (Phase 3)

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
  — deliberately no LLM, §9.2), `/gear` (usage vs service intervals),
  `/plan` (today's confirmed sessions), `/forecast [days]`. Reads go
  through the shared query layer `app/queries` (§8.2).
- **Free text:** routed to `app/agent/entrypoint.py` — the full tool-using
  agent (Phase 5) inside the §6.4 30-minute session boundary.
- **Alert push (§21):** alert-creating code paths commit the row then call
  `push_alert` — delivered to the linked chat with severity icons.

Running live needs `TELEGRAM_BOT_TOKEN` (§5); the voice pipeline additionally
needs `OPENAI_API_KEY` (Whisper) and `GLM_API_KEY` on the worker, and the
Celery worker must be running for voice drafts:

```bash
docker compose -f infra/docker-compose.yml --profile telegram up -d
# or without Docker:
cd backend && uv run python -m app.connectors.telegram.polling
```

Automated tests and demos never touch the live Bot API, LLM, or STT — they run
against recorded fixtures only (§0/§20).

### Medical, lifestyle & gear (Phase 4)

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
  `gear.accumulate_all` task (beat :15, inside the 03:00-03:59 local
  window right after the feature engine, §19) RECOMPUTES
  `hours_since_service`/`km_since_service` from linked activities — a
  recompute, never an increment, so re-runs never double-count (§17).
  Crossing a configured interval fires ONE `gear_service_due` alert per gear
  and pushes it; logging a service (`POST /gear/{id}/service`, §18) resets
  the counters and resolves the open alert.
- **Shared reads (§8.2):** `get_lab_trend`, `get_donation_status`,
  `get_gear_status` run on the Phase 4 ORM models — the same functions
  the bot, the agent tools, and report tasks call.

### Agent harness & AI layer (Phase 5)

- **Tool loop (§8.4):** free text runs the full harness — the model sees
  a cached system block (profile, active feature weights, a 14-day feature
  window, open alerts) plus the §8.3 tool registry, and can call tools for
  up to 8 iterations before returning the best partial answer. Tool errors
  come back as results, never as crashes. Every tool execution is audited to
  `agent_tool_calls` (with `session_id`; scheduled callers log NULL).
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
  `DAILY_TOKEN_BUDGET_USD`.
- **Reports (§19, §9.2):** the daily summary is TEMPLATED — zero LLM cost,
  `model_used` NULL (§6.4) — persisted at :45 inside each user's 03:00-03:59
  local window. Weekly (Monday 06:00 local) and monthly (1st 06:00 local)
  reports are always POWERFUL tier over a §8.2 data pack, audited with
  `session_id=NULL`, and pushed to linked chats. All report rows upsert
  idempotently per period.
- **Semantic search (§6.2, §8.3):** journal entries (on save) and report
  content (on generation) are embedded with the PINNED
  `text-embedding-3-small`; `search_context` runs pgvector cosine over them,
  scoped to the caller via the source rows. Without `OPENAI_API_KEY` the
  tool degrades to a readable "unavailable" result.

### Technogym connector (Phase 6) — RETIRED

> **Owner decision (post-build):** the Technogym API turned out to be
> **B2B-only** — personal accounts cannot register an OAuth client, so this
> connector can never be connected. The code stays (dormant, tested against
> fixtures, degrades honestly when unconfigured); no time is invested in it.
> If a future source for machine workouts is wanted, §12 reconciliation
> accepts a second activity source unchanged.

- **Stage 11a (built regardless, §11):** OAuth2 authorization-code flow per
  the enduser-to-enduser sample on developer.technogym.com — authorize URL
  with a single-use Redis-backed `state`, code exchange, single-flight token
  refresh on sync (rotated tokens are re-encrypted back into
  `integrations.credentials_encrypted`). Workout pulls go raw-first into
  `raw_ingest`, then the normalizer upserts `activities` keyed on
  `(source='technogym', external_id)` — full history backfill on first sync,
  ±10 min-window incremental afterwards, every remote call paced like
  Garmin (§19).
- **Multi-source reconciliation (§12, Phase 6 AC):** when an ingested
  session lands within ±10 minutes of an existing row for the same user and
  the SAME seeded discipline, no duplicate `activities` row is created — the
  new source is attached via `activity_source_links` and fields merge per
  the richer-source-per-field rule (Garmin for HR/GPS-derived, Technogym for
  machine power), and a populated field is NEVER overwritten with NULL.
  The rule runs symmetrically — Garmin arrivals reconcile into Technogym
  rows too.
- **Manual connection (§0/§16.7):** the owner connects the real account —
  `POST /settings/integrations/technogym/authorize` then open the returned
  URL, or the CLI:

  ```bash
  cd backend
  TECHNOGYM_CLIENT_ID=... TECHNOGYM_CLIENT_SECRET=... \
      uv run python tools/technogym_connect.py start   # prints URL + state
  uv run python tools/technogym_connect.py complete <code> <state>
  uv run python tools/technogym_connect.py sync [--backfill]
  ```
- **Stage 11b (contingent, §24):** `sync_plan_to_technogym` still validates
  the confirmed-plan precondition and returns the documented fallback until
  the owner registers and confirms what the individual access tier grants.
  The fallback delivery path is real: `/plan today` in Telegram shows the
  day's confirmed-plan sessions (drafts never show) with the
  follow-manually note. Raw-first design means any live payload shape drift
  is a parser fix, never data loss (§3).
- **Schedule (§19):** `technogym.sync_all` runs every 6 hours, staggered at
  :10 off the Garmin :00 tick; §21 escalation is a shared helper both
  connectors use.

### Weather module (Phase 7)

- **Source (§2, §14):** Open-Meteo — free, no API key. Forecast API (future
  days plus up to 92 past days) and archive API (full history). Raw-first
  per §3/§17 into `raw_ingest` before normalization.
- **Forecast cache (§19 AC):** `weather.refresh_all` every 6 hours (beat
  :20) upserts `forecast_cache` on its `UNIQUE (lat, lon, date)` key — keyed
  on the coordinates we asked for, not the grid-snapped echo values, which
  would quietly multiply near-duplicate rows.
- **`weather_snapshot` on ingestion (§14 AC):** the same beat enriches every
  activity whose `weather_snapshot` is still NULL — coordinates from the
  first positioned stream sample, falling back to home. Recent dates ride
  the forecast API's past window; older dates go to the archive API.
  NULL-only writes; the column is `none_as_null` so "not weathered yet"
  means SQL NULL for every writer.
- **§14 nudge:** once per user per local day (07:00 local), when TOMORROW's
  cached forecast is a good training window (max temp 5–28 °C, rain ≤ 40 %,
  wind ≤ 35 km/h) AND latest readiness ≥
  `WEATHER_NUDGE_READINESS_THRESHOLD` (default 70), the linked chat gets one
  proactive message. Redis SETNX dedup.
- **Configuration:** `WEATHER_HOME_LAT` / `WEATHER_HOME_LON` (unset/0
  disables refresh with a logged note), `WEATHER_FORECAST_DAYS` (default 7),
  `WEATHER_NUDGE_READINESS_THRESHOLD` (≤ 0 disables the nudge). Weather has
  no `integrations` row — keyless, nothing to escalate (§21); failures are
  logged and retried next tick.

### Backups & disaster recovery (Phase 8)

§22.7: nightly `pg_dump` at 02:00 UTC, encrypted with a key **dedicated to
backups** (`BACKUP_ENCRYPTION_KEY` — independent from the app's
`ENCRYPTION_KEY` so one leaked key cannot open both), retained as 14 daily +
6 monthly archives (first-of-month snapshots are the monthly pool — judgment
call documented in `app/core/backups.py`).

- **Artifact format:** `hcc-YYYYMMDD-HHMMSS.{daily|monthly}.sql.gz.enc` —
  Fernet(gzip(plain-SQL pg_dump)). Encrypted *before* it touches disk; a
  plaintext dump of health data is never written anywhere, ever. Key unset ⇒
  honest nightly skip (never an unencrypted fallback).
- **Offsite:** pushed to Backblaze B2 when `B2_APPLICATION_KEY_ID` /
  `B2_APPLICATION_KEY` / `B2_BUCKET` are set (native v2 API over httpx). A
  failed upload never fails the local backup — reported honestly, retried
  next night.
- **Restore:** `backend/tools/restore_backup.py <artifact> --target-dsn …`
  decrypts, gunzips and pipes SQL into psql with `ON_ERROR_STOP` — stdin
  only, no plaintext temp file. TimescaleDB hypertables restore under the
  documented `timescaledb_pre_restore()` / `timescaledb_post_restore()`
  wrapper.
- **The restore drill (§22.7 AC):** `backend/tools/restore_drill.py` seeds
  marker data through the ORM, snapshots every public table, runs the real
  backup pipeline, restores into a scratch database and compares
  table-by-table — including `alembic_version` and proving the encrypted lab
  note still decrypts with the *app* key. First live run: **46/46 tables
  matched**. Rerun it on the real host after Docker parity is proven:

  ```bash
  BACKUP_ENCRYPTION_KEY=<key> uv run python tools/restore_drill.py
  ```

  `backups/` is gitignored — artifacts of real health data never enter git.

### Multi-user & remote access (Phase 9)

§15's deferral ("actually inviting and onboarding friends") ends here.

- **Invite flow (§18 Settings):** the owner mints one-shot codes with
  `POST /settings/invites` (128-bit urlsafe capability tokens, default 7-day
  expiry, listed with redemption state, unused ones revocable). The code is
  shown once and works exactly once: redemption claims the row under
  `SELECT ... FOR UPDATE`, so two people racing the same code cannot both
  get an account — the loser sees a uniform rejection with no oracle for
  *why* (unknown / used / expired are indistinguishable from outside).
- **Redemption = onboarding:** `POST /auth/invite/redeem` turns a live code
  into a `role=friend` account (`ai_access_tier=cheap_only`, share off —
  §15 defaults) *and* a session in one transaction; the friend picks their
  own email and password. Email-taken is answered 409 *without* consuming
  the code, so an invite survives a typo'd recipient.
- **Owner-only surface:** `require_owner` gate (403, honest) on
  `/settings/invites*` and `/settings/users/{id}/ai-tier` (§18). Judgment
  call (documented in `app/api/settings.py`): `/settings/integrations`
  stays per-user — under friend onboarding every friend connects their own
  sources and the whole data model is `user_id`-scoped.
- **Data isolation — the AC:** "a friend redeems an invite, logs in, sees
  only their own data." Asserted in both directions across labs / gear /
  settings in `tests/test_multiuser_isolation.py`, including direct
  addressing of the other user's row IDs (404 — existence denied, same
  convention the API always used) and per-account session independence.
  `backend/tools/demo_phase9.py` reproduces the full flow live.
- **Tailscale Funnel (§15):** `TRUST_PROXY_HEADERS=true` + a
  loopback-only `ProxyHeadersMiddleware` makes the app Funnel-aware (the
  local tailscaled proxy is the only peer allowed to vouch for
  `X-Forwarded-Proto/For`); `infra/tailscale-funnel-setup.md` is the
  §4-named setup artifact (why Funnel, serve/funnel commands, what is
  already correct — Secure/HttpOnly/Lax cookies, CSRF header, no CORS by
  design, email-keyed rate limiting, revocable server-side sessions — and
  the onboarding walkthrough). The AC was demonstrated end-to-end through a
  Funnel-shaped local HTTPS terminator: redeem + login *over the Funnel
  URL* → only own rows visible.

### Connect IQ watch app — "Apex Day" (Phase 10 v2, rethought)

The original Phase 10 put readiness / recovery / strain on the wrist — the
wrong idea, because every supported device already renders those natively
(Training Readiness, Recovery Time, Body Battery / Training Load). Phase 10
v2 rethought the app around the actual need: the watch is where Apex shows
what **only Apex knows** and Garmin cannot:

- **Gym schedule** — the recurring weekly routine (`gym_schedule_slots`,
  migration 0005: weekday + start time + title + exercises block). Confirmed
  AI training plans (`planned_sessions`) **override** the recurring template
  on their specific dates — the routine is the baseline, the plan refines
  individual days. Managed from Telegram (`/gym`, `/gym week`, `/gym set Mon
  18:00 Push Day`, `/gym note <id> Bench 4x8 · Incline 3x10`, `/gym list`,
  `/gym rm`) or REST (`GET/POST /schedule`, `PATCH/DELETE /schedule/{id}`).
- **Supplements due today** — active protocols with dose.
- **Apex alerts** — open, severity-colored (ferritin trends, sync failures,
  gear service due); acking stays in Telegram/web.
- **Journal streak** — consecutive journal days (ends today, or yesterday
  when today's entry hasn't happened yet).

Surfaces: the **glance** strip shows today's session (title + time) or
"Rest day" plus the supplement/alert/streak counts; opening the app gives a
menu — **Today** (sessions with wrapped exercises, supplements, alerts,
streak), **Week** (7-day schedule, today highlighted, plan overrides marked),
**Alerts** (severity-colored list). A 30-minute background temporal event
refreshes the day cache; views paint from `Application.Storage` so the wrist
never blocks on the radio.

- **Backend:** migration 0004 `device_tokens` (peppered-hash, soft-revocable,
  per-user — unchanged) plus the new v2 Bearer-authed endpoints `GET
  /watch/day` and `GET /watch/week` (owner-local dates, §17); `GET
  /watch/today` remains for the scores. Isolation stays structural: a
  friend's watch token resolves only the friend's schedule (tested both
  directions).
- **Device side:** on 401 the app deletes its cached data and shows "Token
  invalid" — a revoked token never leaves yesterday's plan posing as today.
- **Honest limit:** the Monkey C source is written against the CIQ 4.0 API
  surface but **not compiled here** (the SDK isn't fetchable in this
  environment) — `connectiq/README.md` has the exact `monkeyc` build +
  sideload steps for the owner's machine.

### CI & drill re-run (Phase 11)

- **CI (§20):** `.github/workflows/tests.yml` runs the full pytest suite on
  every push — services `timescale/timescaledb-ha:pg16` (carries both
  extensions migration 0001 needs) and `redis:7`; conftest rebuilds the
  Alembic chain per session, so CI sees the same schema as local.
- **Hardening re-verified** in the fresh environment: the §20/§21/§22 audit
  suites (sliding-session expiry, served-route auth matrix, JSON logging,
  alert/log channel separation) all green — 269 tests total.
- **Restore drill re-run live** on this deployment: **48/48 tables match**
  (`device_tokens` + `gym_schedule_slots` included), `alembic_version=0005`,
  the encrypted lab note round-trips with the app key. The drill is
  committed and rerunnable — the owner should run it once more on the real
  host after Docker parity.
- **Final verification pass** (end of build round): every phase's evidence
  re-audited against the spec; deep math audit of the feature engine found
  and fixed three latent issues (best-window power search anchors, the
  §7 journal component of the illness score was still dormant despite the
  seeded weight, `iron_status_flag` was never populated despite Phase 4 —
  all three now wired, golden-tested, and covered by 12 new regression
  tests); served auth surface re-probed live (401s + CSRF + owner flow).
- **Remaining connectors:** Garmin, weather and Telegram/STT/embeddings are
  built and live; **Technogym is a confirmed dead end** (B2B-only API —
  connector dormant); Strava /
  MyFitnessPal are deliberately unspecced (§1 substitutes them via the
  feature engine).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold: schema + seeds, `/health`, owner auth + security middleware, Celery, CI | ✅ |
| 1 | Garmin connector (fixtures; real connect = owner CLI) | ✅ |
| 2 | Feature engine + golden-dataset regression suite | ✅ |
| 3 | Telegram bot: linking, voice drafts, commands, alert push | ✅ |
| 4 | Medical / lifestyle / gear + low-ferritin & gear alerts | ✅ |
| 5 | Agent harness: 11 tools, loop + audit, tier routing, budget, reports, pgvector search | ✅ |
| 6 | Technogym OAuth2 connector + §12 reconciliation + `/plan today` | ✅ |
| 7 | Weather: cache, activity enrichment, `/forecast`, §14 nudge | ✅ |
| 8 | Hardening audit, encrypted backups + B2 offsite + **restore drill 46/46** | ✅ |
| 9 | Multi-user: invite flow, friend accounts, **data-isolation proof**, Tailscale Funnel readiness + setup guide | ✅ |
| 10 | Connect IQ watch app **v2 "Apex Day"** (rethought): gym schedule + supplements + alerts + streak on the wrist, NOT native scores; `/watch/day`, `/watch/week`, `/schedule` CRUD, `/gym` bot, recurring `gym_schedule_slots` + plan-override resolution | ✅ source+API, demoed live; `.prg` build needs the owner's SDK + watch |
| 11 | CI on every push (§20), hardening re-verified, **restore drill re-run live: 48/48** | ✅ |
| — | Temporary Grafana web UI (8 dashboards / 147 panels) | ❌ removed by owner decision — history keeps it; the real full UI (Appendix A) is next |
| — | Real dashboard style (Appendix A) | ⏳ deferred by owner |

Out of scope this build round (per the spec): the real web dashboard
(Appendix A). Friend onboarding is now IN (Phase 9). Strava / MyFitnessPal
have no integration sections anywhere in the spec — §1 explicitly
substitutes them with the feature engine ("without needing those
subscriptions"); treated as deliberately out of scope rather than invented
spec (§0).

**Known honest limitation:** everything above was developed and verified on
a user-space dev stack (PostgreSQL 16 + TimescaleDB + pgvector on :5433,
Redis 8 on :6380). **Docker parity is still unproven** until
`docker compose -f infra/docker-compose.yml up -d --build` runs on the
owner's host — same for the real-account connections, which are manual owner
steps by design (§0/§16.7). The compose deployment is feature-complete
(embedded beat, pg_dump 16 in the images, host-mounted backup dir, restart
policies) and §9 of the INSTALL guide walks the full SSH migration.

## Repo layout

```
backend/
  app/
    api/          REST routers (§18) — health, auth, labs, gear, integrations, weather
    agent/        entrypoint, tool registry (§8.3), loop (§8.4), routing (§9.2)
    auth/         sessions, owner bootstrap, login rate limiting
    connectors/   garmin · technogym · telegram · weather · b2 · reconciliation · escalation
    core/         config, db/redis, security (Fernet), llm client, logging, backups
    features/     derived-metrics engine (§7): load, baselines, scores, discipline math
    gear/         service accumulation + alerts (§13)
    medical/      labs + lifestyle ingestion (§12/§13)
    models/       ORM models (§6 schema)
    queries/      shared read layer (§8.2) — bot, agent tools, reports, dashboards
    reports/      templated daily + LLM weekly/monthly (§9.2)
    schemas/      Pydantic boundary schemas
    tasks/        Celery app + beat schedule (§19)
  alembic/        migrations
  tests/          39 test files / 269 tests — fixtures only, no live APIs (§20)
  tools/          owner CLIs: garmin_sync, technogym_connect, seed_demo_data,
                  restore_backup, restore_drill, demo_phase9 (AC demo)
connectiq/        Garmin watch app "Apex Day" (Monkey C): gym schedule,
                  supplements, alerts, journal streak — talks to /watch/day
                  and /watch/week over the Funnel
infra/            docker-compose.yml (db · redis · api · worker+beat · bot)
                  + tailscale-funnel-setup.md (§15 remote access)
scripts/          reset-dev.sh · start_dev_env.sh · rebuild_pg_redis.sh
                  (user-space, no-Docker/no-root dev stack helpers)
.github/workflows/ tests.yml — full pytest on every push (§20)
docs/             INSTALL.md — full installation guide
```

## Testing

```bash
cd backend
uv sync
uv run alembic upgrade head        # dev DB must be reachable (see .env)
uv run pytest -q                   # 269 tests, fixtures only — no live APIs
```

The suite covers: golden-dataset feature math (incl. EU DST day), connector
normalizers on recorded fixtures, reconciliation, agent loop + tool audit,
tier routing fail-closed paths, budget alerts, session sliding expiry, the
served route-auth matrix, JSON log shape, backup pipeline (fake pg_dump —
no real binary in CI) and the restore drill's crypto round-trip.

## Reset dev state

```bash
scripts/reset-dev.sh           # -f to skip the confirmation prompt
```

## Auth & API notes

- Owner account is bootstrapped at startup from `OWNER_EMAIL`/`OWNER_PASSWORD` (§15).
- `POST /auth/login` returns a `Secure`, `HttpOnly`, `SameSite=Lax` session cookie (§22.2).
- Every state-changing request must send `X-CSRF-Token: <any-value>` (§22.3).
- Five failed logins per email per 15 minutes lock the account temporarily (§22.1).
- `GET /health` is the only public route (§17).
