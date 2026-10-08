# Version completion and deployment checklist

Updated 8 October 2026. This supplements the dated alpha audit; it describes
the `version-completion` changes and separates repository work from checks on
the owner's actual installation. No production health account or server was
accessed. Synthetic tests do not establish live-provider or device support.

## Implemented in this change

| Request / previous gap | Delivered behavior |
| --- | --- |
| Activity calendar | 7 rows × 52 Monday-based weeks. Colour compares recorded workout duration with the busiest day in that displayed window. Click a date to filter activities. Zero recorded activity is not proof of inactivity. |
| Weekly streak | At least one recorded positive-duration workout per week. The current week's goal resets Monday; the preceding streak is retained until an entire week is missed. History outside the grid still contributes to the streak. |
| Sidebar | Collapsed initially; expands on pointer hover or keyboard focus. Navigation targets retain their height during expansion. |
| Favourite metrics | Account-owned stars persist across reloads/devices. Favourites is the first tab; Health and Training & recovery each contain three subgroups. Existing metric links still work. |
| Search | Pages, settings/training/metric/Lab tabs, metric names and up to 50 recently fetched owned activities. This is bounded navigation search, not exhaustive full-text search of every historical activity or private document. |
| Garmin status | Successfully available feeds no longer inherit another feed's generic failure. Recognized obsolete sync warnings are suppressed after an integration has recovered; genuine failures remain visible. |
| Sleep timezone | Hypnogram axis/tooltips and bedtime/wake charts use the account timezone, including Rome daylight-saving changes. |
| Sleep chart | Floating bedtime-to-wake bars show schedule consistency; the tooltip shows recorded time asleep separately. In-bed windows include awake time. Missing duration stays missing. |
| GPS maps | CARTO dark/light tiles follow the theme; route is white in dark mode and black in light mode. External map tile access remains necessary. |
| Strength import | Original FIT ACTIVE sets and Garmin's separate exercise-set feed populate completed sets, reps and conservative movement groups. Notes are stripped from display labels. Italian/English aliases and bundled Garmin FIT exercise enums are used. Unknown movements and ambiguous weight units remain unknown. |
| Overview | Readiness, Recovery, Strain and provider sleep score first; decision next; today plus seven-day activities, last night, compact steps/floors, load graph, supplementary recorded signals and yearly activity grid. At most one prioritized warning. Detailed decision feedback appears after a quick response; duplicated metric-value cards were removed from the decision. |
| Nightly repair | Existing Celery schedule now recalculates 28 completed local days and queues missing Garmin HRV/resting-HR/sleep and strength-set retrieval through the durable repair outbox. Completed missing-data checks are remembered for seven days. Manual repairs retain their original scope. |
| Report safety | Report persistence rechecks the input revision/account status after inference. Stale health content is discarded while actual inference usage remains accounted. Invalid grounded responses are not cached as verified reports. Clients close on scheduler exit. |
| Model configuration | Scheduled powerful-tier reports use the same endpoint resolver as the application; DeepSeek does not require a GLM key. |
| Oura | Mapping verified against public OpenAPI 1.41: sleep periods supply durations/stages/overnight HRV; daily_sleep supplies provider score. Typed observations retain raw lineage. Retiming, nap corrections and deleted periods remove obsolete owned values. Sleep timelines cannot borrow another provider's stages. |
| Watch safety | No current daily feature gives an unavailable assessment. An old feature is not repackaged as today's GO. This does not implement watch write actions. |
| Configuration/copy | Oura environment keys documented; unconfigured OAuth Connect controls disabled; deterministic daily report template supports EN/IT. Raw provider text is not automatically translated. |

No database migration or paid exercise-database dependency was added. Existing
AthleteEntry preferences, LabJob outbox, source semantics and account locks are
reused. The shared derivative deletion helper preserves the existing erasure
scope. Oura upstream deleted/rest periods also invalidate owned cached health
explanations rather than retain deleted measurements.

## Exact steps on your server

1. Deploy a revision whose complete CI has passed. Preserve `.env`, database
   volumes, `SESSION_SECRET`, `ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`, Compose
   project/context and existing override files. Never replace existing keys
   with values generated from the template. This change adds no migration;
   the existing chain remains at 0022.
2. For an updater-managed host, follow [AUTO_UPDATES.md](AUTO_UPDATES.md): run
   `python3 infra/auto_update.py status` and `doctor` with the original deployment
   options. Confirm the installed API and worker revisions match the intended
   tested image. Include `.apex-updater/active.compose.yml` when manually
   restarting an updater-managed stack; do not replace it with a local build.
3. For a manually built installation, from the repository root, including your
   original overrides/project/context:

   ```sh
   docker compose --env-file .env -f infra/docker-compose.yml up -d --build --wait
   docker compose --env-file .env -f infra/docker-compose.yml ps
   curl http://127.0.0.1:8000/health
   ```

