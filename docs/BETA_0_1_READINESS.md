# Apex Health web beta 0.1 — release and owner checklist

8 October 2026. This is the current checklist. Earlier alpha/completion reports
are historical evidence, not proof that the live deployment works. Release
identity is available at `GET /version`; the image embeds its Git commit.
The beta covers the web application and tested ingestion contracts. It does
not certify health predictions, every wearable, or a signed native application.

## Confirmed defects fixed in this release

| Severity | Location | Observed behavior / reasoning | Fix and test evidence |
| --- | --- | --- | --- |
| HIGH | `backend/app/agent/loop.py:run_agent_loop`, `entrypoint.py:_history_messages` | The live recovery question retrieved data but exhausted its aggregate context budget. The tool-message cap could replace a weekly summary with handles alone, encouraging repeated evidence expansion. Failed assistant replies were replayed in later history. | Compact only redundant observation lineage/policy fields in the model projection; retain exact values, units, origin, acquisition, timestamps, availability and method/device metadata. Normalize read-cache arguments and reserve a final completion. Exclude failed history. Permit one bounded correction of rejected claims, with unchanged validation. Regression verifies real observation payloads survive the cap and a token-heavy turn closes with an answer. Earlier fixture replies had zero token usage and missed this. |
| HIGH | `backend/app/connectors/garmin/sync.py`, `tasks/lab_tasks.py`, `tasks/feature_engine.py` | Legacy gym rows had a strength discipline but no provider `type_key`/set metadata. Both repair selection and the fetch guard skipped them; manual repair did not request strength by default. | Recognize owned canonical strength disciplines as well as provider type keys; repair missing feeds by default. Reindex current linked raw summaries under the account lock and recompute calculations. Tests exclude foreign credentials, deleted sessions and obsolete raw revisions, and preserve recorded sets. |
| HIGH | `backend/app/connectors/garmin/sync.py` | One failed optional stream fetch raised after wellness normalization, preventing a successful overall checkpoint and repeatedly restarting a backfill. Successfully empty stream responses were also retried indefinitely. This is a confirmed code defect; old redacted live logs cannot prove it explains every historical failure. | Keep wellness success separate from the visible `activity_streams` failure. Failed streams remain retry candidates; successful empty responses are remembered. Integration test starts with a failing stream and verifies fresh sleep, advancing sync time, partial status and the remaining retry candidate. |
| HIGH | `backend/app/tasks/provider_sync.py` | The nightly run computes completed days, before most athletes wake up. Newly imported today's sleep/HRV/activity data did not trigger today's feature computation. | Refresh the preceding 28 days plus today after provider ingestion, using the account timezone and current profile. Do not display yesterday's score as today's. A timezone-boundary test verifies post-ingestion refresh follows successful persistence. |
| HIGH | `backend/app/tasks/provider_sync.py`, `tasks/lab_tasks.py` | Disabling sign-in did not stop new background provider ingestion or queued maintenance. | Exclude disabled accounts from scheduled fan-out, recheck before opening a provider client, and cancel disabled-account maintenance before processing. Tests verify no provider client or health processing is invoked. Work already in flight can finish its current operation; disabling is not source erasure. |
| MEDIUM | `frontend/src/features/sleep/SleepTimingChart.tsx` | Bedtime appeared below wake time; simply reversing the axis would collapse bars with the old height calculation. | Reverse the time axis and use positive coordinate-independent bar heights. Chromium verifies bedtime is above waking and a visible bar remains; Rome DST cases also pass. |
| MEDIUM | `frontend/src/features/overview/OverviewPage.tsx` | Recorded signals appeared below other sections. | Put them immediately after the Today/APEX decision card. Browser verifies the actual order. |
| MEDIUM | `backend/tests/test_lab_api.py` | The named credential-ownership test created no foreign credentials and depended on the owner not having an integration left by another test. | Establish an explicit foreign configured account and absent owner integration. The regression now works independently of test order. |
| LOW | `backend/app/core/logging.py`, `connectors/escalation.py` | Operational logs removed even safe error categories, preventing useful remote diagnosis. | Permit a fixed exception-code vocabulary only. Never persist arbitrary exception text, SQL, tokens, request arguments or health values in this buffer. Privacy test rejects arbitrary error-code text. |
| LOW | `backend/app/api/health.py`, `backend/Dockerfile` | The public site could not identify its installed commit. | Add an uncached public release identity containing version/stage/validated commit only. The authentication matrix explicitly permits this public endpoint and still probes protected routes. |

