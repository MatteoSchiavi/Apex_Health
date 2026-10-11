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

CI obtains `timescale/timescaledb-ha:pg16` through its public `mirror.gcr.io`
cache to avoid Docker Hub anonymous pull quotas. The mirrored and official
manifests were compared and matched exactly; this retains the TimescaleDB
distribution containing pgvector. The release job retags that same image under
the original Compose name; production database configuration is unchanged.
The release also caches the identical `redis:7-alpine` image from the public
ECR Docker library and uses Google-cached `node:22-slim` and
`python:3.12-slim-bookworm` build bases. Official and mirror manifests matched
for those images too; runtime versions and base distributions are unchanged.

Before any service stop, backup creation or migration, the server checks:

- A healthy API and worker running the same immutable image, plus current
  database revisions and the backup encryption key.
- Exact repository/full-commit labels and `org.apex.release-channel=main`.
  Ordinary local and non-main CI builds default to `development`.
- A trusted GHCR RepoDigest and an independent pull of `:sha-<full-commit>`
  matching the moving tag's local image ID and registry digest. Deployment
  subsequently uses only the immutable local image ID.
- A bounded public GitHub comparison proving that the candidate commit equals
  or descends from the running commit, and a completed successful main-push
  run of `.github/workflows/tests.yml` for that exact candidate revision.
  All jobs, including `backend-release`, must have succeeded. GitHub outages,
  rate limits, pending publication and unverifiable metadata fail closed.
- The candidate's complete Alembic graph, inspected using a disposable
  read-only, network-disabled container with no production environment or
  mounts. Every database revision must be present and lead forward to exactly
  one candidate head. Missing, cyclic, disconnected or multi-head graphs fail.
- At least 1 GiB free on the host checkout and updater-state filesystems,
  checked before image download and again before downtime.

Only after these checks does the updater stop application processes gracefully,
create and decrypt an encrypted database backup, run migrations, and check the
new API and an actual Celery round trip. A rejected candidate leaves running
services untouched. After migration, the updater requires the actual database
revision to equal the verified candidate head before starting the image.
An unchanged selected image is a safe no-op and does not
require new release labels or GitHub verification. When updating an existing installation, the
updater stops and removes that installation's legacy bot container by its
Compose project and service labels after the new API and worker are healthy.

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

   If the old stack used the Telegram bot, remove `TELEGRAM_BOT_TOKEN` from
   `.env`. The next updater start removes the now-orphaned bot container and
   recreates the API/worker without that credential.

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

   The installer preserves an exported `COMPOSE_PROJECT_NAME`, `COMPOSE_FILE`
   (including file order and `COMPOSE_PATH_SEPARATOR`) and the selected named
   Docker context in the service command. Explicit installer options take
   precedence. This matters because systemd does not automatically inherit
   variables from the terminal that installed the timer. Use
   `--docker-context NAME` to select another named context. A session-only
   `DOCKER_HOST` is rejected unless a named context is explicitly selected;
   configure the connection as a Docker context first. Keep other Compose
   interpolation settings in the deployment `.env`, rather than relying on
   temporary shell exports.

## When updates appear stuck

The Git checkout on the host deliberately stays at its old revision. That
does not mean the running application is old: updates replace the Docker
image, whose revision is reported by the runtime diagnostic below.

After fetching the latest tools with `git pull --ff-only origin main`, run:

```sh
python3 infra/auto_update.py doctor
```

Include your original `--compose-file`, `--project-name` and
`--docker-context` options when applicable. `doctor` checks the installed
script, user timer, linger, recorded pause/interruption/failed-image state,
actual running revision, application/queue health, backup-key presence and
registry-manifest access. It does not download images, stop containers, run
migrations, resume automation or rewrite deployment state. It returns a
nonzero exit code for failed checks; warnings do not authorize a retry or
database restore. A service outage can naturally change between a diagnostic
and deployment. `status` and `doctor` remain available during an active update.

Common outcomes:

- **Installation/timer missing:** install the timer with
  `bash infra/install-auto-update.sh`, using the existing deployment options.
  Pulling a commit or running Docker Compose alone does not install a timer.
- **Linger warning:** run `sudo loginctl enable-linger "$USER"` for the same
  Linux user that installed the timer. Without linger it can stop after logout.
- **Registry error:** verify connectivity and Docker login as that same user.
  Successful authentication in another user's terminal is not sufficient.
- **Application error:** verify the recorded Docker context and project/files;
  ensure API and worker are running the same image. Do not reset the database.
- **Backup-key error:** preserve an existing key; if none exists, configure
  one securely and recreate the existing API/worker as described above.
- **Paused/interrupted or blocked image:** inspect `status` and the service
  journal and follow the recovery procedure. Do not blindly resume or retry.
- **Installed updater differs:** reinstall after pulling script changes.
  Application-image updates do not replace the installed host script.