4. Confirm Profile → timezone is `Europe/Rome` if you want 03:00 Italian local
   time. The shipped worker command includes `--beat`; one Beat scheduler must
   remain running. Do not install a second host cron for the same nightly job.
   The hourly UTC dispatch selects accounts in their local 03:00 hour (03:00
   for Rome, 03:30/03:45 for timezones with fractional-hour offsets).
5. Reconnect Garmin if Data Health requests authentication/MFA. At 03:00 the
   job computes yesterday and its preceding 27 days, even before account
   registration, then queues missing supported feeds. Inspect Data Health's
   repair-job status and worker logs; a scheduled task is not proof a provider
   returned measurements. To start immediately, use Data Health's bounded
   repair for the desired 28-day interval. Newly imported repair data triggers
   recomputation. Nightly automatic repair also attempts absent strength sets.
6. For existing raw history missing typed evidence, run Data Health's reindex
   first. Oura records already marked processed by the old incorrect mapper
   need provider replay: the old mapper consumed records without useful
   projections. Run the bounded operator replay below with your account ID
   and provider-day range. It preserves original raw records, replays only
   owned Oura sleep/score records in chronological order and recomputes that
   range. No upstream login or source erasure is necessary.

   ```sh
   docker compose --env-file .env -f infra/docker-compose.yml exec api \
     python -m tools.replay_oura --user-id 1 --start 2026-09-01 --end 2026-10-07
   ```
7. For calculation history older than four weeks, run the existing bounded
   operator tool inside the API container, substituting your actual numeric
   account ID and closed date range (maximum 366 days):

   ```sh
   docker compose --env-file .env -f infra/docker-compose.yml exec api \
     python -m tools.recompute_features --user-id 1 --start 2026-09-01 --end 2026-10-07
   ```

   This recalculates existing inputs; it does not retrieve missing upstream
   measurements. Recovery baselines need preceding comparable history, so
   missing support can still leave scores unavailable after a successful job.
8. Verify the browser's displayed dates, an actual 00:02 sleep start, known
   sleep score, both GPS themes, starred metrics after reload, a known Monday
   streak transition and your two original gym recordings. The recordings
   were unavailable in this workspace; attach them for exact parser verification.
9. Confirm HTTPS login, CSRF-protected writes, account isolation and sign-out
   on the actual hostname. Run the encrypted backup/restore drill on a
   disposable target and verify offsite recovery and key retrieval. Follow
   [INSTALL.md](INSTALL.md), [BACKEND_RELEASE.md](BACKEND_RELEASE.md) and
   [LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md) before inviting other athletes.

## Provider and service setup still required from you

Configure only the capabilities you will use. OAuth callbacks must match your
registered HTTPS URL exactly, including the actual proxy path. Restart both
API and worker after configuration changes; a disabled Connect control means
server configuration is missing, not that your wearable has failed.