No new migration is required for these fixes. The current branch already
includes migration **0023**, which preserves reported lab reference intervals.
The populated upgrade/downgrade, ownership, source-deletion, scientific
registry, formula provenance, proposal approval, concurrency, retention and
telemetry suites remain part of release CI. Passing them is evidence about
the tested contracts, not proof of an unobserved production operation.

## Real-account verification

- Authenticated HTTPS login and the actual overview, sleep, metrics, activities,
  coach, provider settings and Data Health pages were inspected in Chromium.
- All three supplied original gym FIT files were uploaded to the owned account.
  Each reconciled to its existing activity; the activity count did not change.
  The live anatomy diagrams now render coloured recorded movement groups.
  Undetected exercises remain unknown; colour is not measured muscle activation.
- The failing recovery question was reproduced against the actual model. It
  failed with `BUDGET_EXCEEDED`, not a missing provider key or a network timeout.
- A four-week account-owned repair was requested through the durable outbox.
  A queued job is **not** a completed repair. Its actual outcome must be checked
  after installing the matching API and worker release.
- Fresh individual Garmin feeds coexist with an unsuccessful overall sync
  checkpoint. Do not reset the counter manually or claim successful backfill
  from fresh sleep alone. Confirm the first successful/partial run and inspect
  remaining feed failures after deployment.

No supplied password, session cookie, real health payload, private screenshot
or provider token belongs in this repository or its release artifacts.

## Release validation

- Production frontend build; English/Italian parity (1,463 keys); PWA tests.
- Full Chromium suite: 122 passed; one private-file test is opt-in and separately
  verified with the supplied recordings.
- Targeted final backend integration run: 79 passed, including auth matrix,
  real PostgreSQL normalization, stream recovery, coach budgets and ownership.
- Additional coach/security integration run: 102 passed. Private originals and
  disabled-account maintenance: five passed; original-recording browser: passed.
- Deterministic agent runtime evaluation: 26/26 passed. These are synthetic
  security/runtime evaluations, not evidence of clinical usefulness or a live
  model's answer quality.
- Full backend run before the final stream/disabled-account refinements:
  887 passed, one opt-in private-file skip, one newly public version-route
  expectation corrected. Final full-suite CI must pass on the release commit.

Production acceptance remains separate: verify `/version`, the live recovery
answer, maintenance completion, current calculation rows and both new UI
placements on the installed image. Do not call an old deployment beta-ready
merely because a newer GitHub commit passed tests.

## What only the owner can finish

### 1. Install the matching image if automatic deployment has not done so

Open `https://apex-health.it/version`. It must return JSON with `version: 0.1.0`,
`stage: beta` and the intended tested Git commit. HTML means an older deployment.
Both **API and worker** must run the same image. The remote application provides
no host shell or deployment control, so a stopped/misconfigured updater needs
host access.

For an updater-managed host, use your existing project/context/options:

```sh
python3 infra/auto_update.py status
python3 infra/auto_update.py doctor
```

Follow [AUTO_UPDATES.md](AUTO_UPDATES.md) if it is paused or unhealthy. When
recreating containers, preserve `.env`, volumes, all encryption/session keys,
original Compose files and `.apex-updater/active.compose.yml`. Do not replace
the pinned image with a local build. A generic `docker compose up --build`
is not appropriate for a managed pinned deployment.

### 2. Verify the real worker and overnight run

In **Settings → Data Health**, the requested repair must advance from queued
to running/completed, or display a specific recoverable state. If it stays
queued despite an online worker, inspect the host's **worker** logs and image:

```sh
docker compose --env-file .env -f infra/docker-compose.yml \
  -f .apex-updater/active.compose.yml logs --since 30m worker
```

Include any additional original overrides and omit the updater file only on
an installation that does not use it. Do not paste unredacted provider/token
logs into chat. If authentication is required, reconnect Garmin in Devices
and complete its MFA yourself; retry the same repair from Data Health.

Keep timezone **Europe/Rome** and one Celery Beat scheduler. The existing
hourly dispatcher selects the local 03:00 window; do not add a duplicate cron.
After the next 03:00 run, confirm yesterday and its preceding 27 days were
recalculated. New provider ingestion also refreshes today in this release.
Unavailable measurements/baselines can legitimately leave individual metrics
unavailable even after a successful job.

### 3. Confirm deployment facts and participant consent before invitations

