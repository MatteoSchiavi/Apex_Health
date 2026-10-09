# Apex Health

A private, invite-only, self-hosted health and performance platform for the owner
and individually invited friends who want one evidence-aware place for
training, recovery, sleep, laboratory results, gear
and coaching decisions.

The deployed application is a single stack:

- **FastAPI** provides the authenticated API and serves the web application.
- **PostgreSQL + TimescaleDB + pgvector** stores health data and analysis.
- **Redis + Celery** runs imports, analysis, scheduled work and backups.
- **React + Vite** provides the responsive, bilingual web UI.

![CI](https://github.com/MatteoSchiavi/Apex_Health/actions/workflows/tests.yml/badge.svg)

Web beta 0.1 release checks and the remaining owner actions are documented in
[BETA_0_1_READINESS.md](docs/BETA_0_1_READINESS.md). `GET /version` identifies
the installed release; passing repository tests does not update a home server.

See [ATHLETE_SYSTEM.md](docs/ATHLETE_SYSTEM.md) for the optional multi-priority athlete profile, shared daily sessions, reviewed plan baselines and voluntary AI authorization. Metric formulas and release validation are linked there.

## What it does

- Imports Garmin data and original FIT files; supports source-aware manual,
  CSV, Apple Health ZIP and laboratory observations. The repository also
  contains a native HealthKit bridge source project and pairing API; Xcode,
  Apple signing, device installation and live synchronization still need a
  compatible Mac/iPhone verification.
- Shows activities, sleep, biometrics, training, gear and data coverage in a
  clean Swiss-modern interface.
- Produces an evidence-backed daily decision and a Performance Lab for trends,
  baselines, experiments, data quality and goals.
- Lets the coach prepare reviewable changes. Nothing is applied until the
  account owner approves the exact proposal.
- Keeps source provenance, revisions, privacy controls, encrypted originals,
  exports, deletion previews and audit records.
- Runs scheduled jobs and encrypted backups locally. AI providers are optional
  integrations.
- Supports phone installation as a PWA, a monthly calendar, subtle metric
  interpretation cues and selectable history windows. Offline navigation shows
  a generic page; private health responses are not cached by the service worker.
- Keeps notification preferences and Data Health in Settings, with a notification
  popover in the top bar. Food reads an optional external Fitbit diary rather
  than providing a separate food-logging application.
- Provides an owner-only `/admin` dashboard for users, permissions, sessions,
  invitations, feedback, measured server resources, filtered operational logs
  and aggregate alpha-utility signals. Those signals describe use and reported
  influence; they do not establish product acceptance or health benefit.
- Collects feedback throughout the app and optionally sends owner Telegram
  notifications with durable retries. This is an outbound notification bot.
- Supports rolling 30-day Remember Me sessions, capped at 90 days; ordinary
  logins use browser-session cookies.
- Explains supported health metrics in a collapsed “Understand this metric”
  section, using local English/Italian education and recorded context with no
  AI calls. Actual ACWR inputs are shown when available; measured and provider
  metrics do not claim causal contributors.

## Run it locally

Docker is the supported way to run the whole platform.

```sh
git clone https://github.com/MatteoSchiavi/Apex_Health.git
cd Apex_Health
cp .env.example .env
# edit .env: set SESSION_SECRET, ENCRYPTION_KEY, OWNER_EMAIL,
# OWNER_PASSWORD and POSTGRES_PASSWORD using docs/INSTALL.md
# for this loopback HTTP trial, also set COOKIE_SECURE=false
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
```

Open `http://127.0.0.1:8000` in your browser and sign in as the owner. Set
`BACKUP_ENCRYPTION_KEY` to enable encrypted backups; automatic updates require it.

Use HTTPS for any network-facing install. For a loopback-only HTTP trial, set
`COOKIE_SECURE=false` in `.env`; browser sessions cannot work over plain HTTP
when secure cookies are enabled.

The full guide, including upgrades, backups and optional providers, is in
[docs/INSTALL.md](docs/INSTALL.md).

For a home server, [automatic updates](docs/AUTO_UPDATES.md) can follow tested
main commits using prebuilt images, encrypted backups and deployment checks.
Install the updater once; pushing to GitHub alone does not install a server timer.
Supported updater hosts are Linux/systemd on Intel/AMD x86-64, with Compose v2
and Python 3.10+. Preserve your existing Compose files, project and Docker context.

Once installed, the updater changes the running application image; the host Git
checkout stays at its old revision. Infrastructure/updater changes need a deliberate
pull and reinstall. Use `python3 infra/auto_update.py doctor` with your deployment
options to check timer, health, backup-key presence, registry access and the actual
running revision. Follow the guide for pauses and migration failures rather than
blindly retrying. Include `.apex-updater/active.compose.yml` when manually restarting
an updater-managed installation so the selected image is preserved.

## Owner, AI and deployment configuration

The owner account is created from `OWNER_EMAIL` and `OWNER_PASSWORD` at startup.
Invite friends through Settings or `/admin`. Owners can revoke friend access and
sessions; owner roles cannot be transferred or demoted through the dashboard.

For DeepSeek, set `DEEPSEEK_API_KEY`. With per-tier overrides empty, the Coach
uses `https://api.deepseek.com` and `deepseek-flash`; existing explicit GLM/custom
settings retain precedence. See [Coach setup](docs/COACH_SETUP.md) for settings,
model selection, tool budgets and restarting the correct image.

Owner Telegram notifications use `OWNER_TELEGRAM_BOT_TOKEN` and
`OWNER_TELEGRAM_CHAT_ID`; test delivery in `/admin` after configuring the server.
The former interactive Telegram chat service remains removed. Feedback can be
sent to the configured owner chat, so avoid submitting credentials or private
medical records. See [owner operations](docs/OWNER_ADMIN.md) for monitoring scope,
log limits, delivery retries and retained feedback.

Keep `.env` and encryption keys private and preserve them during upgrades. Before
inviting friends, configure the operator facts and review
[legal deployment requirements](docs/LEGAL_DEPLOYMENT.md). Private hosting and
legal notices alone do not establish legal compliance or medical-device status.

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
- [Owner administration, feedback and Telegram](docs/OWNER_ADMIN.md)
- [AI Coach and DeepSeek configuration](docs/COACH_SETUP.md)
- [Architecture and technical choices](docs/STACK.md)
- [Performance Lab and agent contract](docs/PERFORMANCE_LAB.md)
- [UI system and screenshots](docs/UI_REDESIGN.md)
- [UI refinements and sport-specific detail views](docs/UI_REFINEMENTS.md)
- [UI/data changes and external food diary setup](docs/UI_DATA_CHANGES.md)
- [Metric education, deterministic context and current limitations](docs/METRIC_EDUCATION.md)
- [WHOOP setup](docs/WHOOP_SETUP.md) · [COROS MCP](docs/COROS_MCP.md) · [Apple Health import](docs/APPLE_HEALTH.md)
- [Release checklist](docs/BACKEND_RELEASE.md)
- [Security and privacy posture](docs/SECURITY.md)
- [Private deployment legal review](docs/LEGAL_DEPLOYMENT.md)
- [October audit fixes, exceptions and historical repair](docs/AUDIT_2026_10.md)
- [System 1 model research and benchmark criteria](docs/SYSTEM1_MODELS.md)

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

Provider credentials are not bundled. Fixture tests and repository code do not
establish a live provider connection, complete data delivery, provider approval
or device acceptance. Verify each intended connector with the account owner's
credentials and the target device before relying on it. The native HealthKit
source project also needs Xcode signing and physical-device verification. See
the [Performance Lab contract](docs/PERFORMANCE_LAB.md) and
[Apple Health guide](docs/APPLE_HEALTH.md) for current boundaries.

This repository describes implementation and planned validation; it is not a
private-alpha acceptance statement for this code revision or any deployment.

Corrected load calculations apply when days are recomputed. Existing historical
features may need the bounded account/date-range repair described in the
[audit register](docs/AUDIT_2026_10.md); upgrades do not rewrite all history.
System 1 classifier research is documented, but no resident local model service
has been added. A deployed home server, physical-phone installation and live
provider delivery still require verification on the intended installation.
