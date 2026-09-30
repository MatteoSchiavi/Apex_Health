# Chapter 7 — Moving to the 8 GB Linux homeserver

*Same compose file, same commands — bring `.env` and the backups.*

## Step 1 — Prepare the box

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker YOURUSER    # re-login afterwards
```

## Step 2 — Clone and configure

```bash
git clone https://github.com/MatteoSchiavi/Apex_Health.git ~/apps/apex-health
cd ~/apps/apex-health && cp .env.example .env && nano .env
```

Copy your **existing** `.env` values over — especially the three keys. A fresh install with new keys cannot read data encrypted by the old ones: connector tokens and lab notes would be unrecoverable. Do not rsync Windows-side `.venv`/node artifacts; clone fresh.

## Step 3 — Boot, migrate, verify

```bash
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
curl http://localhost:8000/health
docker compose -f infra/docker-compose.yml exec api python tools/restore_drill.py
```

## Step 4 — Remote access + bot

Apply [Remote access](06-Remote-Access.md) on the server, and `--profile telegram up -d` if you use the bot. If you have existing data to carry over, take a backup on the old host, copy the `backups/` artifact over any channel (it's encrypted), and restore with `tools/restore_backup.py` into the new database.

## Boot resilience

Enable the Docker daemon at boot (`sudo systemctl enable docker`) — with `restart: unless-stopped` on every service the stack survives power cuts unattended. The memory limits from [Chapter 1](01-What-You-Are-Running.md) are already correct for this box; nothing to retune.

**Next:** [Quick reference →](Quick-Reference.md)
