# Backend release acceptance

The release backend is `backend/`: FastAPI, PostgreSQL 16 with TimescaleDB
and pgvector, Redis and Celery. Docker serves the `frontend/` Vite bundle.

## What this release fixes

- Session-bound signed CSRF tokens, rotation at login, cross-origin bootstrap
  protection, authenticated logout and safe handling of malformed tokens.
- Password changes revoke other browser sessions. Sliding expiry renews both
  the database expiry and browser cookie, within the absolute lifetime cap.
- Known and unknown account identifiers share Argon2 verification and rate
  limiting; Redis failure keys expire and concurrent attempts are counted.
- Migration `0009` preserves source links and adds account ownership,
  account-scoped provider IDs and a composite ownership foreign key.
- Scheduled syncs fan out to retryable account jobs. Advisory locks prevent
  overlapping syncs; committed Garmin checkpoints survive worker failure.
  Today is included in first syncs; stream retries are deduplicated.
- Missing credentials cannot use the owner's global Garmin credentials.
  OAuth and Garmin token refreshes persist, including failed runs; revoked
  integrations cannot have their credentials reinserted by an old job.
- Failed SQL transactions are rolled back before failure bookkeeping.
  Provider collection failures trigger retries rather than false success.
- “Sync now” returns `202` and an account-scoped status URL. It does not block
  the API or launch a second inline job. Queue outages return `503`.
- Coach chat requests define `session_id`; starting, resuming and creating a
  separate conversation work. Explicit model preferences respect account
  access caps. Provider failures return `502`/`503`, release locks and close
  HTTP clients. Draft transitions use row locks.
- CSV units follow column headers; invalid numbers and malformed rows do
  not crash ingestion. UTC offsets remain zero. Upload reads are bounded.
- Celery closes pooled asyncpg connections before its event loop ends, so
  subsequent jobs do not reuse connections from a closed loop.
- Compose gates API startup on migrations and worker startup on a healthy
  API. Redis queues persist; memory pressure causes explicit write failures.
  API exposure defaults to loopback. Backup paths and permissions are explicit.
- Backup and restore stream encrypted gzip frames with bounded memory.
  Existing Fernet archives remain readable. Frames authenticate archive
  identity and order and require an authenticated ending. Passwords are
  passed to libpq through the environment, never process arguments.
- Restores run in a transaction; SQL failure or an interrupted archive rolls
  back. Restore drills use unique scratch databases, never seed the source,
  compare row checksums and always clean up their target.

## Deploy and upgrade

Follow [INSTALL.md](INSTALL.md). Preserve existing `SESSION_SECRET`,
`ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` when upgrading. Changing an
encryption key does not migrate ciphertext. Record an encrypted backup and
verify a restore before upgrading a database containing real data.

