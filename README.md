# Apex Health

A self-hosted health and performance platform for people who want one private,
evidence-aware place for training, recovery, sleep, laboratory results, gear
and coaching decisions.

The deployed application is a single stack:

- **FastAPI** provides the authenticated API and serves the web application.
- **PostgreSQL + TimescaleDB + pgvector** stores health data and analysis.
- **Redis + Celery** runs imports, analysis, scheduled work and backups.
- **React + Vite** provides the responsive, bilingual web UI.

There is no second web application or mock-data runtime in this repository.

![CI](https://github.com/MatteoSchiavi/Apex_Health/actions/workflows/tests.yml/badge.svg)

## What it does

- Imports Garmin data and original FIT files; supports source-aware manual,
  CSV and laboratory observations.
- Shows activities, sleep, biometrics, training, gear and data coverage in a
  clean Swiss-modern interface.
- Produces an evidence-backed daily decision and a Performance Lab for trends,
  baselines, experiments, data quality and goals.
- Lets the coach prepare reviewable changes. Nothing is applied until the
  account owner approves the exact proposal.
- Keeps source provenance, revisions, privacy controls, encrypted originals,
  exports, deletion previews and audit records.
- Runs scheduled jobs and encrypted backups locally. Telegram and AI providers
  are optional integrations.

## Run it locally

Docker is the supported way to run the whole platform.

```sh
git clone https://github.com/MatteoSchiavi/Apex_Health.git
cd Apex_Health
cp .env.example .env
# edit .env: set SESSION_SECRET, ENCRYPTION_KEY, OWNER_EMAIL and OWNER_PASSWORD
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
open http://127.0.0.1:8000
```

Use HTTPS for any network-facing install. For a loopback-only HTTP trial, set
`COOKIE_SECURE=false` in `.env`; browser sessions cannot work over plain HTTP
when secure cookies are enabled.

The full guide, including upgrades, backups and optional providers, is in
[docs/INSTALL.md](docs/INSTALL.md).

For a home server, [automatic updates](docs/AUTO_UPDATES.md) can follow tested
main commits using prebuilt images, encrypted backups and deployment checks.

## Repository map

```text
backend/       FastAPI application, data model, migrations, workers and tests
frontend/      React/Vite web application and browser tests
infra/         production Docker Compose configuration
connectiq/     optional Garmin Connect IQ companion
docs/          installation, architecture, security and product contracts
scripts/       local PostgreSQL/Redis helpers
wiki/          user-facing operating notes
```

## Product contracts

- [Installation and local hosting](docs/INSTALL.md)
- [Automatic home-server updates and recovery](docs/AUTO_UPDATES.md)
- [Architecture and technical choices](docs/STACK.md)
- [Performance Lab and agent contract](docs/PERFORMANCE_LAB.md)
- [UI system and screenshots](docs/UI_REDESIGN.md)
- [Release checklist](docs/BACKEND_RELEASE.md)
- [Security and privacy posture](docs/SECURITY.md)

## Verification

CI covers frontend build, locale parity, PWA and Chromium browser checks;
backend tests; updater recovery; and a production Docker release smoke test
including migration, background work and encrypted backup/restore. Successful
main pushes publish the exact tested application image to GitHub Packages.

For local UI development:

```sh
cd frontend
npm ci
npm run check:i18n
npm run build
```

For the backend test suite, use disposable PostgreSQL and Redis instances.
The suite intentionally resets its configured database; see the test section
in [docs/INSTALL.md](docs/INSTALL.md).

## Integration boundaries

Live Garmin, LLM and Telegram credentials are not bundled with the project.
The UI and local stack work without them, but live provider behaviour must be
verified with the account owner’s credentials before relying on it. The
[Performance Lab contract](docs/PERFORMANCE_LAB.md) records the remaining
provider and calibration work explicitly.
