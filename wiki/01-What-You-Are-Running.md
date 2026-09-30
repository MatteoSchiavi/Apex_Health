# Chapter 1 — What you are running

*Five containers, one box, zero cloud dependency.*

Apex Health is a single-server platform: a FastAPI backend that also serves the compiled web UI, a PostgreSQL 16 database with TimescaleDB and pgvector extensions, Redis as the job broker, a Celery worker that runs every scheduled job (syncs, scoring, backups, retention), and an optional Telegram bot. Everything is stored locally in one Docker volume — activity streams, sleep stages, lab panels, AI chat history, embeddings — and nothing leaves the machine except calls you deliberately configure (device APIs, LLM providers, optional B2 backup upload).

## The services

| Service | Role | Exposed as |
|---|---|---|
| `api` | FastAPI + the built SPA (one process, no nginx). Serves every route incl. `/docs` | `127.0.0.1:8000` only |
| `db` | PostgreSQL 16 + TimescaleDB + pgvector. All health data, tuned for 8 GB | compose network only |
| `redis` | Celery broker, rate limits, OAuth state, agent locks (256 MB cap, LRU) | compose network only |
| `worker` | Celery worker with embedded beat — every scheduled job lives here | none |
| `bot` | Telegram long polling (outbound-only, behind the `telegram` profile) | none |

## Three facts worth memorizing

1. **The API never auto-migrates.** After the very first build (and after every update) you run `alembic upgrade head` once.
2. **The owner account is bootstrapped at startup** from `OWNER_EMAIL` / `OWNER_PASSWORD`, and a startup validator refuses to boot production with weak secrets — if the API exits immediately, check your `.env`.
3. **Every service carries `restart: unless-stopped`**, so a reboot of the host brings the whole stack back with the Docker daemon; there is nothing to babysit.

## Memory budget (sized for your 8 GB homeserver)

```
db 2560 MB · worker 1536 MB · api 1024 MB · redis 256 MB
```

A ~5.4 GB worst-case ceiling that idles far lower. The Postgres flags (512 MB shared buffers, 8 MB work_mem, WAL compression, 256 MB shm) and the Redis cap were audit-tuned so concurrent backfills, the nightly engine and AI chats cannot OOM the box.

**Next:** [Installation (Windows) →](02-Installation-Windows.md)
