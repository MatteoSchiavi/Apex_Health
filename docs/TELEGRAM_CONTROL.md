# Telegram remote control

The owner bot can manage the existing Apex installation from a private Telegram chat. The controller is a
separate systemd user process on the Docker host, so it remains available during API/worker restarts.
It polls Telegram over outbound HTTPS; no inbound webhook, public administration port, Telegram SDK or
Docker socket mount inside application containers is needed. Existing feedback/operational outbox notifications
continue using the same bot.

## Installation

Use the Linux account and named Docker context that manage the existing stack. Python 3.10+, Docker Compose
v2 and systemd user services are required. Pull the reviewed infrastructure changes while preserving `.env`,
local overrides and encryption keys. In `.env`, set `OWNER_TELEGRAM_BOT_TOKEN` and the owner's positive private
`OWNER_TELEGRAM_CHAT_ID`. Start the bot conversation from that private account. Optionally set
`OWNER_TELEGRAM_USER_ID`; it must equal the private chat ID. Group/supergroup/channel chats are rejected.
Never send credentials to the bot or paste them into a support chat.

Install controls without deploying the application or resuming the updater:

```sh
bash infra/install-telegram-control.sh --dry-run
bash infra/install-telegram-control.sh
sudo loginctl enable-linger "$USER"
```

Pass the same `--compose-file` (repeatable), `--project-name` and `--docker-context` options used by your existing
installation. `COMPOSE_FILE`, `COMPOSE_PATH_SEPARATOR`, `COMPOSE_PROJECT_NAME` and `DOCKER_CONTEXT` are honored.
Session-only `DOCKER_HOST` is rejected; use a named Docker context. Only one polling consumer may use this bot.
Remove any previous webhook or independent polling process before installing these controls. The disabled
legacy application chat bot must stay disabled.

The installer validates literal credentials and Docker access, copies the controller and its updater dependency
into `.apex-updater`, writes `apex-health-telegram.service`, and starts it. It neither deploys an image nor alters
the automatic-update timer. It does not replace the timer's independently installed updater script. Linger keeps
user services available after logout and reboot. Send `/help` when the bot reports that it is online.

After changing credentials, restart only this host service and restart API/worker separately if their notification
settings also changed. Infrastructure fixes need an explicit pull and reinstall; an app image update cannot
replace installed host scripts.

## Commands

| Command | Behavior |
| --- | --- |
| `/help` or `/start` | Command list; available during an operation |
| `/status` | Actual running revision, recorded updater revision, services and update permission/phase; during operations returns the current phase |
| `/health` | API/database/Redis health and a real worker round trip |
| `/resources` | Host memory/load and deployment-filesystem disk usage |
| `/logs` | Last 15 sanitized operational event codes; no raw log text or health data |
| `/jobs` | Responding worker, active, reserved and scheduled job counts; no account/job arguments |
| `/sync garmin` | Queue synchronization for active connected accounts; also supports whoop, oura, strava, coros and technogym |
| `/update` | Check and deploy the newest **tested, published** release now, using the updater preflight/backup/migration/recovery safeguards |
| `/verify` | Verify the published release, digest and migration path without deploying, saving updater state or resuming updates |
| `/update retry` | Explicit retry of a blocked failed image, with confirmation; all compatibility checks still apply |
| `/backup` | Create and decrypt-verify an encrypted database backup on the server; requires the existing backup key |
| `/restart api`, `/restart worker`, `/restart app` | Confirmed restart of existing application containers; retain their selected images |
| `/pause` | Pause automatic application updates without stopping services |
| `/resume` | Confirmed adoption of a healthy deployment and resumption of update permission; requires deliberate owner review |
| `/rollback` | Confirmed rollback only if current and previous schemas match; leaves updates paused |
| `/confirm CODE` | Single-use confirmation valid for 60 seconds |
| `/cancel` | Cancel a pending confirmation; cannot cancel an already running deployment |

`/update` cannot bypass a paused updater, interrupted migration, release verification, protected database state,
backup requirements or shared deployment lock. A newer Git commit is not necessarily a published release.
Commands neither rewind databases nor delete volumes, keys, health records or backups. `/sync` affects all
active accounts connected to the selected provider; it schedules existing account-scoped tasks rather than
reading or returning their health records.

If automation was paused after an incident, leave it paused until the release channel, running revision and
schema compatibility are verified using [automatic update recovery](AUTO_UPDATES.md). Installing controls is
not approval to resume. Explicit owner `/resume` remains a deliberate operation, never a startup action.

## Notifications and failure behavior

The controller reports deployment state changes, initial health failure, subsequent recovery and disk crossing
90% usage in either direction. Checks run about once per minute while idle. Expected deployment downtime
suppresses health-failure alerts. Repeated unchanged failures stay quiet. Existing notifications still cover
feedback, invites, connector failures, critical application events and the daily summary.

Accepted operations run in a background thread; Telegram polling and lightweight status/resources remain
available. One command operation runs at a time and mutations share the timer's `update.lock`. Commands are
accepted only from the configured private owner's sender and chat, within two minutes of sending. Forwarded
messages, other chats, edited updates, arbitrary service names, shell arguments and unknown commands cannot
run operations. Confirmation codes are one-use, expire and are lost when the controller restarts.

The durable polling cursor is advanced before execution to prevent command replay. The first installation
discards queued older commands. If the process restarts during an accepted operation, it reports an uncertain
outcome and never reruns it automatically; inspect `/status` and `/health` before retrying. Replies/alerts have
a private, persistent bounded outbox (100 messages), retried after Telegram outages. A crash after Telegram
accepts a reply can duplicate delivery. An outage longer than two minutes can make delayed commands expire;
resend a command after connectivity returns. Raw exception messages, tokens, SQL, prompts and private health
payloads are never returned in operation failures. The private host journal is the recovery diagnostic source.

Telegram is an external service: operational messages and existing feedback content go to the configured
owner chat. Keep it private, secure that account and protect the token and host user, which has Docker access.
Manual backups are retained under the server deployment-backup directory and are not covered by nightly
retention; review disk use and remove obsolete backups deliberately while preserving recovery copies.

## Troubleshooting and removal

```sh
systemctl --user status apex-health-telegram.service
journalctl --user -u apex-health-telegram.service -n 50
systemctl --user restart apex-health-telegram.service
systemctl --user disable --now apex-health-telegram.service
```

Stopping the controller leaves the application and timer untouched. API/worker outbox delivery remains
independent. No live Telegram delivery or host deployment is verified by offline regression tests.
