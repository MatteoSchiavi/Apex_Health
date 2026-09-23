# Apex Health — Full Stack Definition

> Decision record, owner request: "Before everything define the full stack of the
> project: define what tools you're going to use and why." Every choice below is
> judged against four constraints: **8 GB RAM homeserver**, **private install for
> friends (no public internet exposure assumed)**, **all data local**, **one
> coherent Apex Precision design language**.

## 1. The stack at a glance

| Layer | Tool | Version pin | Role |
|---|---|---|---|
| API | FastAPI | ≥ 0.115 | JSON API, session auth, CSRF, static SPA host |
| DB | PostgreSQL 16 + TimescaleDB + pgvector | pg16 / ts2.x | Hypertables for biometrics/streams, vector store for AI docs |
| Cache/queue | Redis 7 | 7-alpine | Celery broker, rate limits, session TTL counters |
| Workers | Celery beat + workers | 5.4 | Connectors, nightly features, backups |
| Frontend | React 18 + TypeScript + Vite 6 | react 18.3 | The official web UI |
| Frontend styling | Tailwind CSS v4 | 4.x | Apex Precision tokens as CSS variables |
| Charts | Apache ECharts 5 | 5.x | Telemetry streams, hypnogram, zones, load curves |
| Map | MapLibre GL JS | 5.x | Activity GPS traces (CARTO dark tiles, offline fallback) |
| Router | React Router v7 (library mode) | 7.x | URL-per-page; deep-linkable metric pages |
| Server state | TanStack Query v5 | 5.x | Cache, refetch, pagination |
| Client state | zustand | 5.x | Theme, locale, session user |
| i18n | i18next + react-i18next | 24.x | English + Italian, set at signup / settings |
| Icons | lucide-react | latest | Outline icon set matching the hairline design law |
| Fonts | Geist + JetBrains Mono (variable, bundled woff2) | — | Design-law typography, zero CDN calls |
| Connect IQ | Monkey C "Apex Day" | — | Watch client, already in repo |

## 2. Why these choices (and what was rejected)

### 2.1 React + Vite SPA instead of Next.js / Remix

The UI is a **private, authenticated dashboard** behind session cookies. Server-side
rendering buys nothing here: there is no SEO, no first-paint marketing page, no
crawler. Next.js would add a Node server process (~150–300 MB RSS) to an 8 GB box
that already runs Postgres/Timescale + Celery + API, plus a second build pipeline.

A Vite SPA compiles to **static files** that FastAPI can serve directly — no new
container, no reverse-proxy changes, no Node runtime in production. Deployment
stays: `docker compose build` → up. The whole frontend is one `dist/` folder the
API process serves with a SPA fallback.

**Rejected**: Next.js (runtime cost, SSR useless here), SvelteKit (smaller
ecosystem for chart-heavy dashboards), plain HTMX (would fight the dense
client-side interactivity — scrubbing, live rest timers, chart hover sync).

### 2.2 Tailwind CSS v4 as the design-token carrier

Both approved design specs (`ui-language/apex_precision_*/DESIGN.md`) are
token-first: color scales, type ramp, radii, spacing. Tailwind v4 reads design
tokens as **CSS custom properties** (`@theme`), so the Apex Precision palette is
declared once and every component consumes semantic classes
(`bg-surface-1`, `text-muted`, `rounded-lg`) that automatically flip under the
`.light` / `.dark` root class. Light and dark themes are therefore **guaranteed
coherent** because they are the same tokens resolved against two palettes — there
is no second styling path to drift.

The four approved mockups are Tailwind-authored; class names in the product code
stay recognizable against them.

### 2.3 ECharts for every chart class in the design

The design language demands: synchronized multi-series telemetry streams with a
scrubbing playhead (HR/power/cadence/elevation on one time axis), stage
hypnograms (horizontal banded bars), zone distributions (stacked percentage
bars), load/ACWR combo charts (bars + line + band), score gauges, and dense
sparklines. ECharts covers **all** of these in one library with canvas
performance (thousands of stream points at 60 fps scrub) and the exact aesthetic
control (hairline axes, tabular-figure tick labels, custom tooltip DOM) the spec
requires.

