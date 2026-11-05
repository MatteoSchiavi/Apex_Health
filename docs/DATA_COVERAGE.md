# Data Coverage — what we can and cannot retrieve per provider

> Owner question: "Check what data we can't retrieve. I do not have the API for
> Garmin so maybe using Garmin API we are missing some data. Check what data
> we can't retrieve that Garmin registers but Garmin API doesn't let us have."
>
> This document is the honest answer, per provider, verified against what the
> connectors actually fetch (see the payload lists in
> `app/connectors/garmin/fetch.py`, `app/connectors/whoop/fetch.py`,
> `app/connectors/oura/fetch.py`). It also names what the UI can never show
> from a given device and which secondary device fills the hole (the device
> priority law, `app/services/device_merge.py`).

## Garmin API

The official owner Personal API is the only runtime connection. See
[setup and actual coverage](GARMIN_PERSONAL_API.md) and the
[26-endpoint inventory](GARMIN_API_COVERAGE.md).

Normalized: activity summaries, sleep, HRV, daily steps/resting HR/stress/Body
Battery observations, weight/body fat, supplied activity VO2max, and original FIT
samples/laps/recorded strength sets where present. Extra daily/profile/activity
feeds are retained as source documents; raw retention is not typed UI support.
Stress timeline, dedicated training readiness/status/recovery feeds and workout
upload are absent from the checked contract. The old 30-day cap is removed;
empty-gap history stopping is a heuristic. Explicit date-range maintenance is
available; API permissions, malformed FITs and missing provider records remain
visible limitations. Neither this table nor automated fixtures establish full
live-account delivery.

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
subject to the approved API scope. This stays honest in the
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
| Strength sets | `gym_set_logs` | local gym logs and recorded Garmin API FIT sets |

## Remaining Garmin projection work

Additional official feeds are archived before any new semantic mapping. Typed
metrics and UI for food, hydration, fitness age, cycle data, profile/HR zones and
other supplemental fields require verified units and source-aware projection.
Readiness/status/recovery and workout delivery require separately supported API
capabilities. Do not infer them from another Garmin product or a raw response.