| Capability | Owner action / remaining verification |
| --- | --- |
| Garmin Connect | Connect your own account in Devices, complete MFA, verify actual backfill, sleep, HRV, strength sets and session expiry/reconnect. Adapter is unofficial. Do not use owner-global credentials for other users. |
| Official Garmin Health/Training | Obtain actual program access, authorized contracts and permitted terms. Official transport is a raising placeholder; official ingestion/webhooks/workout delivery still require implementation. Optional future work. |
| Oura | Set `OURA_CLIENT_ID`, `OURA_CLIENT_SECRET`, `OURA_REDIRECT_URI=https://YOUR-HOST/integrations/oura/callback`; verify app scopes and authorize a real ring. Compare actual periods, score, HRV, corrections and provider changes. Continuous HR and undated profile weight remain raw-only; readiness/SpO2/temperature/stress are not fetched. |
| WHOOP | Set `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `WHOOP_REDIRECT_URI`; consent to the configured read/offline scopes. Validate paging, refresh, pending scores, revocation and Garmin coexistence. Proprietary WHOOP metrics are not interchangeable Apex/Garmin scores. |
| Strava | Register permitted app/athlete access; set `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI`. Verify paging, duplicates, refresh and deauthorization. Summary activities only; no streams. Strava evidence and restricted merged derivatives remain excluded from AI. |
| COROS via MCP | Supply an actual compatible account-scoped MCP server, `COROS_MCP_URL`, `COROS_MCP_ACTIVITY_TOOL`, `COROS_MCP_ACTIVITY_ARGS` and the user's bearer token. Verify schema, paging/history completeness and account isolation. This is not direct COROS OAuth. |
| Technogym | Requires eligible partner/B2B access, actual `TECHNOGYM_*` credentials/endpoints/scopes and explicit upload entitlement. Leave dormant without that access; delivery is unverified. |
| Fitbit nutrition | Set `FITBIT_CLIENT_ID`, `FITBIT_CLIENT_SECRET`, `FITBIT_REDIRECT_URI`; authorize nutrition. Test known and empty days, refresh and disconnect. Read-only external food diary, not full Fitbit wellness sync. |
| Apple export ZIP | Upload your actual iPhone export; test duplicate upload, timezone, overlaps and deletion. No vendor key. Manual snapshot; SDNN is not converted to overnight RMSSD. |
| Native HealthKit | Mac/Xcode, Apple signing team, entitlements, HTTPS API, iPhone permissions and one-use pairing. Run Swift tests and physical-device initial/delta/delete/replay/revoke/background checks. No signed native build or real background delivery was tested here. |
| Garmin watch | Build in Connect IQ and run on the actual watch. Read routes exist; `/watch/v3/day` and `/watch/events` write contracts remain absent. Set logs, feedback and other queued watch actions must be excluded from the release or separately implemented/tested. Read tokens must not gain write permission. |
| Original FIT/CSV | Supply the two actual gym FIT recordings and other chosen export formats. Synthetic CRC-valid FIT verified ACTIVE sets, unit scaling and normalized presentation; it does not prove your files parse. Unknown exercise/weight labels require evidence-based aliases or an explicit unit contract. |
| Chat / scheduled AI reports | Choose/configure DeepSeek, GLM or explicit supported tier endpoints; verify powerful-tier availability, access caps, grounded real answers, budgets and an actual scheduled report. Keys alone do not establish model output correctness. See [COACH_SETUP.md](COACH_SETUP.md). |
| Notifications | Configure only desired owner email/Telegram delivery and test it yourself. Channel setup is separate from wearable sync. No outbound message was sent in this work. |
| Weather | Verify selected location and external weather service availability if enabled. Historical/weather context availability is separate from recorded training evidence. |
| Hosting / backups | Verify actual domain/TLS/trusted proxy, API/worker revision, one Beat scheduler, Redis persistence, disk space, independent backup key, host permissions, offsite copy and disposable restore. The image/update pipeline targets Linux/systemd x86-64; ARM/non-systemd installation needs a separate build/operational path. |
| Privacy / pilot | Supply true operator/collection/retention/legal facts; demonstrate source/account erasure and withdrawal, including upstream and backup handling. Run a small consented pilot and record task completion plus multi-week provider failures/recovery. |

## Deliberately deferred or not claimed

- External exercise database: chose the bundled Garmin FIT catalogue and
  conservative aliases. No additional service key, license assumption or
  inferred clinical muscle-activation model. The body map remains movement
  groups, not an anatomical activation measurement.
- No fabricated resting HR from Oura mean/minimum sleep HR, no dated weight
  from an undated Oura profile and no guessed kg from an ambiguous number.
- No implementation of every Oura collection, direct Google Fit, official
  Garmin delivery, watch writes or native signing without verified contracts.
- No voice-upload/STT, scanned-document OCR or new embedding search: the
  existing adapters do not constitute active product flows. Coach uses local
  lexical retrieval; legacy embeddings of unknown ownership stay quarantined.
- No rewriting of proprietary scores as equivalent metrics. Apex estimates
  remain descriptive heuristics rather than validated clinical predictions.
- No claim that the two user recordings, real model output, physical devices,
  deployed 03:00 job or home-server backup operation were verified here.

## Validation record

Local verification:

- Full backend suite: **853 passed**. Subsequent final integration run:
  **94 passed**, including the additional Oura/Garmin awake-source boundary
  and malformed raw-timestamp regression. The new total collected by CI is 854.
- Full clean Chromium suite: **107 passed**, including both GPS themes,
  floating sleep-window calculations, chart resizing, metric stars, sidebar,
  feedback, keyboard navigation and accessibility checks. Final sidebar
  mouse-versus-keyboard focus behavior also received a targeted rerun.
- TypeScript/Vite build, **1,450 EN/IT keys** in parity and service-worker
  regression passed. Deterministic agent runtime replay: **26/26 passed**.
- Backend tests used disposable PostgreSQL/Redis; provider requests were
  mocked. FIT parsing used a real CRC-valid synthetic file, not the two
  unavailable user recordings. Overview screenshots were visually inspected
  at desktop and mobile widths. No live model/device/host proof is implied.

See the change's pull request and CI for the exact committed revision and
container release evidence. Earlier historical reports are not evidence for
newly changed code. The initial failed runs uncovered the unlabelled sleep
fixture, baseline warning regression and English-locale fixture dependency;
these were fixed and rerun. An overlapping browser output-directory failure
was corrected with isolated artifacts; it is not application verification.
