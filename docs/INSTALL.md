# Installation Guide

Complete setup for **Apex Health** — from a bare server to a running
platform with the temporary Grafana web UI, demo data, backups and the
restore drill. Product background lives in the
[README](../README.md); every env var referenced here is defined in
[`MASTER_SPEC.md` §5](../MASTER_SPEC.md).

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Linux host (Debian/Ubuntu or Arch tested) | root not required for the bare-metal dev path |
| **Docker + Compose v2** *(Option A)* | or nothing but Python for Option B |
| **Python 3.12** + [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **PostgreSQL 16** with **TimescaleDB** and **pgvector** extensions | via the compose image `timescale/timescaledb-ha:pg16`, or a local install |
| **Redis 7+** | broker + one-time codes + dedup keys |
| ~2 GB RAM, ~5 GB disk for the stack | Grafana tarball adds ~500 MB |

Ports used by default: **8000** API · **3001** Grafana · **5433** Postgres ·
**6380** Redis. Option A's compose keeps Postgres/Redis
container-internal (only the API port is published); host-side commands
(alembic, pytest) reach the DB through `docker compose exec` or the
bare-metal recipe ports above.

## 2. Get the code

```bash
git clone https://github.com/MatteoSchiavi/Apex_Health.git apex-health
cd apex-health
cp .env.example .env
```

## 3. Environment variables

Fill `.env` (gitignored — never commit it). The complete reference:

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://hcc:…@host:port/hcc` |
| `REDIS_URL` | ✅ | `redis://host:port/0` |
| `SESSION_SECRET` | ✅ | session signing — generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | ✅ | Fernet key encrypting connector tokens + lab notes — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `OWNER_EMAIL` / `OWNER_PASSWORD` | ✅ | owner account bootstrapped at startup (§15) |
| `TELEGRAM_BOT_TOKEN` | for the bot | from @BotFather; bot is optional in dev |
| `GLM_API_KEY` | for the AI coach | chat + structured extraction (§9.1 tiers) |
| `OPENAI_API_KEY` | for voice + embeddings | Whisper STT (§10.2) and pinned `text-embedding-3-small` (§6.2) |
| `DAILY_TOKEN_BUDGET_USD` | optional | per-account daily AI budget, default `0.25` (§8.6) |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | for connect only | used once by the CLI, never stored (§16.7) |
| `TECHNOGYM_CLIENT_ID` / `TECHNOGYM_CLIENT_SECRET` | for connect only | from developer.technogym.com (§24) |
| `WEATHER_HOME_LAT` / `WEATHER_HOME_LON` | recommended | enables forecast cache + activity enrichment (unset/0 = off) |
| `WEATHER_FORECAST_DAYS` | optional | default `7` |
| `WEATHER_NUDGE_READINESS_THRESHOLD` | optional | default `70`; ≤ 0 disables the nudge |
| `LOW_FERRITIN_NG_ML` | optional | default `30` (§12) |
| `BACKUP_ENCRYPTION_KEY` | for backups | dedicated Fernet key — different from `ENCRYPTION_KEY` (§22.7) |
| `B2_APPLICATION_KEY_ID` / `B2_APPLICATION_KEY` / `B2_BUCKET` | for offsite | Backblaze B2 upload (§22.7) |
| `TRUST_PROXY_HEADERS` | for Funnel/proxy | `true` behind Tailscale Funnel / Caddy — adopts X-Forwarded-Proto/For from loopback peers only (§15) |

> **Note (dev keys):** any valid Fernet string works for
> `ENCRYPTION_KEY`/`BACKUP_ENCRYPTION_KEY` in dev. In production they are
> secrets — back them up: losing `ENCRYPTION_KEY` means losing connector
> tokens and lab notes; losing `BACKUP_ENCRYPTION_KEY` means losing every
> backup artifact.

---

## 4. Option A — Docker Compose (recommended for a server)

```bash
cp .env.example .env && $EDITOR .env
docker compose -f infra/docker-compose.yml up -d --build

docker compose -f infra/docker-compose.yml ps
curl http://localhost:8000/health          # → {"status":"ok"}
docker compose -f infra/docker-compose.yml logs -f api
```

Services: `db` (TimescaleDB-ha pg16 with shared_preload_libraries),
`redis`, `api` (uvicorn), `worker` (Celery worker **+ beat** — the beat
schedule lives inside the worker, §19), `bot` (Telegram long polling).

Then apply migrations (first boot only — the API also runs them
automatically on start in dev mode):

```bash
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
```

**Honest caveat:** the whole project was developed and verified on the
bare-metal path; the compose file mirrors it but **Docker parity is still
unproven** — treat the first `up --build` on your host as the acceptance
run (log output welcome as an issue/PR).

## 5. Option B — bare-metal / dev (no Docker)

Use this when you develop on the repo daily. Postgres and Redis may come
from your distro packages — they only need to serve the URLs in `.env`.

```bash
# 1. backend venv
cd backend && uv sync

# 2. services (distro Postgres 16 + TimescaleDB + pgvector, Redis 7+)
#    create db `hcc` with role `hcc`, then:
uv run alembic upgrade head            # → migration 0005 (gym_schedule_slots)

# 3. run the platform (4 terminals, or tmux)
uv run uvicorn app.main:app --port 8000                        # API
uv run celery -A app.tasks.celery_app worker --loglevel=INFO   # worker+beat
uv run python -m app.connectors.telegram.polling               # bot (optional)
grafana/run_grafana.sh                                         # UI (optional)
```

### 5a. User-space Postgres/Redis recipe (no root, no Docker)

The sandbox this project was built in has no root and no Docker, so the dev
stack runs extracted from Debian/PGDG packages. Two committed scripts
drive the whole path (both keep their downloads/cluster under `$HOME`,
overridable via `PG_ROOT`/`REDIS_ROOT`/`PGDATA` env vars):

```bash
bash scripts/rebuild_pg_redis.sh   # fetch + extract PG16+TimescaleDB+pgvector, Redis 8
bash scripts/start_dev_env.sh      # initdb (first run) + start both, idempotent
```

- **PostgreSQL 16** on **:5433**, `unix_socket_directories` pointed at a
  writable dir, `shared_preload_libraries = 'timescaledb'`;
- **Redis 8.x** on **:6380** (wire-compatible with the compose `redis:7` for
  everything this project uses);
- export `DATABASE_URL=postgresql+asyncpg://hcc@localhost:5433/hcc` and
  `REDIS_URL=redis://localhost:6380/0` for every backend command.

## 6. Temporary web UI (Grafana)

```bash
grafana/run_grafana.sh            # first run downloads the OSS tarball (~180 MB)
# → http://127.0.0.1:3001  (anonymous Viewer; admin login admin/apex-demo)
```

The script defaults its dist/runtime dirs to `/home/z/grafana-dist` and
`/home/z/grafana-runtime`; override both via `GRAFANA_DIST` / `GRAFANA_RUNTIME`
env vars. It connects to the DB on `localhost:5433` — override via
`PGHOST`/`PGPORT` if your Postgres lives elsewhere.

- Provisioned automatically: PostgreSQL datasource (uid `apex-pg`), the 8
  dashboards from `grafana/dashboards/`, Overview pinned as home, dark
  theme. The datasource connects as `grafana_ro`, a **SELECT-only** role the
  script creates in `grafana/sql/bootstrap.sql`.
- Dashboards are **generated code**:

  ```bash
  python3 grafana/tools/build_dashboards.py    # regenerate after schema changes
  python3 grafana/tools/validate_panels.py     # run every panel SQL against PG
  ```

- **Seed demo data** (synthetic, deterministic, wipes user data):

  ```bash
  cd backend
  PYTHONPATH=. .venv/bin/python tools/seed_demo_data.py --days 240
  # owner login afterwards: owner@apexhealth.dev / demo-owner-1234
  ```

> **Gotcha:** seed **before** starting Grafana, or restart it after seeding
> (`grafana/run_grafana.sh stop && grafana/run_grafana.sh start`). Grafana's
> Postgres pool caches prepared plans that go stale after the seeder's
> TRUNCATE — the symptom is every panel showing *No data* with
> `pq: could not open relation with OID …` in the Grafana log.

Full details: [`grafana/README.md`](../grafana/README.md).

## 7. Connecting real data sources (owner steps, §0/§16.7)

Automated tests only use recorded fixtures — connecting real accounts is
deliberately manual:

```bash
# Garmin — one-time login, tokens stored app-layer-encrypted
cd backend
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=... \
    uv run python -m tools.garmin_sync connect
uv run python -m tools.garmin_sync sync            # incremental now

# Technogym — OAuth2; register at developer.technogym.com first
TECHNOGYM_CLIENT_ID=... TECHNOGYM_CLIENT_SECRET=... \
    uv run python tools/technogym_connect.py start  # prints authorize URL
uv run python tools/technogym_connect.py complete <code> <state>

# Telegram — put TELEGRAM_BOT_TOKEN in .env, then /link in the chat,
# and finish with /confirm <code-from-server-log>
```

Weather needs no account — set `WEATHER_HOME_LAT`/`WEATHER_HOME_LON` and
the next 6-hourly beat tick fills the cache and starts enriching
activities.

## 8. Backups & the restore drill (§22.7)

```bash
# 1. dedicated key (NOT your ENCRYPTION_KEY)
export BACKUP_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# 2. nightly task is already on the beat schedule (02:00 UTC);
#    artifacts land in backend/backups/ (gitignored)

# 3. prove restores work — seeds markers, backs up, restores to a scratch DB,
#    compares all tables and decrypts the crypto-marked lab note
cd backend && uv run python tools/restore_drill.py
# → RESTORE DRILL PASSED — 48/48 tables match (first live run 46/46 at Phase 8,
#   re-run after Phase 11 at 47/47, again at the final verification pass with
#   gym_schedule_slots included)

# 4. real restore into a target DB
uv run python tools/restore_backup.py backups/hcc-YYYYMMDD-HHMMSS.daily.sql.gz.enc \
    --target-dsn postgresql://hcc:...@localhost:5433/hcc_restore
```

Optional offsite: set the three `B2_*` variables — upload failures never
block the local encrypted backup, they are reported and retried next night.

## 8a. Friends & invites (§15, Phase 9)

The API is multi-user: the owner invites, the friend onboards themselves.

```bash
BASE=https://<funnel-host>.ts.net          # or http://localhost:8000 in dev
CSRF="X-CSRF-Token: t"

# 1. OWNER logs in (cookie jar), mints an invite (7-day default expiry)
curl -c /tmp/owner.jar -X POST $BASE/auth/login -H "$CSRF" \
     -H 'Content-Type: application/json' \
     -d '{"email":"owner@...","password":"..."}'
CODE=$(curl -b /tmp/owner.jar -X POST $BASE/settings/invites -H "$CSRF" \
     -H 'Content-Type: application/json' -d '{}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["code"])')

# 2. Send the code to your friend over a channel you trust.
# 3. FRIEND redeems — one call creates the account AND their session:
curl -c /tmp/friend.jar -X POST $BASE/auth/invite/redeem -H "$CSRF" \
     -H 'Content-Type: application/json' \
     -d "{\"code\":\"$CODE\",\"name\":\"Dana\",\"email\":\"dana@…\",\"password\":\"…\"}"
# → 201 {"role":"friend","ai_access_tier":"cheap_only",...}

# list/revoke invites (owner):  GET / DELETE /settings/invites
# raise a friend's AI tier:     PATCH /settings/users/{id}/ai-tier
```

Friends see ONLY their own data everywhere (labs, gear, activities, plans,
alerts, chat): cross-user row IDs answer 404, owner-only settings answer
403. Isolation is asserted in `tests/test_multiuser_isolation.py`.
To expose `$BASE` beyond your tailnet, follow `infra/tailscale-funnel-setup.md`.

## 8b. Watch app "Apex Day" (Phase 10 v2)

The watch app shows what ONLY Apex knows — the gym schedule, active
supplements, open alerts and the journal streak. It deliberately does NOT
duplicate readiness/recovery/strain: Garmin renders those natively
(Training Readiness, Recovery Time, Body Battery).

### 8b-1. Set your gym schedule (the recurring weekly routine)

**From Telegram** (no REST client needed):

```
/gym                       — today's sessions
/gym week                  — the 7-day schedule
/gym list                  — recurring slots with ids
/gym set Mon 18:00 Push Day          — add a slot
/gym note <id> Bench 4x8 · Incline 3x10 — attach the exercises block
/gym rm <id>               — remove a slot
```

**From REST** (session cookie + CSRF header, like every mutating call):

```bash
curl -b /tmp/owner.jar -X POST $BASE/schedule -H "$CSRF" \
     -H 'Content-Type: application/json' \
     -d '{"weekday":0,"start_time":"18:00","title":"Push Day",
          "description":"Bench 4x8 · Incline DB 3x10 · OH Press 3x8"}'
# 201 {"id":1,"weekday":0,"start_time":"18:00","title":"Push Day",...}

curl -b /tmp/owner.jar $BASE/schedule            # list
curl -b /tmp/owner.jar -X PATCH $BASE/schedule/1 -H "$CSRF" \
     -d '{"start_time":"19:30"}'                 # edit / pause (active:false)
curl -b /tmp/owner.jar -X DELETE $BASE/schedule/1 -H "$CSRF"   # remove
```

`weekday` is 0=Mon .. 6=Sun. Confirmed/active AI training plans
(`planned_sessions`) override the recurring template on their specific
dates — the routine is the baseline, the plan refines individual days.

### 8b-2. Mint a device token

Each user (owner or friend) mints a token for THEIR wrist — the watch can
only ever see that user's schedule and data:

```bash
curl -b /tmp/owner.jar -X POST $BASE/watch/tokens -H "$CSRF" \
     -H 'Content-Type: application/json' -d '{"name":"fr965"}'
# {"id":1,"name":"fr965","token":"<ONE-TIME SECRET>",...}
```

Paste `$BASE` + the token into the watch app's settings (Connect IQ →
Apex Day → Settings); build/sideload from `connectiq/` — see its README.
Revoke any time with `DELETE /watch/tokens/{id}` (immediate) and list with
`GET /watch/tokens` (hashes only — the plaintext is shown exactly once).
On the next wrist refresh a revoked token wipes the cached data and the
app shows "Token invalid" instead of yesterday's plan.

