# Temporary Web UI (Grafana)

A complete, read-only **stop-gap dashboard** for everything built in Phases
0-8, used during development **until the real dashboard style is chosen**
(the spec itself defers the web dashboard / Appendix A). It is a plain
Grafana OSS install talking **directly, read-only** to the dev PostgreSQL —
no backend code paths involved.

## Start / stop

```bash
# dev stack must be up first (PG :5433, Redis :6380)
bash scripts/start_dev_env.sh

grafana/run_grafana.sh          # start on http://127.0.0.1:3001
grafana/run_grafana.sh status
grafana/run_grafana.sh stop
```

First start: downloads the Grafana 11.6.3 tarball if missing (parallel-range
downloader built in — dl.grafana.com throttles per connection), creates the
`grafana_ro` SELECT-only DB role (`sql/bootstrap.sql`), provisions the
datasource + all dashboards, sets Overview as the org home (dark theme).

- **Viewer access**: no login — anonymous Viewer is enabled (dev only).
- **Admin**: `admin` / `apex-demo` (grafana.ini) — needed only to edit.
- Runtime state lives outside the repo in `/home/z/grafana-runtime`.

## Dashboards (folder "Apex Health")

| UID | Dashboard | Covers |
|---|---|---|
| apex-overview | Overview — Health at a glance | readiness/recovery/strain KPIs, alerts, load, plan, forecast |
| apex-activity | Training & Activities | weekly hours by discipline, pace, FTP, segments, weather-enriched rows |
| apex-recovery | Recovery & Sleep | HRV vs baseline, sleep stages, stress/body battery, body comp, risk scores |
| apex-nutrition | Nutrition & Supplements | calories, macros, hydration, caffeine/alcohol, supplement adherence bar gauges |
| apex-labs | Labs & Blood Health | ferritin/hemoglobin recovery story, latest metrics vs reference ranges, panel history, per-metric dropdown |
| apex-ai | AI & Agent | token budget vs spend, tool-loop audit (§8.3), model mix, tier routing, latency bar gauges, reports, voice drafts (§8.5) |
| apex-journal | Journal & Mind | subjective scores vs measured, mood vs strain dual axis, tags, voice-note history |
| apex-system | System & Sync Health | integrations, raw ingest, gear service (§13), sync logs, data coverage, rollups (§7.4), invites (§4.3), ops notes |

Every dashboard is scoped by the **Athlete** dropdown (users table); Labs
adds a lab-**Metric** dropdown; AI has an editable **Daily budget $** box
(mirrors `DAILY_TOKEN_BUDGET_USD`).

## Demo data

The UI is only as full as your dev DB. `backend/tools/seed_demo_data.py`
seeds a deterministic ~240-day story across every table (activities, sleep,
HRV, nutrition, journal + Telegram voice flow, labs incl. the low-ferritin
alert, gear overdue, AI budget crossing, plans, embeddings, forecasts):

```bash
cd backend && PYTHONPATH=. .venv/bin/python tools/seed_demo_data.py --days 240  # re-runnable, wipes user data first
# owner login afterwards: owner@apexhealth.dev / demo-owner-1234
```

**Gotcha:** seed **before** starting Grafana (or restart Grafana after
seeding) — the PostgreSQL connection pool caches prepared plans that go
stale after a TRUNCATE (`could not open relation with OID ...`), and a
restart (`grafana/run_grafana.sh stop && grafana/run_grafana.sh start`)
fixes it instantly.

**All seeded data is synthetic.** With a fresh, unseeded DB the dashboards
are honest "No data" panels and fill in as real ingestion runs.

## Maintaining the dashboards

Dashboards are **generated code** (versioned JSON, provisioned from
`grafana/dashboards/`), so schema changes don't rot them silently:

```bash
python3 grafana/tools/build_dashboards.py          # regenerate all 8 JSONs
python3 grafana/tools/validate_panels.py           # run every panel SQL against PG (needs psql)
```

`validate_panels.py` substitutes Grafana macros (`$user`, `$__timeFilter`,
`$__timeGroupAlias`) with literals and executes each query — 97/97 must pass.

Grafana-known pitfalls baked into the generator (do not regress):
- every target needs `"rawQuery": true` (else the frontend serializes the
  builder object and the backend 500s),
- template-variable `query` must be a plain SQL **string**,
- `$__timeGroupAlias` breaks this Grafana build's frontend — use explicit
  `date_trunc('day', …)` instead,
- pie/bar "category" charts use long format (`time, metric, value`) with
  `format: time_series`.

## Not covered here (by design)

- Interactive features (Telegram bot, agent chat, write-confirm flow) stay
  in the backend; the AI dashboard observes them, it does not replace them.
- Structured app logs (§21) are JSON lines on disk, not DB rows — wiring a
  log aggregator (Loki) is deliberately out of scope for a temporary UI.
- Notes on lab panels are encrypted at rest (`notes_ciphertext`) and are
  not rendered.
