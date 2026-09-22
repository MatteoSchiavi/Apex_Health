# Installation Guide

Complete setup for **Apex Health** — from a bare server to a running
platform with demo data, backups and the restore drill. Data surfaces
through the REST API and the Telegram bot; the real full web UI is the
next work item (spec Appendix A). Product background lives in the
[README](../README.md); every env var referenced here is defined in
[`MASTER_SPEC.md` §5](../MASTER_SPEC.md).

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Linux host (Debian/Ubuntu or Arch tested) — or **Windows 10/11 via Docker Desktop** (§4a) | root not required for the bare-metal dev path |
| **Docker + Compose v2** *(Option A)* | or nothing but Python for Option B |
| **Python 3.12** + [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **PostgreSQL 16** with **TimescaleDB** and **pgvector** extensions | via the compose image `timescale/timescaledb-ha:pg16`, or a local install |
| **Redis 7+** | broker + one-time codes + dedup keys |
| ~2 GB RAM, ~5 GB disk for the stack | bare-metal dev needs more for the source-built Postgres |

Ports used by default: **8000** API · **5433** Postgres · **6380** Redis.
Option A's compose keeps Postgres/Redis
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
`redis`, `api` (uvicorn), `worker` (Celery worker **+ embedded beat** — the
§19 schedule runs inside the worker process) — plus `bot` (Telegram long
polling), which lives behind the `telegram` profile: start it once
`TELEGRAM_BOT_TOKEN` is set (`--profile telegram up -d`). Every service
carries `restart: unless-stopped`, so a server reboot brings the stack
back with the Docker daemon.

Then apply migrations (first boot — the API does **not** auto-migrate;
owner bootstrap happens on startup):

```bash
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
```

Nightly backup artifacts land on the host in `./backups/` (bind-mounted
into api + worker — containers stay disposable), and the api/worker
images carry `pg_dump`/`psql` 16 so the §22.7 backup task and the restore
tooling work unmodified.

**Honest caveat:** the whole project was developed and verified on the
bare-metal path; the compose file mirrors it but **Docker parity is still
unproven on your host** — treat the first `up --build` as the acceptance
run (log output welcome as an issue/PR). The full SSH-migration
walkthrough is §9.

### 4a. Windows notes (Docker Desktop)

Windows runs the identical stack — everything is a Linux container — so
what you verify here is exactly what later lands on the Linux server.

1. **Install once:**
   - **Docker Desktop for Windows** with the **WSL 2** backend
     (`wsl --install` first on a fresh machine, reboot, then install Docker
     Desktop and leave "Use WSL 2 based engine" enabled).
   - **Git for Windows** (default options are fine — see `.gitattributes`
     note below).
2. **Clone somewhere local, not cloud-synced:**
   `C:\Users\<you>\apex-health` is ideal. **Avoid OneDrive/Dropbox folders**
   (file locks interfere with bind mounts). Docker Desktop shares your user
   profile by default, so no share configuration is needed.
   ```powershell
   git clone https://github.com/MatteoSchiavi/Apex_Health.git ~/apex-health
   cd ~/apex-health
   ```
3. **Line endings are handled:** the repo pins `.gitattributes` to
   `eol=lf`, which overrides Git-for-Windows' `core.autocrlf` — every file
   checks out with LF endings, so the Dockerfile's line-continuations and
   the POSIX scripts survive the clone intact.
4. **Create `.env` without Python:**
   ```powershell
   Copy-Item .env.example .env
   # three fresh secrets — paste one per line into .env:
   -join ((1..2) | % { [guid]::NewGuid().ToString('N') })
   ```
   Edit `.env` in VS Code (or any editor saving UTF-8 **without** BOM —
   plain Notepad's default is fine). Fill `OWNER_EMAIL`/`OWNER_PASSWORD`
   and the three secrets; leave `DATABASE_URL`/`REDIS_URL` empty.
5. **Run the same commands in PowerShell** — forward slashes work as-is:
   ```powershell
   docker compose -f infra/docker-compose.yml up -d --build
   docker compose -f infra/docker-compose.yml exec api alembic upgrade head
   curl.exe http://localhost:8000/health      # → {"status":"ok"}
   ```
   Use **`curl.exe`**, not `curl` — in PowerShell `curl` is an alias for
   `Invoke-WebRequest` and the cookie-jar examples below would fail.
   The login smoke test from §9.3, Windows form:
   ```powershell
   curl.exe -c cookies.txt -X POST http://localhost:8000/auth/login `
        -H "Content-Type: application/json" `
        -d '{"email":"<OWNER_EMAIL>","password":"<OWNER_PASSWORD>"}'
   curl.exe -b cookies.txt http://localhost:8000/labs
   ```
6. **Run the test suite on Windows (optional):** the images ship without
   dev dependencies, but the api container has `uv` and the full source —
   pull dev deps and run inside the container (tests create and drop their
   own throwaway databases):
   ```powershell
   docker compose -f infra/docker-compose.yml exec api sh -c "uv sync --frozen && uv run pytest -q"
   ```
   This mutates only the disposable container's venv — `up -d` recreates
   it clean. If it gives you trouble, rely on CI (the same 269 tests run
   on every push) plus the functional checks above.
7. **Migrating to the Linux server afterwards:** §9 as-is — the compose
   stack is identical. Bring your `.env` (secrets decrypt your connector
   tokens and lab notes — a fresh install with new keys can NOT read old
   data) and, if you produced any, the `backups/` artifacts. Clone the
   repo fresh on the server and copy `.env` over — do not rsync
   Windows-side node/venv artifacts.

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

## 6. Demo data

Optional synthetic demo data (deterministic, wipes user data) — useful to
exercise every API/bot surface before your real connectors are live:

```bash
cd backend
PYTHONPATH=. .venv/bin/python tools/seed_demo_data.py --days 240
# owner login afterwards: owner@apexhealth.dev / demo-owner-1234
```

Docker form: `docker compose -f infra/docker-compose.yml exec api env
PYTHONPATH=/app python tools/seed_demo_data.py --days 240`.

## 7. Connecting real data sources (owner steps, §0/§16.7)

Automated tests only use recorded fixtures — connecting real accounts is
deliberately manual: putting `GARMIN_EMAIL`/`GARMIN_PASSWORD` in `.env`
alone does **nothing** (the sync tasks only poll accounts whose tokens are
already stored). The one-time connect consumes them:

```bash
# Garmin — one-time login, tokens stored app-layer-encrypted
cd backend
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=... \
    uv run python -m tools.garmin_sync connect
uv run python -m tools.garmin_sync sync            # incremental now
uv run python -m tools.garmin_sync status          # counts + last_synced_at
```

Docker form (credentials come from `.env` via `env_file`):

```bash
docker compose -f infra/docker-compose.yml exec api \
    env PYTHONPATH=/app python tools/garmin_sync.py connect
# verify the backfill landed:
docker compose -f infra/docker-compose.yml exec api \
    env PYTHONPATH=/app python tools/garmin_sync.py status
```

`connect` performs the FULL §6.3 backfill — every paginated activity in
the account's history, plus wellness (sleep/biometrics) walked backwards
day by day until a sustained 10-day empty gap, i.e. 3–6 months is normal
and multi-year histories are pulled too. It is paced (§19: unofficial
client, ban-safe speed), so a large history takes a while — watch
`status` counts climb or re-run `sync --backfill` later to re-walk.

Scores (readiness/recovery/strain) are computed nightly at 03:00
user-local for the PRIOR day. To score the freshly backfilled history
immediately instead of waiting, run the §6.4 correction task over the
synced range (user 1 = owner; adjust user_id and dates):

```bash
docker compose -f infra/docker-compose.yml exec worker \
    celery -A app.tasks.celery_app call features.recompute_range \
    --args '[1, "2026-03-01", "2026-09-14"]'
```

After it reports ok, the Overview/Recovery dashboards have scores for the
whole range.

```bash
# Technogym — B2B-ONLY (owner-confirmed dead end): personal accounts cannot
# register an OAuth client; the connector remains dormant. Leave the
# TECHNOGYM_* vars unset.

# Telegram — put TELEGRAM_BOT_TOKEN in .env, then /link in the chat,
# and finish with /confirm <code-from-server-log>
```

Weather needs no account — set `WEATHER_HOME_LAT`/`WEATHER_HOME_LON` and
the next 6-hourly beat tick fills the cache and starts enriching
activities.

### 7b. Whoop (official Developer API v2) — a primary device

Whoop is a **first-class alternative to Garmin** (owner decision): recovery,
sleep and workouts land in the exact same canonical tables the Garmin
connector writes, with a strict annotation law (HRV in ms as
`overnight_avg`, sleep stages in **seconds**, Whoop Recovery % and Strain
0-21 stored in `source_metrics` — never merged into Garmin-comparable
columns). Whoop has no steps/body-battery; those fields are simply never
touched.

One-time app registration (manual — you own the Whoop developer account):

1. Sign in at `developer.whoop.com` → **Create an app**.
2. Data access: pick **USER** (not partner). Request the read scopes
   `read:profile`, `read:body_measurement`, `read:cycles`, `read:recovery`,
   `read:sleep`, `read:workout` **plus `offline`** (that last one is what
   makes Whoop hand out a refresh token).
3. Redirect URI — copy exactly what goes into `.env`:
   `http://localhost:8000/integrations/whoop/callback`
   (behind the funnel/domain instead: `https://<your-domain>/integrations/whoop/callback`
   — the value in `.env` and the value registered at Whoop must match
   character for character).
4. Put `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` / `WHOOP_REDIRECT_URI`
   into `.env`, then restart the api container.

Connect the account (each user does this themselves; the flow stores tokens
app-layer-encrypted and binds via a single-use `state`):

```bash
# 1. logged-in session with CSRF header (see §8a for the cookie jar pattern)
curl -sk -c /tmp/owner.jar -X POST https://localhost:8000/settings/integrations/whoop/authorize \
    -H "X-CSRF-Token: x" -b /tmp/owner.jar
# → {"authorize_url": "https://api.prod.whoop.com/oauth/oauth2/auth?..."}
# 2. open authorize_url in a browser, log into Whoop, approve — Whoop
#    redirects to the callback URL and the server stores the tokens.
# 3. verify:
curl -sk -b /tmp/owner.jar https://localhost:8000/settings/integrations | python3 -m json.tool
```

The beat already syncs every 6 hours (`whoop.sync_all` at :05 — rotated
refresh tokens are persisted automatically). First sync is a full backfill
back to 2012-or-origin; sleep/recovery/cycles/workouts all paginate via the
official API — no rate-limit gymnastics needed.

### 7c. Strava (official REST API v3) — GPS companion source

Whoop has no GPS/distance and no public feed; Strava supplies rides, runs
and their distance/elevation. Same one-time registration:

1. `strava.com/settings/api` → **Create & Manage Your App**.
2. Authorization Callback Domain: `localhost` (or your domain without
   scheme); the redirect URI in `.env` must match the registered domain.
3. `.env`: `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`,
   `STRAVA_REDIRECT_URI=http://localhost:8000/integrations/strava/callback`.

Connect: `POST /settings/integrations/strava/authorize` → open the URL →
approve → done. Beat syncs every 6 hours at :07 (rate-limit-aware pacing).
Strava's `relative_effort` is **not** comparable to Garmin's training load
and stays in `source_metrics` — the feature engine never mixes them.

### 7d. CSV import (Apple Health / Google Fit / generic)

For histories no API covers (or when a friend just has an export file):

```bash
curl -sk -b /tmp/owner.jar -X POST https://localhost:8000/imports/csv \
    -H "X-CSRF-Token: x" -F "file=@apple-health-export.csv"
```

Two shapes are auto-detected by header sniffing (Apple Health vocabulary
like `Workout Type` / `Start Time` / `Energy Burned (kcal)` works, as does
a plain `date,steps,weight_kg,resting_hr,hrv_ms,spo2_avg` daily table —
see `backend/app/services/csv_import.py` for the alias table). Importing
is idempotent; CLI form: `python -m tools.import_csv --file export.csv`.

Labs, journal, nutrition and gear are manual-entry domains by design
(§12/§13) — REST POSTs or Telegram; they stay empty until you enter
data. AI panels need `GLM_API_KEY` plus actual usage.

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

## 9. Migrating to a homeserver over SSH (Docker)

The full path from your machine to a headless, always-on box.
Assumptions: `ssh USER@SERVER` works and Docker + Compose v2 are installed
(on a fresh Debian/Ubuntu: `curl -fsSL https://get.docker.com | sh`, then
`sudo usermod -aG docker USER` and re-login). Nothing else should listen
on :8000.

### 9.1 Move the code

```bash
# from your machine — clone straight on the server (private repo, so ssh
# keys or a token are needed there), or push/pull via your workstation:
ssh USER@SERVER 'git clone https://github.com/MatteoSchiavi/Apex_Health.git ~/apps/apex-health'

# …or copy an existing working tree (fastest when you already have .env
# tuned locally — .venv/backups excluded):
rsync -a --exclude .venv --exclude backups --exclude .git \
      /path/to/apex-health/ USER@SERVER:apps/apex-health/
```

### 9.2 Configure on the server

```bash
ssh USER@SERVER
cd ~/apps/apex-health
cp .env.example .env
nano .env
```

Minimum for a working server (generate each secret fresh — never reuse
the dev values):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SESSION_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # ENCRYPTION_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # BACKUP_ENCRYPTION_KEY
```

- `OWNER_EMAIL` / `OWNER_PASSWORD` — your login (§15 bootstrap).
- `DATABASE_URL` / `REDIS_URL` can stay EMPTY: compose overrides them with
  container-network values (`db:5432`, `redis:6379`) anyway.
- `BACKUP_ENCRYPTION_KEY` — set it now; losing it later means losing every
  backup artifact (§22.7).
- `TELEGRAM_BOT_TOKEN`, `GLM_API_KEY`, `OPENAI_API_KEY`,
  `WEATHER_HOME_LAT/LON`, `GARMIN_EMAIL/PASSWORD` — per feature, see §3
  and §7. Uncomment `GRAFANA_ADMIN_PASSWORD` to move off `apex-demo`.
  After setting the bot token add the bot service:
  `docker compose -f infra/docker-compose.yml --profile telegram up -d`.

### 9.3 Boot & verify

```bash
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
curl http://localhost:8000/health                     # → {"status":"ok"}
docker compose -f infra/docker-compose.yml ps        # all healthy
```

- Exercise the API (owner login, session cookie + CSRF header for writes,
  §22.3):

```bash
BASE=http://localhost:8000
curl -c /tmp/jar -X POST $BASE/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"<OWNER_EMAIL>","password":"<OWNER_PASSWORD>"}'
curl -b /tmp/jar $BASE/labs | head -c 400       # authenticated GET → own lab panels
```

- Demo data (optional, synthetic, wipes user data — re-run any time):

  ```bash
  docker compose -f infra/docker-compose.yml exec api \
    env PYTHONPATH=/app python tools/seed_demo_data.py --days 240
  # owner login afterwards: owner@apexhealth.dev / demo-owner-1234
  ```

### 9.4 Survive reboots & stay off the open internet

Every compose service has `restart: unless-stopped`; the Docker daemon is
enabled by default (`sudo systemctl enable docker` to be sure). The stack
then needs no babysitting.

Do NOT port-forward the API on your router. For remote access use
Tailscale Funnel (real TLS, no opened ports, invite-flow access control):
follow [`infra/tailscale-funnel-setup.md`](../infra/tailscale-funnel-setup.md)
and set `TRUST_PROXY_HEADERS=true` in `.env` (§8a walks the friend flow).

### 9.5 Backups on the server

- Nightly at 02:00 UTC the worker writes an encrypted dump to
  `~/apps/apex-health/backups/` (host-visible, 14 daily + 6 monthly
  retention, §22.7). B2 offsite upload starts automatically once
  `B2_APPLICATION_KEY_ID` / `B2_APPLICATION_KEY` / `B2_BUCKET` are set.
- Prove restores work on the real server (the §22.7 acceptance run):

```bash
docker compose -f infra/docker-compose.yml exec api python tools/restore_drill.py
```

- A real restore into a fresh DB: `tools/restore_backup.py` (§8-4).

### 9.6 Updating the deployment

```bash
cd ~/apps/apex-health
git pull
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
```

Data lives in the named volume (`apex-health_db_data`) and the host
`./backups/` dir — code updates
don't touch them. To move homeservers: `pg_dump` via a fresh backup
artifact + copy `backups/` + `.env`, then restore into the new host's
db (§8-4) — the encrypted artifact travels safely over any channel.

## 9a. Hosting for friends: remote access on an 8 GB server

The stack is sized for it: compose carries memory limits (db 2.5 GB,
worker 1.5 GB, api 1 GB, redis 256 MB) leaving ~3.5 GB headroom on 8 GB.
Multi-user is fully server-side (invite-only accounts, per-user data
isolation, per-user AI budgets) — remote access is the only missing piece.

Recommended (in order of friend-friendliness):

1. **Cloudflare Tunnel + a real domain — the best friend experience.**
   A public `https://apex.yourdomain.com` that works in any browser, no
   VPN, no port forwarding, nothing to explain.
   - Point a (sub)domain at Cloudflare (free plan is enough).
   - On the server: `docker run -d --name cloudflared --restart unless-stopped
     --network apex-health_default cloudflare/cloudflared:latest tunnel --no-autoupdate run
     --token <TUNNEL_TOKEN>` (create the token in the Cloudflare Zero Trust
     dashboard → Networks → Tunnels; map `apex.yourdomain.com` to
     `http://api:8000`).
   - `.env`: `TRUST_PROXY_HEADERS=true` so the app adopts the forwarded
     scheme (§15), and set the Whoop/Strava redirect URIs to the public
     domain (§7b/§7c).
   - Session cookies are Secure + HttpOnly and HTTPS is automatic; invite
     redemption (§8a) is the only thing friends ever need from you.
2. **Tailscale (already documented for the Funnel variant, §15 /
   `infra/tailscale-funnel-setup.md`).** Zero public exposure; every
   friend installs the Tailscale app and joins your tailnet (or you
   enable Funnel for a public HTTPS URL without a domain). Best if you
   don't want the site on the open internet at all.
3. **What NOT to do:** plain port-forwarding of :8000 over HTTP. Cookies
   are `Secure`, so plain HTTP would break logins anyway — always put a
   TLS terminator (Cloudflare / Funnel / Caddy) in front.

Friend onboarding is §8a verbatim: mint an invite code, send it over a
trusted channel, friend calls `/auth/invite/redeem` — one request, account
+ session. Friends default to `ai_access_tier=cheap_only` (bounded AI
cost, §9.2); raise it with `PATCH /settings/users/{id}/ai-tier`.

## 10. Running the tests

```bash
cd backend && uv sync
# point DATABASE_URL/REDIS_URL at a DEV database (tests create their own DBs)
uv run pytest -q          # 315 passed is the green baseline
```

CI (GitHub Actions) runs the same suite against
`timescale/timescaledb-ha:pg16` + `redis:7` services on every push.

## 11. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `UndefinedTable` / migration errors | run `uv run alembic upgrade head`; for a scorched-earth reset use `scripts/reset-dev.sh` |
| TimescaleDB error on restore | run inside `timescaledb_pre_restore()` / `timescaledb_post_restore()` — `tools/restore_backup.py` already does this |
| Bot silent | the bot is a separate long-polling process — check it is running and `TELEGRAM_BOT_TOKEN` is set; pairing requires `/link` then `/confirm <code>` from the server log |
| Voice drafts stuck "pending" | Whisper/STT runs on the Celery **worker** — worker must be up with `OPENAI_API_KEY` |
| `search_context` says unavailable | embeddings need `OPENAI_API_KEY`; the tool degrades honestly by design |
| 403 on API writes | send the `X-CSRF-Token` header (any value) with the session cookie (§22.3) |
| Account locked | 5 failed logins per email per 15 min trigger a temporary lock (§22.1) — wait it out |
| Redis version mismatch vs compose | dev used Redis 8.x, compose pins `redis:7` — wire-compatible for everything this project uses |