### 8b-3. What the wrist renders

- **Glance** — today's session (title + time) or "Rest day", plus
  `supp N · alert N · streak Nd` counts.
- **Today** — gym sessions with the exercises block (recurring routine and
  `PLANNED SESSION` AI overrides), supplements, alerts, streak.
- **Week** — the 7-day schedule, today highlighted, plan overrides marked.
- **Alerts** — open alerts, severity-colored (ack in Telegram/web).

## 9. Running the tests

```bash
cd backend && uv sync
# point DATABASE_URL/REDIS_URL at a DEV database (tests create their own DBs)
uv run pytest -q          # 269 passed is the green baseline
```

CI (GitHub Actions) runs the same suite against
`timescale/timescaledb-ha:pg16` + `redis:7` services on every push.

## 10. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Grafana panels all "No data", log shows `could not open relation with OID …` | stale prepared plans after the demo seeder TRUNCATEd tables — restart Grafana (`grafana/run_grafana.sh stop && grafana/run_grafana.sh start`) |
| `UndefinedTable` / migration errors | run `uv run alembic upgrade head`; for a scorched-earth reset use `scripts/reset-dev.sh` |
| TimescaleDB error on restore | run inside `timescaledb_pre_restore()` / `timescaledb_post_restore()` — `tools/restore_backup.py` already does this |
| Bot silent | the bot is a separate long-polling process — check it is running and `TELEGRAM_BOT_TOKEN` is set; pairing requires `/link` then `/confirm <code>` from the server log |
| Voice drafts stuck "pending" | Whisper/STT runs on the Celery **worker** — worker must be up with `OPENAI_API_KEY` |
| `search_context` says unavailable | embeddings need `OPENAI_API_KEY`; the tool degrades honestly by design |
| 403 on API writes | send the `X-CSRF-Token` header (any value) with the session cookie (§22.3) |
| Account locked | 5 failed logins per email per 15 min trigger a temporary lock (§22.1) — wait it out |
| Redis version mismatch vs compose | dev used Redis 8.x, compose pins `redis:7` — wire-compatible for everything this project uses |