The original installer could successfully run its first update using exported
Compose settings, then install a timer without those settings. The timer could
subsequently select the wrong project or miss an override. The corrected
installer freezes those choices and the Docker context. Existing installations
need one deliberate reinstall to receive this host-side fix:

```sh
git pull --ff-only origin main
bash infra/install-auto-update.sh
sudo loginctl enable-linger "$USER"
python3 infra/auto_update.py doctor
```

Supply the existing custom options to both commands where required. Reinstalling
does not clear a paused/interrupted deployment, reset secrets or replace the
database. Diagnose failures before repeating installation. To read the original
error locally, use `journalctl --user -u apex-health-update.service -n 60 --no-pager`.
If sharing diagnostics, redact credentials and private deployment details;
never send `.env`.

## Status, pause and recovery

The previously recovered deployment must remain paused until the installed
updater, published main release, running application revision and database
migration graph have been verified. Applying these source changes does not
enable the timer or resume updates. Reinstall host tools deliberately after
review; an application-image update does not replace the installed script.

For the already paused/recovered installation, use this sequence instead of
the ordinary installer, including the existing Compose/context options on
every applicable command:

```sh
systemctl --user disable --now apex-health-update.timer
bash infra/install-auto-update.sh --install-only
python3 .apex-updater/auto_update.py status
python3 .apex-updater/auto_update.py doctor
python3 .apex-updater/auto_update.py verify
```

`--install-only` refreshes the installed script and units without running an
update or enabling/starting the timer; it preserves paused/recovery state and
uses the existing shared update lock. `verify` downloads candidate images and
checks the complete release/database preflight, returning only image ID,
revision, digests, migration head and whether deployment is required. It never
changes updater state, stops services, creates a backup or runs migrations.
A disabled timer remains an expected `doctor` error while deliberately paused.

If `verify` fails, keep the recovered application running and investigate its
concise reason. If it reports `deployment_required: true`, verification has
not deployed that image: complete an owner-reviewed, encrypted-backup-backed
manual deployment using the verified immutable ID and existing Compose options.
Verify its migration head and API/worker health again. Only after explicit
owner approval, and with the running image matching the verified selected
release, run:

```sh
python3 .apex-updater/auto_update.py resume
systemctl --user enable --now apex-health-update.timer
```

These commands are separate owner actions; source changes and verification
never perform them automatically. The original Compose overrides, project
name and Docker context must be retained throughout recovery.

From the checkout (include your custom Compose options if any):

```sh
python3 infra/auto_update.py status
python3 infra/auto_update.py doctor
python3 infra/auto_update.py verify
python3 infra/auto_update.py pause
python3 infra/auto_update.py update
python3 infra/auto_update.py rollback
python3 infra/auto_update.py resume
```

`pause` leaves the running app alone. `rollback` restores the previous app
image only when its recorded database revision still matches; it leaves
updates paused. `resume` requires healthy API/worker, backup readiness, disk
reserve and the same release/digest/source/migration preflight as deployment.
The running image must match the selected registry release; health alone never
clears a pause or blocked candidate. Resume starts no services, performs no
migration and creates no backup. Use `update --retry` only after diagnosing a failed image. A failed
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

For an old-image/new-database rejection (for example, candidate migrations end
at `0023` while the database is at `0026`), keep the healthy recovered image
running and leave automation paused. Publish a verified main release containing
the entire database migration ancestry; verify its GitHub workflow and exact
GHCR revision identity before any authorized manual recovery. If the selected
main tag differs from the recovered running image, `resume` refuses adoption.
Complete a reviewed deployment of a compatible release first, then explicitly
request resumption. Never edit the database revision marker to bypass this gate.

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

The 1 GiB preflight is a minimum known host reserve, not an estimate of database
backup size or migration growth. It does not measure free space on a remote
Docker daemon, Docker's image/volume filesystems, or a separately mounted backup
destination. Operators must verify those capacities and allow additional space
for retained images, encrypted backups, temporary dumps and migration growth.
No automatic pruning or deletion is performed.

The automated backup covers the database. Keep independent backups of `.env`,
Compose overrides, reverse-proxy configuration and any external files you add
to the deployment. A backup on the same disk does not protect against disk loss.

## Verification boundaries

The preflight change has offline orchestration and public-GitHub-client tests;
run `python -m unittest infra.tests.test_auto_update -v` to verify the rejection,
backup, migration, rollback, explicit-resume, duplicate-invocation and failure
boundaries. These tests use synthetic image/registry/workflow/migration data
and perform no Docker deployment or database writes. They prove the reported
`0026` database / `0023` image mismatch triggers no service stop, backup or
migration. Existing healthy installations remain untouched by failed preflight.

This change has not verified a live deployment, real published release labels,
container graph inspection or home-server recovery. The completed GitHub release
job remains the production-image gate; successful earlier test jobs alone do
not establish release readiness. Full CI and a disposable release rehearsal
are required before owner-authorized production use. Installer diagnostics do
not authorize resuming the paused home-server timer.