**Rejected**: Recharts (SVG, chokes on full-activity streams), uPlot (fastest but
too low-level — every composite chart becomes hand-rolled code), D3 (same, more
so). Bundle uses tree-shaken ECharts (~300 KB gz with only the needed chart
types).

### 2.4 MapLibre GL with free dark raster tiles + graceful offline fallback

Activity pages show the GPS trace over a dark topographic canvas. MapLibre GL is
open-source (no billing account), renders smooth with `vector`/`raster` sources.
We use **CARTO basemaps** (free, no key required) with the `dark_matter` style,
matching the mockup. If the homeserver has no internet (the "all data local"
posture), the map component **falls back to a pure canvas polyline** colored by
pace/elevation — the page never breaks, it just loses basemap context. GPS data
itself is always served from the local DB.

### 2.5 Session-cookie auth reused — the SPA is a first-class client

The backend already ships argon2 password hashing, DB-backed sessions, CSRF
middleware, and invite-based onboarding. The SPA reuses all of it unchanged:
`HttpOnly` session cookie + an `X-CSRF-Token` header on unsafe methods, injected
by the central `apiFetch` wrapper. **No tokens in localStorage** — a stolen
frontend store cannot yield a session.

`COOKIE_SECURE` (new, default `true`) exists because the cookie is
`Secure`-flagged for the TLS paths (Cloudflare Tunnel / Tailscale serve / Caddy).
LAN-HTTP installs set `COOKIE_SECURE=false` once in `.env`; the INSTALL documents
when.

### 2.6 i18n: i18next with locale baked into the account

`en` and `it` translation catalogs ship in the bundle. Locale is chosen during
onboarding (invite redeem) and stored on the account (`users.locale`), so the
choice follows the user across devices. The default falls back to browser
language for the login screen only. All metric names, day/date formats, and
coach UI strings are keyed — no hardcoded strings in components (enforced by a
grep check in CI-style pre-commit below).

### 2.7 Fonts and icons: bundled, zero CDN

Geist (UI + numerals) and JetBrains Mono (micro-telemetry, timestamps, units)
are committed as variable woff2 files (~120 KB total) under
`frontend/public/fonts`. The Material Symbols icon font of the mockups is
replaced by **lucide-react** (tree-shaken SVG outline icons, visually equivalent
hairline style) — a variable icon font would ship ~300 KB for the ~40 icons we
use. A production install makes **zero third-party requests** (tiles are the one
optional exception, see 2.4).

### 2.8 AI stack: DeepSeek main model + optional MedGemma medical tier

The LLM client is already an OpenAI-compatible abstraction (`app/core/llm.py`)
where provider choice is an env-var change. v3 makes the base URL **per tier**:

- `LLM_PROVIDER_CHEAP=deepseek-chat`, `LLM_API_BASE_CHEAP=https://api.deepseek.com/v1`
  → **DeepSeek V4-class chat model is the main coach model** (user decision),
  cheap enough for the default `cheap_only` friend tier, tool-calling capable.
- `LLM_PROVIDER_POWERFUL` stays GLM-5.2 (or any OpenAI-compatible endpoint) for
  strategy-grade answers.
