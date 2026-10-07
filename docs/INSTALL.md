# Install and host Apex Health

This is the supported path for a laptop, home server or small private host.
Docker Compose builds the React web interface into the FastAPI image, then
starts PostgreSQL/TimescaleDB, Redis, the API and the Celery worker.

## Requirements

- Docker Engine with Compose v2
- 8 GB RAM and 15 GB free disk for a comfortable small installation
- A modern browser

Automatic updates additionally require Linux/systemd, Intel/AMD x86-64 and
Python 3.10+; see [AUTO_UPDATES.md](AUTO_UPDATES.md).

The default stack exposes the application only on `127.0.0.1:8000`. Put a TLS
reverse proxy in front of it before making it reachable from your network or
the internet.

## First start

```sh
git clone https://github.com/MatteoSchiavi/Apex_Health.git
cd Apex_Health
cp .env.example .env
```

Open `.env` and set these values before starting:

| Setting | How to set it |
| --- | --- |
| `OWNER_EMAIL` | Your administrator login email |
| `OWNER_PASSWORD` | A unique password, at least 12 characters and three of lowercase/uppercase/digit/symbol |
| `SESSION_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | `python3 -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
| `POSTGRES_PASSWORD` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `BACKUP_ENCRYPTION_KEY` | A separate `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` value; required for automatic updates |

Generate values locally and put them securely into `.env`; do not commit them
or paste them into chat. Preserve existing session, database and encryption
secrets during upgrades. Changing either encryption key makes existing
encrypted values or backups unreadable. Changing `POSTGRES_PASSWORD` in `.env`
alone does not change the password of an existing PostgreSQL volume.

For this loopback HTTP first start, also set `COOKIE_SECURE=false` before
starting. Keep it enabled when using HTTPS.

Start the platform:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
docker compose --env-file .env -f infra/docker-compose.yml ps
curl http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:8000` and sign in with the owner account. Migrations run
before the API starts; do not run Alembic manually for a normal Compose start.
Use `/admin` for owner administration and Settings to invite friends. Before
sharing the instance, configure the operator's legal facts and review
[LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md).

## Local HTTP and HTTPS

`COOKIE_SECURE=true` is the safe default. For a local loopback-only HTTP trial,
set `COOKIE_SECURE=false` in `.env` and restart the API:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --force-recreate api
```

For a LAN or internet-facing host, leave secure cookies enabled and terminate
TLS in a trusted reverse proxy. Set `TRUST_PROXY_HEADERS=true` and set
`TRUSTED_PROXY_IPS` to only the proxy addresses that can reach the API. Keep
port 8000 bound to loopback.

## Everyday operations

For automatic deployments of tested main commits, follow
[AUTO_UPDATES.md](AUTO_UPDATES.md). Its image override replaces the manual
rebuild commands below once enabled.
Include your original override files and `.apex-updater/active.compose.yml`
for manual restarts of an updater-managed stack. Pulling Git changes alone
does not update its installed timer script; reinstall deliberately for updater
fixes. `python3 infra/auto_update.py doctor` checks prerequisites without
deploying; preserve custom project/files/context options.

```sh
# Follow API or worker logs
docker compose --env-file .env -f infra/docker-compose.yml logs -f api
docker compose --env-file .env -f infra/docker-compose.yml logs -f worker

# Rebuild after pulling an update
git pull --ff-only origin main
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait

# Stop the platform without deleting data
docker compose --env-file .env -f infra/docker-compose.yml down
```

Do not use `down -v` on a real installation: it deletes the database and Redis
volumes.

## Optional integrations

The platform is useful without third-party credentials. Add only the
integration settings you intend to use to `.env`, then restart the affected
service.

- **Garmin:** connect through Settings in the web application. Tokens are
  encrypted; the password is used only for the connection flow.
- **FIT files:** import original files from Data Health. Originals are stored
  encrypted and sample provenance is retained.
- **AI coach:** configure an OpenAI-compatible provider using the LLM settings
  in `.env`. `DEEPSEEK_API_KEY` selects DeepSeek when per-tier overrides are
  empty; follow [COACH_SETUP.md](COACH_SETUP.md). The app remains usable when
  no key is configured.
- **Apple Health:** upload `export.zip` in Settings → Data Health; see
  [APPLE_HEALTH.md](APPLE_HEALTH.md). This is a manual import, not automatic
  iOS HealthKit synchronization.
- **Food diary:** authorize the optional external Fitbit nutrition connector;
  see [UI_DATA_CHANGES.md](UI_DATA_CHANGES.md). Provider registration and scope
  access are required.
- **Owner Telegram:** configure `OWNER_TELEGRAM_BOT_TOKEN` and
  `OWNER_TELEGRAM_CHAT_ID`, then test outbound delivery in `/admin`; see
  [OWNER_ADMIN.md](OWNER_ADMIN.md). This is independent of the old chat bot.
- **Other device providers:** add the corresponding OAuth credentials only
  after registering an application with that provider.

Provider access, model latency and device delivery are not proven by the local
test suite. Validate them with your own account before relying on them.

For a manually rebuilt installation upgrading from the former interactive
Telegram bot, delete the
`TELEGRAM_BOT_TOKEN` line from `.env` and recreate the stack. This clears the
old credential from the application environment and removes the orphaned bot
container:

```sh
docker ps -aq --filter label=com.docker.compose.project=apex-health --filter label=com.docker.compose.service=bot | xargs -r docker rm -f
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --force-recreate --wait
```

Replace `apex-health` with the Compose project name if the installation uses a
custom name.

## Backups and upgrades

Set `BACKUP_ENCRYPTION_KEY` to enable nightly encrypted backups in `backups/`.
Before any upgrade that contains real health data:

1. Verify that a recent encrypted backup exists.
2. Run a restore drill against a disposable target:

   ```sh
   docker compose --env-file .env -f infra/docker-compose.yml exec api python tools/restore_drill.py
   ```

3. For manual deployments, pull the update and run `up -d --build --wait`.
   For updater-managed deployments, follow [AUTO_UPDATES.md](AUTO_UPDATES.md)
   to preserve the pinned tested image and deployment/recovery state.

See [BACKEND_RELEASE.md](BACKEND_RELEASE.md) for the full release checklist.

## Development and tests

The production frontend lives in `frontend/`.

```sh
cd frontend
npm ci
npm run dev
```

Run the backend suite only with disposable services. It refuses to reset a
database unless `APEX_TEST_DATABASE_RESET=1` is set, and it rebuilds that
database during the run. The CI workflow shows the complete isolated setup.

```sh
cd backend
uv sync --frozen
APEX_TEST_DATABASE_RESET=1 DATABASE_URL=postgresql+asyncpg://... REDIS_URL=redis://... \
  uv run --frozen python -m pytest -q
```

For user-space development helpers, `scripts/rebuild_pg_redis.sh` installs a
local PostgreSQL/Redis toolchain and `scripts/start_dev_env.sh` starts it.
