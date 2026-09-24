# Chapter 5 — Maintenance

*Four commands to update; everything else the beat does for you.*

## 5.1 — Update runbook

```powershell
cd ~/apps/apex-health   # (or your Windows clone)
git pull
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
```

Data lives in the named volume `apex-health_db_data` and the host `./backups/` folder — code updates never touch either. The build recompiles the SPA, so UI updates ship with the same command; a hard browser refresh (**Ctrl+Shift+R**) after updating avoids stale cached assets.

## 5.2 — What the nightly schedule does

| When (UTC) | Job | What it does |
|---|---|---|
| every 6 h | Connector syncs | Garmin :00, Whoop :05, Strava :07, Oura :09, weather :20 — incremental, paced, per-user isolated (one account's failure never aborts another's sync). |
| 02:00 | Encrypted backup | `pg_dump` compressed and encrypted with `BACKUP_ENCRYPTION_KEY` → `./backups/` on the host; 14 daily + 6 monthly retained; optional B2 offsite upload. |
| 03:00 local | Feature engine | Scores readiness/recovery/strain for the prior day per user (hourly dispatch, gates on local wall clock). |
| 04:00 | Session purge | Deletes expired login sessions (the table stays bounded forever). |
| 04:30 | Retention | Drops 1 Hz streams older than 400 days once summary metrics exist, raw ingest payloads older than 180 days, AI call logs older than 400 days; weekly VACUUM ANALYZE. |
| 23:45 | Budget check | Sums per-user AI spend; a pre-turn gate also refuses new agent turns past 2× the daily budget with a friendly 429. |

## 5.3 — Backups: prove they work

The nightly artifact is only as good as your last restore test. The restore drill seeds markers, takes a backup, restores into a scratch database, compares every table and decrypts the crypto-marked lab note:

```powershell
docker compose -f infra/docker-compose.yml exec api python tools/restore_drill.py
# RESTORE DRILL PASSED — N/N tables match
```

A real restore into a fresh DB:

```powershell
docker compose -f infra/docker-compose.yml exec api python tools/restore_backup.py `
  backups/hcc-YYYYMMDD-HHMMSS.daily.sql.gz.enc --target-dsn postgresql://.../hcc_restore
```

**Guard two keys.** Losing `ENCRYPTION_KEY` means losing connector tokens and lab notes (they cannot be decrypted again); losing `BACKUP_ENCRYPTION_KEY` means losing every backup artifact. Store both in a password manager now. The audit's own report file (`AUDIT_FINDINGS_diff.md`) can be deleted from the repo whenever you like.

## 5.4 — Health, logs, troubleshooting

```powershell
curl.exe http://localhost:8000/health
```

answers with database and redis status; the Settings page shows each integration's state and failure streak. Logs rotate (10 MB × 3 files per service):

```powershell
docker compose -f infra/docker-compose.yml logs -f api   # (or worker, bot)
```

| Symptom | Cause & fix |
|---|---|
| API exits at boot | Startup secret validator refused weak/missing `SESSION_SECRET` / `ENCRYPTION_KEY` / `OWNER_PASSWORD` — fix `.env`. |
| `UndefinedTable` / migration error | Run `alembic upgrade head` (the API never auto-migrates). |
| 403 on a write from curl | Send the `X-CSRF-Token` header (double-submit: value must match the `csrf_token` cookie) — the SPA does this automatically. |
| Login blocked | 5 failed attempts / 15 min → temporary lockout; wait it out. |
| Garmin connect rejected | Rate-limited to 3 connects/hour; re-check credentials/MFA; sync tokens refresh automatically afterwards. |
| Bot silent | Start it: `--profile telegram up -d`; pairing is `/link` then `/confirm` with the code from the server log. |
| Voice drafts stuck pending | Whisper runs on the worker — worker up + `OPENAI_API_KEY` set. |
| Overview shows an older day | Working as designed: today is unsynced, the dashboard anchored to the most recent measured day and says so. |
| Coach answers 429 | Daily AI budget gate — raise `DAILY_TOKEN_BUDGET_USD` or wait for the UTC reset. |
| Login impossible over HTTP | Cookies are `Secure` — on plain-HTTP LAN set `COOKIE_SECURE=false` in `.env` (never when served over HTTPS). |

**Next:** [Remote access (free) →](06-Remote-Access.md)