The live notice has nonempty fields, but its AI processor, backup and transfer
descriptions list alternatives rather than one verified deployment. Replace
those alternatives with the actual enabled processors, actual backup regions
and actual transfer arrangements. See [LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md).
The notice says explicit health-data consent is requested before processing;
the current signup is not a dedicated recorded, withdrawable health-consent
flow. If relying on that basis, obtain and retain appropriate participant
consent before importing their data and provide a withdrawal process. Merely
filling environment variables does not create consent. Operator facts and
other people's choices cannot be supplied by an automated code review.

### 4. Verify recovery of your actual home-server backup

Confirm `BACKUP_ENCRYPTION_KEY` is retained separately, actual encrypted backups
exist, the retention settings match your intended policy, and an actual backup
can be restored to a disposable database. CI tests the restore implementation;
it cannot verify an inaccessible home-server archive or your offsite key.
Use [BACKEND_RELEASE.md](BACKEND_RELEASE.md) and the supplied restore drill.
Choose/configure Backblaze `B2_*` only if you want that offsite destination;
offsite upload is optional and is skipped when unconfigured.

### 5. Invite named testers and perform physical acceptance

After the checks above, create individual invite links in the owner Admin UI;
each tester connects their own provider account and selects their own profile.
Do not share the owner login. Have them verify a known sleep night, both GPS
themes, their own gym recording, metric stars, a recovery question, mobile
navigation and logout. Only they can judge their own wearable readings and
exercise detection. Report bugs with the in-app feedback control.

## Optional providers — configure only those you want to test

| Capability | Action and release boundary |
| --- | --- |
| Garmin Connect | Already connected on the reviewed account. No new key is needed. MFA/reconnect may require the account holder. Unofficial adapter; successful feeds are not evidence of official Garmin approval. |
| DeepSeek coach | The real model endpoint already responds. Do not replace keys merely to fix the budget bug. Daily spending limits are intentional; raising them is an operator choice. |
| Oura / WHOOP / Strava | Register the vendor application, set its client ID/secret and exact `https://apex-health.it/integrations/PROVIDER/callback`, then authorize a real device/account. Validate refresh/revocation and actual data. Strava is activity summaries only and remains excluded from AI evidence. Exact variables/scopes are in [VERSION_COMPLETION.md](VERSION_COMPLETION.md). |
| COROS | Requires an actual compatible account-scoped MCP server and the user's token, plus `COROS_MCP_*` configuration. This is not a direct COROS OAuth implementation. |
| Technogym | Requires partner access and approved endpoint/scopes. Leave dormant without them; delivery is not live-verified. |
| Fitbit nutrition | Requires `FITBIT_*` application settings and diary authorization. It is a food-diary integration, not full Fitbit wellness ingestion. |
| Apple export | Upload an actual Health export ZIP. Snapshot import needs no vendor key; SDNN is not overnight RMSSD. |
| Native HealthKit | Source and backend pairing exist. A Mac/Xcode, signing team and physical iPhone are required to build/run Swift tests and validate initial/delta/deletion/background/revoke behavior. No signed-device release is claimed. |
| Garmin watch | Read routes exist; physical Connect IQ validation is separate. Watch write actions and official Garmin delivery are not beta capabilities. |
| Email / Telegram | In-app notifications work. External owner delivery is currently unconfigured on the reviewed host, with a pending outbox. Configure and intentionally test it only if desired; notifications may include user-submitted support text. No test message was sent by this review. |

## Deliberately excluded rather than half-promised

- No paid third-party exercise database: recorded FIT enums plus conservative
  Italian/English aliases already support the gym workflow. Unknown exercises
  are not guessed from another person's notes.
- No arbitrary female score offsets or invented menstrual-cycle inputs.
  Sex/profile context and reported lab intervals are supported; shared
  formulas remain shared where the reviewed science does not justify a split.
- No conversion of proprietary provider scores into interchangeable metrics,
  calibrated injury/medical prediction, or muscle-activation measurements.
- Official Garmin ingestion/delivery, watch writes, full Google Fit sync,
  voice-upload/STT, scanned-document OCR and embedding-based retrieval remain
  future implementation work. Dormant adapters are not active product flows.
- The account export is a selected-table export, source deletion is not full
  account erasure, and upstream deletion discovery varies by provider. Do not
  promise complete rights handling or automatic propagation beyond tested
  contracts; the operator needs a process for full-account requests/backups.

Recommendation: **SAFE AFTER LISTED FIXES** for the web beta, after final CI and
installed-release acceptance. Native/device delivery and optional providers
remain outside that recommendation.
