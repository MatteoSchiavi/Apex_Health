# Apex workflow and Garmin audit — 16 November 2026

## Setup and daily use

Athlete setup is one form: sports/priorities, optional goal, weekly time and rest
day, followed by one Save. It is designed for a 2–3 minute setup; that time has
not been established by a user study. Advanced Settings retains allocations,
seasons, availability, existing plans, sport context, FTP provenance, zones,
restrictions and free-form notes. Existing drafts, revisions, consent and plan
approval remain in place. Sleep baselines accrue automatically and no longer
block completion. Today has a direct Garmin Sync now action and retains the
existing workout and feedback shortcuts.

## Official API audit

Reviewed Garmin's published Personal OpenAPI 1.0.0 on 16 November 2026:
[Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
and the embedded `Garmin Connect Personal API` schema (26 GET data paths).
This review uses public contracts and synthetic tests, not a new live account
verification.

| Data | Finding and resulting behavior |
| --- | --- |
| Sleep duration, stages and score | Already mapped from official sleep fields. Provider sleep score stays separate from Apex sleep-architecture estimates. |
| Overnight HRV | Uses `lastNightAvg`, including summary-only nights, rather than averaging an overnight summary into its samples. Official baseline is a **range**, not an average: no synthetic `baseline.avg` or midpoint is invented. |
| Normalized power | Previously the endurance detail required dense streams despite an imported summary value. Detail now prefers Garmin's recorded value, with explicit recorded provenance. |
| Intensity factor, training stress score | Previously locally reconstructed with manual FTP; now preserve and prefer official activity-summary fields. Local fallbacks keep their formula/dependencies and separate units. Provider IF never enters a local TSS calculation with a different FTP. |
| HR/power zones | Preserve official `hrTimeInZone_*` and `powerTimeInZone_*` durations. No inferred HRmax/FTP zone boundaries. Zero-duration zones are retained in a measured partition. |
| Body Battery, daily stress | Already indexed from daily summaries, but absent from Today. Now displayed directly with source/date/sync time; no feature-engine run is needed. Body Battery is not labeled readiness/recovery. |
| Hydration | `hydrationValueInML` was discarded despite existing hydration UI fields. Now mapped to biometrics and source observations, and shown in Today. Missing intake stays absent; genuine recorded zero stays zero. |
| Readiness/status/recovery time | No dedicated paths in the published Personal schema. These remain unsupported. Apex heuristics retain their own names; they are not disguised as Garmin scores. |
| Invalid values | Non-finite/boolean numeric inputs and zero resting HR are rejected. Empty all-zero zone partitions and zero summary NP do not manufacture sensor metrics. |

Additional endpoint handling and remaining presentation opportunities (including the Garmin ingestion already on `main`):

- Activity detail and associated workouts are retained as source documents.
  Original ZIP/FIT downloads already provide validated samples, laps and recorded
  sets where available; native summary metrics remain useful without a valid FIT.
- HRV range exposes native weekly averages and status/baseline ranges. These
  are distinct from Apex's 30-day baseline calculations; daily HRV is normalized.
- Body Battery reports, daily heart rate and hydration/steps/stress ranges are
  already retained as source documents. Today uses normalized daily-summary
  fields without adding more remote calls. Dedicated within-day charts and
  hydration-goal interpretation remain presentation opportunities.
- Sleep summaries expose sleep need, naps and alignment. Sleep-need units need
  confirmation before display. Nutrition and women's health documents are
  retained when supplied/authorized by Garmin; they are not included in the
  short AI check-in evidence pack.
- Heart-rate zones, SpO2 acclimation, fitness age, profile settings, weight
  goals and wellness activities are retained as source documents. Canonical
  metric/chart coverage is documented separately in
  [the endpoint inventory](GARMIN_API_COVERAGE.md).
- The API is read-only. Reading associated workouts is not workout upload;
  aggregate exercise summaries are not individual strength sets.

The official ingestion already on `main` is preserved. The unofficial Garmin
library and its transitive dependencies have been removed
from the application dependency lock. Password/MFA UI, client and CLI login
paths are removed. Password payloads are rejected; the former connect URL is an API-key-only alias. Workers, agent
refresh tools and CLI sync all use the same Personal-only factory; legacy token
blobs fail closed with a reconnect instruction. Imported history remains intact.
Personal key setup remains owner-only; friend Garmin access needs the separate
Business integration. Reconnect old accounts through Settings, never copy old
session tokens into an API-key field.

## On-open AI check-in

`POST /dashboard/check-in` runs from the authenticated foreground application on
open/login and when a hidden tab returns to view, including entry through a deep
link. No timer, background refetch, catch-up job or midnight/noon job generates
these check-ins. An open tab does not generate just because noon passes. Today
renders the result only for the current day, with a maximum of three rendered
lines; historical day views do not relabel today's summary as historical data.

The server uses the account's IANA timezone. Morning is before 12:00; afternoon
is 12:00 or later. A durable `(user_id, local_date, slot)` primary key plus an
account transaction lock prevents duplicate invocations across refreshes,
concurrent requests, devices and worker restarts. A claim commits before remote
I/O; timeouts/failures consume the slot and never auto-retry. There are at most
two attempts per local day. No data or absent AI consent/access makes no call.

The cheap model gets a bounded evidence pack for today and the previous seven
local dates, with a 650-token output ceiling. Source eligibility, voluntary AI
consent, account access, budget reservations, usage accounting and numeric claim
validation apply. No journal/profile notes are sent. Source corrections or
erasure invalidate cached evidence; erasure scrubs content while retaining the
consumed quota. The retired scheduled daily task is a no-op for queued older
messages. Existing weekly/monthly/quarterly reports retain their separate
schedules and authorization policy.

## Installation and existing history

Deploy the API, worker and frontend together and run `alembic upgrade head`
(migration `0031`) before serving this version. Restart beat to remove the old
daily schedule. This code change does not install a production server revision.
New syncs populate the additional mappings; old imported summaries may require
a bounded re-fetch/replay before the new fields appear. Do not substitute zero
for unavailable historical data. Use the existing account-scoped data refresh
and repair workflow. The current Personal connector has no application-imposed
30-day history cap; actual availability still depends on Garmin and the account.
