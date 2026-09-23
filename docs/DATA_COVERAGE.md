# Data Coverage — what we can and cannot retrieve per provider

> Owner question: "Check what data we can't retrieve. I do not have the API for
> Garmin so maybe using Garmin Connect we are missing some data. Check what data
> we can't retrieve that Garmin registers but Garmin Connect doesn't let us have."
>
> This document is the honest answer, per provider, verified against what the
> connectors actually fetch (see the payload lists in
> `app/connectors/garmin/fetch.py`, `app/connectors/whoop/fetch.py`,
> `app/connectors/oura/fetch.py`). It also names what the UI can never show
> from a given device and which secondary device fills the hole (the device
> priority law, `app/services/device_merge.py`).

## 0. The Garmin access situation (read this first)

There are **three** Garmins, and they are not the same thing:

| Path | Who can use it | What it gives | Our verdict |
|---|---|---|---|
| **Garmin Health API** (official, developer.garmin.com) | B2B partners with a signed agreement (it is the same class of gate as Technogym's b2b API) | Everything below plus webhooks | **Not available to us.** Registration requires a business, a reviewed use-case, and per-user agreements. Do not plan around it. |
| **garminconnect** (unofficial Python client, we use 0.3.x) | Anyone with Garmin account credentials | The same JSON endpoints the Garmin Connect web app itself calls | **Our primary path.** Login once (`tools/garmin_sync.py connect`), tokens stored encrypted, 6-hourly incremental sync + full backfill. It can break when Garmin changes payloads — the sync layer is version-tolerant and we already rode one breaking change (0.2 → 0.3 shape migration). |
| **FIT files** (exported per-activity binaries) | Anyone | The *device's own recordings* — full-resolution sensor data | **Our enrichment path** (`app/services/fit_enrichment.py`): laps and per-second dynamics that the JSON API hides get parsed from FIT and stored. |

The consequence: **the unofficial API exposes roughly what the Garmin Connect
web app shows — no more**. Anything Garmin computes app-side and only renders in
the phone app is invisible to us. The sections below say exactly where each
metric stands: ✅ captured · 🔶 partial (derived or activity-scoped only) · ❌
not retrievable.

## 1. Garmin — daily health / wellness

| Metric (as the watch records it) | Garmin Connect shows | We capture | Notes / gap-filler |
|---|---|---|---|
| Sleep duration + stages (deep/light/REM/awake) | ✅ | ✅ `sleep_sessions` | Full backfill to account age; Whoop/Oura secondary can fill nights the watch missed |
| Sleep score | ✅ | ✅ | Garmins own sub-score weights; not re-derivable for other devices |
| Overnight HRV (5-min readings + baseline) | ✅ | ✅ `hrv_readings` | The cleanest signal we ingest; identical semantics in Whoop/Oura after annotation |
| All-day (non-sleep) HRV spot readings | ✅ (app) | ❌ | API only serves the overnight window. No provider exposes this on demand |
| Body Battery timeline | ✅ | ✅ `stress_readings.body_battery` (5-min points) | **Body Battery *events*** ("workout X drained 30") ❌ — attribution is app-computed |
| Stress timeline | ✅ | ✅ 5-min points | Same |
| Respiration (day + sleep avg) | ✅ | 🔶 sleep + daily avg only | Per-minute respiration stream exists only in FIT during activities |
| Pulse Ox overnight avg + daily avg/worst | ✅ | ✅ avg values | **Continuous SpO2 curve** ❌ (app renders it, API returns aggregates; FIT carries it during activities) |
| Resting HR | ✅ | ✅ | |
| Steps / floors | ✅ | ✅ | |
| **Intensity minutes** (moderate/vigorous) | ✅ | ❌ today | Fetchable from the same stats payload — candidate backlog item for `daily_biometrics` |
| Calories (active / total / BMR) | ✅ | 🔶 activity calories only | Daily aggregates live in the stats payload we already download — same backlog item as above |
| Hydration | ✅ | ❌ | Flaky endpoint; manual logging mostly; low medical value |
| Skin temperature deviation | ✅ (app) | ❌ today | Present in the sleep payload variants; candidate backlog item (Oura exposes it cleanly and can fill via device law) |
| Weight / body fat (Index scale) | ✅ | ✅ `daily_biometrics` | Oura/Whoop do not do body-comp; manual entry covers gap days |
| VO2max + fitness age | ✅ | 🔶 activity-level VO2max | Daily VO2max/status endpoints exist but are login-scoped and shape-unstable |
| Training Status / Training Readiness | ✅ (app) | ❌ | App-computed composite. We compute our **own** readiness/recovery/strain scores in the feature engine (deliberately — provider-neutral) |
| HRV status weekly baseline | ✅ | ✅ rolling baseline stored per reading | |
| ECG (watch ECG app) | ✅ PDF report | ❌ | No endpoint, not even in the official API. If a reading matters, the owner exports the PDF to the lab/journal section |
| Breathing variations / health snapshots | ✅ (app) | ❌ | App-side feature |
| Women's health cycle logging | ✅ | ❌ | Deliberate scope cut for v1 |
| Meditation / breathwork sessions | ✅ (app) | ❌ | Connect+ feature |
| Golf / tennis / wheelchair metrics | ✅ | ❌ | Sport-specific, no API |
| Incidents / fall detection events | ✅ | ❌ | Safety feature, no API |
| **Strength workouts: exercise name, sets, reps, weight per set** | ✅ (app renders from FIT) | ❌ via JSON API | **FIT files carry it** — extending `fit_enrichment.py` to parse `set` records is the planned unlock. Until then the in-app gym tracker (session logs) is the system of record for strength work |

## 2. Garmin — activities

| Data | We capture | Notes |
|---|---|---|
| Summary (type, time, duration, distance, elevation, avg/max HR, avg/NP/max power, calories, training load, TE) | ✅ | |
| HR/power/cadence/speed/elevation/temperature/position streams | ✅ | Decimated for UI (`/activities/{id}/streams`), full resolution stored |
| Laps | ✅ | JSON + FIT enrichment (idempotent upserts) |
| Time-in-HR-zones, per-zone seconds | ✅ | |
| Weather per activity | ✅ | |
| Gear linkage + usage hours/km | ✅ | |
| **Running dynamics** (ground contact time, vertical oscillation, stride, balance, running power from wrist) | 🔶 | Present in FIT for compatible watches; parsed when present, absent otherwise |
| **Per-second respiration during activity** | 🔶 | FIT-only, when the watch records it |
| Course / navigation data, segments | ❌ | No API |
| Live tracking / incident feed | ❌ | No API |

## 3. Whoop (v2 OAuth) — what changes vs the watch

Captured (after the annotation law — see `whoop/normalize.py`): sleep stages +
score, **sleep performance/efficiency**, overnight HRV, resting HR, respiratory
rate, SpO2, skin temp, **recovery score (0–100)**, **strain (0–21)**, daily
calories, **workouts with per-activity strain** (sport autodetected), body
measurements (weight, HRmax).

Not available from Whoop: **no steps/floors, no GPS trace, no per-second
streams** (workout HR zones only), no VO2max, no body battery equivalent
(strain is *not* stored as training load — annotation law), cycle data behind
opt-in. Because of that the device law keeps Whoop as the **recovery/sleep
specialist** or main device for watchless days; a watch stays the source of
truth for anything spatial.

## 4. Oura (API v2) — same law

Captured: sleep stages + score + latency + efficiency, **sleep timing
(side/bedtime onset)**, HRV, resting HR, respiratory rate, SpO2, **temperature
deviation** (fills the Garmin skin-temp gap), **readiness score**, activity
score + steps + equivalence (km), VO2max estimate, menstrual cycle tags
(opt-in),Tags/notes.

Not available: no GPS, no streams, no workouts worth trusting (ring detects
activity poorly) — Oura never wins activity windows in the device law; it fills
**nights**.

## 5. COROS

Open API access is gated behind a manual developer-portal review. The connector
is a doc-first shell (`connectors/coros/`) with the OAuth flow implemented and
switched off until `COROS_CLIENT_ID/SECRET` exist. Expected coverage when
approved: activities + streams comparable to Garmin's official offering — i.e.
**better than nothing, thinner than garminconnect** (COROS' API does not expose
wellness-day aggregates at garminconnect depth). This stays honest in the
settings UI: COROS shows "Awaiting provider setup" until the owner is approved.

## 6. Strava / CSV

Strava: activities + streams only — no wellness. It exists to **cover activity
windows** (device law: "second device overrides the timeframe when the main
device recorded no activity") and to import rides shared from friends' gear.
CSV (Apple Health export): fills whatever the owner's phone sees — steps, HR,
weight — with sniffed column mapping, deliberately conservative.

## 7. The matrix the UI can honestly promise

*Every metric page in the UI renders from one table; the page header carries
the contributing sources (per `source_metrics` + `sources` arrays), so users
always see WHERE a number came from.*

| UI metric page | Primary table | Fallback chain (device law) |
|---|---|---|
| Sleep night | `sleep_sessions` | Garmin → Whoop → Oura |
| HRV | `hrv_readings` | Garmin → Whoop → Oura |
| Recovery/Readiness | `feature_scores` | computed — provider-neutral |
| Steps/floors | `daily_biometrics` | Garmin → Oura → CSV |
| Weight/body fat | `daily_biometrics` | Garmin (scale) → CSV → manual |
| Activity detail | `activities` + streams | Garmin → Strava → Whoop (gym) |
| Strain/load | `activities.training_load` + `feature_scores` | computed from HR/power, never Whoop strain |
| Skin temp | `source_metrics.oura` | Oura only |
| Strength sets | `gym_set_logs` | our gym tracker (Garmin strength sets = FIT backlog item) |

## 8. Backlog that would shrink this table

1. **Intensity minutes + daily calories + skin temp** from payloads we already
   download (schema + normalize + UI hours, no new endpoints) — highest value
   per line of code.
2. **FIT strength-set parsing** (`fit_enrichment.py` v2) — unlocks exercise
   name/sets/reps/weight matching Garmin Connect's display, feeding both the
   gym tracker history and the coach's session feedback.
3. **Continuous SpO2 + respiration during activities** from FIT streams.
4. **VO2max daily trend** via the login-scoped endpoints, behind a shape-check
   that degrades silently (we have been burned by 0.2→0.3 once; this one gets
   the same tolerant parser).