For updater-managed installations, use [AUTO_UPDATES.md](AUTO_UPDATES.md)
instead of the manual build command below. Retain the active image override
when restarting services. Host updater changes require a deliberate reinstall;
the image deployment does not update the host checkout or timer script.

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
docker compose --env-file .env -f infra/docker-compose.yml ps
curl http://127.0.0.1:8000/health
```

`ENVIRONMENT` defaults to `prod` in Compose; set strong bootstrap credentials
and independent encryption/session/backup secrets. Cookies default to
`Secure`; use TLS for the browser. `COOKIE_SECURE=false` is for loopback HTTP
testing or an explicitly chosen LAN HTTP deployment.

For a reverse proxy, enable `TRUST_PROXY_HEADERS` and set `TRUSTED_PROXY_IPS`
to the actual trusted peer addresses. With a host proxy reaching a Docker
bridge this may be the bridge gateway, rather than `127.0.0.1`. Verify that
a browser request with your public HTTPS Origin succeeds through the proxy.
Keep the API bound to loopback; do not trust arbitrary forwarded headers.

Migration `0009` cannot safely downgrade if multiple accounts share a
provider ID. It refuses before altering schema or removing rows. Keep the
updated restore tooling if rolling back application code: older tooling
cannot read new v2 backup archives.

The host backup directory is restricted to the container application UID
1000. Use the container restore tools or an authorized host operator to read
it. Back up the independent keys separately from the archives.

## Repeatable release checks

The 2026-10-03 pass completed **480 backend tests**, production image build,
Compose startup, deployed HTTP smoke tests, four repeated Celery jobs,
pending-job recovery across Redis/worker restart, session continuity across
API restart, and encrypted TimescaleDB restore with matching row checksums
across all **58 public tables**. Both SQL-error and interrupted-stream
restores left no partial tables. These checks used disposable services.

CI runs the complete backend suite against disposable services and a
separate production-image deployment. The deployment job tests HTTP login,
CSRF, invitations, role enforcement, cross-account isolation, CSV import and
idempotency, repeated Celery jobs, queue restart recovery, actual encrypted TimescaleDB restoration
and transaction rollback after failed or interrupted restores.

The Python suite rebuilds the configured database and flushes Redis. Run it
only against disposable services, with `APEX_TEST_DATABASE_RESET=1`. The
populated upgrade test creates a separate, uniquely named database and
checks preservation, cross-account identifiers and safe downgrade refusal.

On a disposable deployment only:

```sh
docker compose --env-file .env -f infra/docker-compose.yml exec -T api \
  python tools/release_smoke.py --allow-test-writes
docker compose --env-file .env -f infra/docker-compose.yml exec -T api \
  python tools/restore_drill.py
docker compose --env-file .env -f infra/docker-compose.yml exec -T api \
  python tools/check_restore_atomicity.py
```

The smoke test adds synthetic accounts and activities. The restore drill
does not write to its source; pause writers while it compares snapshots.
It reports an inconclusive result if source data changes during the drill.

## Production acceptance still requires real accounts

Automated fixtures and an isolated deployment cannot verify vendor access
or the intended server. Before calling the backend production-ready:

1. Identify the required providers and whether existing data must be upgraded.
2. Connect those accounts manually. Verify initial backfill, MFA/OAuth,
   incremental sync, refresh, disconnect and reconnect with actual records.
3. Configure and exercise the intended AI provider; verify a read-only reply
   and a draft that applies only after confirmation.
4. Check browser login and writes through the intended TLS/proxy path.
5. Restart the deployed services, confirm queued work survives, and restore
   a current backup using the separately stored keys. Verify offsite upload
   if it is required for this deployment.

Technogym requires an eligible partner API account and remains optional.
Unconfigured providers are not evidence of a successful live integration.
UI redesign follows this acceptance boundary.

## Performance lab upgrade

Migration `0010_performance_lab` adds the canonical evidence ledger, changes, decisions, notifications, documents, jobs and analysis results. Read [PERFORMANCE_LAB.md](PERFORMANCE_LAB.md) before enabling live credentials. Start with a scoped reindex of stored Garmin raw history; coverage remains honestly incomplete until actual observations are indexed. The new harness exposes proposal authority only; approval and execution belong to authenticated application endpoints.

## October owner operations and audit update

Migration `0015` adds disabled/last-login credential fields, feedback and the
durable owner notification outbox. Migration `0016` adds derived load provenance.
Remembered sessions now renew for 30 days of inactivity with a 90-day absolute
cap. Owner APIs enforce the persisted role; feedback and outbound Telegram are
documented in [OWNER_ADMIN.md](OWNER_ADMIN.md). DeepSeek defaults and tool-budget
handling are described in [COACH_SETUP.md](COACH_SETUP.md).

The October audit pass completed 562 backend tests, 67 browser tests, production
image build and isolated API/worker checks. The updater subsequently completed
27 recovery/diagnostic tests and actual GHCR download, encrypted backup,
migration, restart, rollback/resume and repeat-update checks on disposable Compose
services. These counts describe those dated checks, not a permanent current
test count or live home-server certification. Consult
[AUDIT_2026_10.md](AUDIT_2026_10.md) for all dispositions and bounded historical
feature repair; migrations do not automatically rewrite all historical features.
