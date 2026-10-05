# Automatic home-server updates

Apex can follow tested `main` commits without exposing an update webhook or
giving GitHub access to the home network. GitHub builds the image; the server
checks GHCR every five minutes. Downloads happen while the old app is running.
The API has a short maintenance window during backup, migration and restart.

This is supported for an existing Linux/systemd, Intel/AMD x86-64 installation
using Docker Compose v2 and Python 3.10+. Use the same Linux account and Docker
context that manage the existing stack. ARM and non-systemd hosts are not
covered by the current release pipeline.

## What is automatically updated

The pipeline runs backend tests, browser tests, frontend build/locales/PWA
checks and updater recovery tests. It then starts the production Compose stack
and checks authenticated API behavior, worker jobs, queue persistence, an
encrypted backup/restore and restore atomicity. Only a successful push to
`main` publishes the **same image** as `ghcr.io/matteoschiavi/apex_health:main`
and `:sha-<full-commit>`. Pull requests and other branches cannot promote it.
A superseded build is not promoted when main has already advanced.

The server verifies the source/revision labels, pins the pulled image ID,
checks the existing API/worker, stops application processes gracefully, creates
and decrypts an encrypted database backup, runs migrations, then checks the
new API and an actual Celery round trip. The optional running Telegram bot is
updated too. Download/authentication/preflight failures leave the app running.

Database/Redis containers and volumes, `.env`, encryption keys and the host Git
checkout are retained. Infrastructure, environment-variable and updater-script
changes still need a planned manual upgrade. Ordinary backend/frontend and
migration changes ship inside the image. Tests reduce risk but do not prove
every provider, account or existing production database works with a release.

## One-time setup on your server

1. Push this change to main and wait for the GitHub `tests` workflow to succeed.
   Verify that the `apex_health` package exists in GitHub Packages. The workflow
   needs Actions enabled and package-write permission. If an existing package
   refuses publication, grant this repository Actions access to it in package
   settings. Private package access needs your own read-only `read:packages`
   credential (authorize organization SSO when applicable); the workflow's
   short-lived `GITHUB_TOKEN` cannot be reused on your server.

2. In your existing checkout, fetch these tools without replacing your `.env`:

   ```sh
   cd /path/to/Apex_Health
   git pull --ff-only origin main
   ```

   Preserve any local Compose overrides and pass them below. Do not use
   `git reset --hard`, recopy `.env.example` or change existing encryption keys.
   Check that the current Compose API and worker are healthy and use the same
   image. The updater refuses to repair a broken or mixed-image installation.

3. If `BACKUP_ENCRYPTION_KEY` is already set, keep it. If it is blank, generate
   a strong value locally (`python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`),
   put it in `.env`, then recreate the **existing** API/worker so they read it.
   Back up this key separately along with `ENCRYPTION_KEY` and `SESSION_SECRET`.
   The updater will refuse to deploy without encrypted backups. Never commit
   keys or paste them into chat.

4. Log in if the package is private. `docker login` prompts for your read-only
   package credential; it is not put into shell history:

   ```sh
   docker login ghcr.io --username MatteoSchiavi
   ```

   Skip this for a public package. Keep the application itself private even
   if you choose to make its code/image public.

5. Install the timer:

   ```sh
   bash infra/install-auto-update.sh
   sudo loginctl enable-linger "$USER"
   systemctl --user list-timers apex-health-update.timer
   journalctl --user -u apex-health-update.service -n 50
   ```

   The installer performs the first verified deployment **before** enabling
   the timer. Linger keeps your user service manager running after logout and
   reboot. Docker must also be configured to start on boot. No server inbound
   port or GitHub SSH key is required. Registry credentials remain in your
   Docker credential store; use a credential helper where available.

   For custom Compose configuration, include every file in its original order
   and the existing project name, for example:

   ```sh
   bash infra/install-auto-update.sh \
     --compose-file infra/docker-compose.yml \
     --compose-file /absolute/path/home.override.yml \
     --project-name apex-health
   ```

   Use the same options for manual updater commands. `--dry-run` prints the
   timer/service without touching the installation. The installer copies a
   stable version of the updater to `.apex-updater/auto_update.py`; reinstall
   deliberately after pulling infrastructure/updater changes.

## Status, pause and recovery

From the checkout (include your custom Compose options if any):

```sh
python3 infra/auto_update.py status
python3 infra/auto_update.py pause
python3 infra/auto_update.py update
python3 infra/auto_update.py rollback
python3 infra/auto_update.py resume
```

`pause` leaves the running app alone. `rollback` restores the previous app
image only when its recorded database revision still matches; it leaves
updates paused. `resume` requires a healthy running API/worker and adopts that
deployment. Use `update --retry` only after diagnosing a failed image. A failed
image is otherwise skipped until a new tested image arrives.

If backup fails, or startup fails **without a database revision change**, the
updater attempts to restore the previous app and checks it. A migration error,
startup failure after a revision change, failed recovery or interrupted update
pauses automation. Application processes remain stopped for operator recovery;
the database, queue and encrypted backup are retained. It never automatically
downgrades or restores the database. This can mean downtime until you intervene.

For migration-related recovery, inspect `status` and the service journal first.
Prefer a corrected release compatible with the current database. If restoration
is necessary, test the recorded artifact against a **new disposable database**
using `backend/tools/restore_backup.py`, verify it, then deliberately switch to
that restored database and its matching previous image. A backup restore loses
changes after the backup; never blindly run it over the live database.
`resume` does not perform a restore or restart stopped services for you.

The active image override is `.apex-updater/active.compose.yml`. Include it when
manually inspecting/restarting the managed deployment, for example:

```sh
docker compose --env-file .env -f infra/docker-compose.yml \
  -f .apex-updater/active.compose.yml up -d --no-build --pull never --no-deps api worker
```

Add your usual override files before the active override. During manual
recovery, `previous.compose.yml` and `candidate.compose.yml` retain the pinned
image choices. Do not run a plain `up --build` while automation is enabled:
that builds the older host checkout and can replace the tested deployment.

To disable the recurring check entirely:

```sh
systemctl --user disable --now apex-health-update.timer
```

## Storage and monitoring

State/lock/overrides are private under `.apex-updater/` and ignored by Git.
Pre-update backups are under `backups/deployments/<time>-<commit>/`, separate
from nightly backup retention. Local rollback images are deliberately retained.
Monitor disk space and failed timer runs; review and remove obsolete deployment
backups/images manually once you have a verified offsite copy and no longer
need their recovery points. Avoid blanket Docker pruning of rollback images.
Health endpoints are checks, not an alerting service. Check the timer journal
or connect it to your existing home-server monitoring.

The automated backup covers the database. Keep independent backups of `.env`,
Compose overrides, reverse-proxy configuration and any external files you add
to the deployment. A backup on the same disk does not protect against disk loss.

## Verification boundaries

The updater's 18 offline failure/recovery tests pass. Installer dry-run output
passes `systemd-analyze verify`; real Compose accepts the image overrides and
an isolated Docker container verified the pinned-image startup flags. The
GitHub release job is the final production-image gate. Cloud Docker build verification may require
allowing `www.postgresql.org` and `apt.postgresql.org` in the environment's
network settings; a policy denial is not a passed production build. Installation
and deployment on the actual home server require the one-time steps above.
