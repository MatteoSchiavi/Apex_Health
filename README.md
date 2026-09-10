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
- Phase 3 (Telegram bot) — complete: polling loop, `/link` flow, voice
  pipeline with confirmable drafts, commands via the shared query layer,
  free-text agent entrypoint, alert push. Live bot needs `TELEGRAM_BOT_TOKEN`;
  fixtures only in tests/demos (§0).
