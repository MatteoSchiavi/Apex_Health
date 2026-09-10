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

## Status

- Phase 0 (scaffold) — complete: schema + seed, `/health`, owner auth +
  security middleware, Celery wiring, reset script, CI.
- Phase 1 (Garmin connector) — complete: fixture-based sync acceptance met;
  real-account connection is the owner's manual `tools/garmin_sync.py connect` step.
- Phase 2 (feature engine) — complete: golden-dataset regression suite green;
  nightly task populates daily/discipline features respecting the day-boundary
  rule; `feature_weights` seeded (v1).