- **MedGemma** (Google's clinical Gemma) is wired as an optional `medical` tier:
  an OpenAI-compatible endpoint (Hugging Face router, Vertex GenAI-compatible
  gateway, or a self-hosted GGUF behind llama.cpp/OpenAI shim). It is **disabled
  by default**, gated behind `MEDICAL_TIER_ENABLED` + per-user `ai_access_tier`,
  and used only for lab/medical interpretation prompts with mandatory
  disclaimers. Rationale: MedGemma shines at clinical text/vitals reasoning, but
  self-hosting the 27B is impossible on 8 GB RAM — hence endpoint-based
  integration the owner can turn on when a suitable host exists. The routing
  rule: anything matching medical/lab intent routes to `medical` when enabled,
  else falls back to `powerful` with the disclaimer prefix.

### 2.9 Data integration stack (devices)

| Device | Connector | Auth | Notes |
|---|---|---|---|
| Garmin | `garminconnect` (unofficial) | credentials → token store | Full backfill + 6-hourly incremental; **FIT enrichment** unlocks what Connect's JSON API hides |
| Whoop | v2 OAuth2 (`developer.whoop.com`) | OAuth2 + refresh | Owner registers the app (INSTALL §7b); annotation laws normalize units to Garmin-canonical |
| Oura | API v2 OAuth2 (`cloud.ouraring.com`) | OAuth2 + refresh, **personal apps allowed** | Sleep stages/HRV/temp deviation/spo2; same normalization law |
| COROS | Open API (`open.coros.com`) | OAuth2 | Doc-first shell implemented; owner must apply at COROS developer portal before live use (approval is manual) |
| Strava | v3 OAuth2 | OAuth2 + refresh | Activities + streams; fills device gaps |
| CSV | Apple Health / generic | file upload | Zero-config fallback for any device |

**Device priority law (new)**: each user has a **main device** (chosen at
onboarding or in Settings). The main device wins every metric where it has
data. A secondary device fills **missing days/fields** only, and its **activity**
overrides the timeframe whenever the main device recorded none for that window
(e.g. Whoop saw the gym session the Garmin left home). The resolution is a
deterministic service (`app/services/device_merge.py`) applied at ingest with
re-computable history — changing priority triggers a range recompute, never a
forked dataset.

### 2.10 Encryption posture (owner-held key)

- **Secrets** (device tokens, passwords via argon2, lab values) are already
  Fernet-encrypted at the column level with `ENCRYPTION_KEY` — a key **only the
  owner generates** and holds in `.env`.
- **Bulk telemetry** (hypertables, streams) stays queryable plaintext *inside
  the DB volume* by design: encrypting it row-wise would break Timescale
  compression and 100× the query cost. The documented answer for at-rest
  coverage of the volume is **LUKS/dm-crypt on the homeserver disk** (INSTALL
  §11) — one key you hold, protecting every byte including the DB.
- Net effect: the owner holds exactly **two keys** (`ENCRYPTION_KEY`, disk
  key) and can hand both to a debugging session — matching "I want to have the
  encryption key so I can fix bugs".

### 2.11 Serving topology (8 GB budget)

```
Cloudflare Tunnel (optional, free TLS)      Tailscale (alternative)
            └────────────┬───────────────────────┘
                   api (FastAPI + SPA)  — 1.0 GB cap
                   worker (celery+beat) — 1.5 GB
                   db (TSDB+pgvector)   — 2.5 GB
                   redis                — 256 MB
                   bot (optional)       — 256 MB
                                            ─────────
                                   total    ≤ 5.5 GB, headroom for OS
```

No Node process, no nginx, no Grafana. The SPA adds **zero runtime memory**
(files served by uvicorn's static mount).

## 3. Directory map (this change)

```
frontend/                    the official web UI (Vite project)
  src/app/                   router, providers, api client, i18n, theme
  src/components/            Apex Precision component kit
  src/features/<domain>/     one folder per nav section (overview, activities,
                             sleep, biometrics, training, coach, social, settings)
  src/locales/en|it/         translation catalogs
  public/fonts/              Geist + JetBrains Mono woff2 (committed)
backend/app/api/             + me, dashboard, activities, sleep, metrics, chats
backend/app/services/device_merge.py   device priority law
backend/app/connectors/oura|coros      new device connectors
backend/app/services/fit_enrichment.py Garmin FIT → streams/dynamics/laps
docs/STACK.md, DATA_COVERAGE.md, SECURITY.md
```
