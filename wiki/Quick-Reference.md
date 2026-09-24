# Quick Reference — the commands you'll actually use

## Every update

```bash
git pull
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
```

## Health & logs

```bash
curl http://localhost:8000/health
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f api
```

## Backup & restore drill

```bash
# nightly 02:00 UTC, automatic
docker compose -f infra/docker-compose.yml exec api python tools/restore_drill.py
docker compose -f infra/docker-compose.yml exec api python tools/restore_backup.py \
  backups/<file>.sql.gz.enc --target-dsn postgresql://.../hcc_restore
```

## Score imported history now

```bash
docker compose -f infra/docker-compose.yml exec worker celery -A app.tasks.celery_app call \
  features.recompute_range --args '[1, "2026-03-01", "2026-09-24"]'
```

## Where things live

| Path | What |
|---|---|
| `~/apps/apex-health/.env` | secrets & config |
| `./backups/` | encrypted nightly dumps |
| volume `apex-health_db_data` | the database itself |
| `infra/docker-compose.yml` | the whole stack |
| `docs/INSTALL.md` | deep reference |
| `infra/tailscale-funnel-setup.md` | tunnel recipe |

## Golden rules

1. **Never lose `ENCRYPTION_KEY` or `BACKUP_ENCRYPTION_KEY`** — data is unrecoverable without them.
2. **Never port-forward `:8000`; tunnels only.**
3. **Run the restore drill after every major change.**
4. **Scores land nightly at 03:00 local** — use `features.recompute_range` to score history now.
