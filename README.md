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
  app/schemas     Pydantic boundary schemas
  app/tasks       Celery tasks (§19 schedule lands with its phases)
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

Phase 0 (scaffold) in progress — see `MASTER_SPEC.md` §23 for the phase plan.
