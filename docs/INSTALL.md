# Install and host Apex Health

This is the supported path for a laptop, home server or small private host.
Docker Compose builds the React web interface into the FastAPI image, then
starts PostgreSQL/TimescaleDB, Redis, the API and the Celery worker.

## Requirements

- Docker Engine with Compose v2
- 8 GB RAM and 15 GB free disk for a comfortable small installation
- A modern browser

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
| `OWNER_PASSWORD` | A long, unique password |
| `SESSION_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `BACKUP_ENCRYPTION_KEY` | Generate a second Fernet key if you want encrypted backups |

Keep the three secrets when you upgrade. Changing either encryption key makes
existing encrypted values or backups unreadable.

Start the platform:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
docker compose --env-file .env -f infra/docker-compose.yml ps
curl http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:8000` and sign in with the owner account. Migrations run
before the API starts; do not run Alembic manually for a normal Compose start.

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

```sh
# Follow API or worker logs
docker compose --env-file .env -f infra/docker-compose.yml logs -f api
docker compose --env-file .env -f infra/docker-compose.yml logs -f worker

# Rebuild after pulling an update
git pull
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
  in `.env`. The app remains usable when no key is configured.
- **Other device providers:** add the corresponding OAuth credentials only
  after registering an application with that provider.

Provider access, model latency and device delivery are not proven by the local
test suite. Validate them with your own account before relying on them.

When upgrading from a version that ran the Telegram bot, delete the
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

3. Pull the update and run the normal `up -d --build --wait` command.

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
uv sync
APEX_TEST_DATABASE_RESET=1 DATABASE_URL=postgresql+asyncpg://... REDIS_URL=redis://... \\
  uv run pytest -q
```

For user-space development helpers, `scripts/rebuild_pg_redis.sh` installs a
local PostgreSQL/Redis toolchain and `scripts/start_dev_env.sh` starts it.
