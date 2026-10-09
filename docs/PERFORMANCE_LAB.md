# Performance lab and agent runtime

The existing Documents review flow now supports encrypted, versioned training-plan drafts and explicitly confirmed active baselines. The deterministic day/session system and minimal adaptation review share those identities. See [TRAINING_PLAN_DOCUMENTS.md](TRAINING_PLAN_DOCUMENTS.md) and [ATHLETE_SYSTEM.md](ATHLETE_SYSTEM.md).

The current implementation uses the authenticated FastAPI/PostgreSQL/Timescale/
Celery platform and the bundled React/Vite UI. This inventory describes code
and deterministic tests, not private-alpha acceptance or validation on a
particular deployment.

## What ships

- **Today:** a deterministic training decision, measured evidence, coverage, comparable personal baselines, declared availability, pain/illness check-ins, event constraints, alternatives, limitations and durable outcomes. Incomplete evidence produces `collect_more_data`. Planning rules are versioned heuristics, not medical diagnoses or calibrated probabilities.
- **Data health:** per-metric availability, measurement/fetch times, source lineage, original immutable revisions, separate athlete annotations, device changes, manual measurements, original FIT and Apple Health ZIP imports, bounded repair/reindex jobs, original document downloads, exports and source-erasure review. The repository also contains an iOS HealthKit bridge and pairing API; Xcode signing, installation and live synchronization require external Mac/iPhone verification.
- **Lab:** robust personal baselines, recorded trend, separate multisport load tracks, session recording quality, sleep timing/debt against an explicit personal target, gym progression, experiments and matched observational associations, nutrition, recorded lab markers/reference ranges, reviewed documents, outcomes and daily/weekly/monthly/quarterly reports.
- **Calendar:** owned events with priority/taper, declared availability, upcoming sessions, exact session-change drafts, minimal deterministic replanning and downloadable workout descriptions.
- **Coach:** source-aware analysis and a separate Changes tab. A draft displays the exact diff, reason, evidence, expiry and approval hash. Approval applies a local change through the application executor; rejection and local undo have distinct audit receipts.
- **Notifications and gear:** durable in-app notification history, evidence/actions, deduplication, expiry, snooze, class mute, quiet hours and daily caps; equipment registration, maintenance and retirement.
- **Privacy and language:** encrypted original files/document text, explicit export whitelists, source deletion bound to a current preview, configurable observation/tool-audit retention, comfortable/compact spacing, account locale, English/Italian controls and deterministic decision explanations.
- **Scientific presentation:** metric values use neutral presentation; signal names and explanatory text distinguish observations and heuristic estimates from diagnosis or calibrated prediction. The language does not establish clinical validity.
- **Alpha utility measures:** an owner-only aggregate reports fixed-vocabulary usage events, weekly active users, AI users, proposal acceptance/edit/rejection rates, provider failure counts and user-reported decision influence. Event metadata excludes prompts and health payloads; decision influence is self-reported and is not a physiological benefit measure.

## Agent execution contract

The model receives these ten tools only:

| Tool | Scope |
| --- | --- |
| `data_get_coverage` | Owned availability and measurement freshness |
| `data_query` | Bounded eligible observations, activities, labs, journal or feedback |
| `data_get_evidence` | Expand an owned current observation or registered analysis handle |
| `context_search` | Bounded private lexical search of context, journal and explicitly reviewed documents |
| `analytics_run` | Registered deterministic recipe; optional durable background execution |
| `planning_get_constraints` | Owned sessions, events, availability and subjective constraints |
| `planning_preview` | Exact before/after plan diff with explicit prediction limitations |
| `changes_propose` | Create a typed, expiring reviewable draft; no execution authority |
| `jobs_get_status` | Owned durable job progress |
| `data_request_repair` | Bounded owned Garmin maintenance request |

Every tool uses a strict schema with unknown fields rejected. Identity, source eligibility and ownership come from the application. There is no model-facing approval, execution, arbitrary SQL, code runner, URL fetch or device-delivery authority.

The same bounded wrapper handles single and batched calls: eight iterations, 24 calls, 32,000 reported tokens, a 180-second turn deadline, a 45-second model-call timeout and 15-second tool timeouts. Up to four reads run in parallel; writes form serial boundaries. Database transactions close before model requests. Repeated writes are refused, and each call records an owned audit entry with redacted free-form inputs. Invalid provider/tool exceptions are sanitized.

Structured numerical answers require owned server evidence handles, exact values/metrics, and registered analysis field paths. Unsupported numerical replies are suppressed. Plain nonnumeric prose is labeled `narrative_only`; this is not a claim that every semantic assertion has been verified. Token costs are conservative estimates. The daily check limits estimated spend; it is not an atomic cross-request reservation or an invoice guarantee.

## Evidence and approval

Observations store origin, acquisition method, provider record key, measured timestamp, user local date/timezone, fetched timestamp, quality metadata, raw lineage and immutable revisions. A corrected provider summary creates a revision; an annotation never overwrites the provider record. Missing values remain missing. Coverage distinguishes `available`, `not_measured`, `not_supported`, `not_exposed`, `pending_sync`, `permission_denied`, `fetch_failed` and `stale`.

AI paths allow only known eligible origins. Strava-origin API data, unknown origins, and derivatives declaring restricted inputs are denied before snapshot/tool/report construction. A merged activity with an ineligible source link is conservatively excluded in its entirety from AI. Legacy report embeddings without the current eligibility marker are excluded. This policy is intentionally stricter than a source-label rename.

Approval binds the authenticated user, normalized typed payload, before/after diff, evidence handles, snapshot revision, reason and expiry. The executor locks the scope and target, recomputes the hash, checks current evidence/constraints and refuses stale targets. Repeated approval returns the existing receipt. Undo checks that later edits have not changed the target. Availability and pain/illness constraints are checked at preview and execution.

Local application, export and actual device delivery are different states. A JSON workout download is an exported description, not an assertion that a watch accepted it. No new notification is automatically sent to an external channel.

## Operations and migration

Alembic `0010_performance_lab` adds ten tables and owned tool audit IDs and extends the report type constraint for quarterly reports. Its DDL is frozen and independent of live ORM classes. Existing observations are not fabricated during migration. Use a bounded **reindex** job in Data health to index already stored Garmin raw history; repair fetches a requested date range and requires the authenticated account's active Garmin integration.

Celery beat dispatches committed job rows. Worker/account advisory locks prevent duplicate execution; cursors and heartbeat progress survive worker restarts. A stale running job can be dispatched again. Cancel is cooperative at chunk boundaries. Analysis result and completion commit atomically. Authentication failures retain the cursor and request reconnection. Source erasure refuses to race an active provider import; it disconnects the source, clears derived caches/notifications/job results and cancels outstanding jobs.

For existing non-HealthKit source paths, deletion intentionally removes a canonical activity linked to the source even if it has merged provenance. Wearable erasure removes source-owned wellness and legacy wellness of unknown origin; explicitly attributed other-provider wellness and feed states are preserved. The preview explains the scope. The native HealthKit path deletes its UUID ledger/projections, revokes native access and removes only its owned canonical fields or sole-source activities, preserving other providers and legacy wellness of unknown origin. Export includes active native records and excludes native tokens, pairing codes and batch receipts. Reconnecting can import upstream data again. Export responses disclose row caps; exported account data contains decrypted owned notes but excludes sessions and integration secrets. Downloaded private files must be stored appropriately by the athlete.

Observation and tool-audit retention are opt-in preferences for those two stores. They are not a promise that every original/raw record or applied-change audit is erased after the same interval; existing raw/stream retention and encrypted backup policy remain separate.

Alpha utility events use a fixed vocabulary and minimal whitelisted metadata.
The scheduled cleanup removes events older than 400 days. The owner rollup's
acceptance, edit and rejection rates describe proposal workflow. Its decision
influence rate counts yes/partly feedback among recorded yes/partly/no outcomes
for decisions created in the requested window; unanswered outcomes are
excluded. These are
usage and self-report measures, not product acceptance, causal evidence,
physiological outcomes or clinical benefit.

## Specification coverage and remaining work

| Master review area | Implemented boundary | Remaining work |
| --- | --- | --- |
| Canonical runtime | One authenticated service layer and bundled SPA | One supported runtime and deployment path |
| Reliable ingestion | Existing durable connectors; source-aware Garmin observations; FIT CRC/originals/overlap reconciliation; scoped repair/reindex | Official Garmin program approval, OAuth adapter and device-specific production validation |
| Provider metrics | Recorded available metrics with original units and honest missing states | Optional training-readiness/status/recovery feeds are `not_exposed` unless actually acquired; no proprietary reconstruction |
| Daily decisions/baselines | Coverage, robust baselines, subjective/event constraints, alternatives and outcomes | Prospective calibration, thresholds and patient/athlete-specific validation |
| Multisport/session quality | Separate known load scales, recording half-change measures, missing-stream checks, RPE and gym set trends | Workout-aligned interval compliance, defensible decoupling and additional sport-specific models |
| Event cockpit/replanning | Calendar, taper/availability constraints, one-session conservative drafts | Rich phase planning and constrained multi-session optimizer |
| Consequence simulator | Exact plan diff; physiological prediction explicitly unavailable | Forward-validated load/fatigue/recovery model and scenario comparison UI |
| Experiment engine | Defined windows/check-ins/confounders, matched observational associations | Prospective protocols and causal identification; associations do not establish causation |
| Plan-to-device closure | Local receipts and honest workout-description export; existing explicit Technogym path retained | Official Garmin Training API delivery, acceptance/sync receipts and supported compensation |
| Documents and search | Encrypted originals, explicit reviewed excerpts, private lexical search | OCR and sophisticated private semantic indexing; no remote embedding is required for the shipped path |
| Notifications | In-app durable rules and fatigue controls | Opt-in per-channel consent/verification and new email/push delivery adapters |
| Agent runtime | Bounded calls, owned audits, serialized drafts and durable analysis/repair jobs | Durable checkpoint/resume of an entire interrupted LLM conversation; atomic spend reservations; live-model evaluation telemetry |
| Localization/privacy | Bilingual UI/decision behavior, export/deletion/retention controls | Complete translation of every analytical/provider sentence and coordinated upstream/backup erasure |
| Apple Health companion | Pairing API, scoped device token, HealthKit ingestion contracts and Swift source project | Xcode build/signing, physical iOS install, background-delivery behavior and live synchronization on a Mac/iPhone |
| Alpha utility measures | Owner-only aggregates for fixed usage events, proposal workflow, provider failures and self-reported decision influence | Complete telemetry coverage, stable alpha cohort and evidence for product utility; these aggregates do not establish acceptance or health benefit |

These limits are deliberate release boundaries, not claims that personalization is calibrated or every roadmap item is finished. The repository and fixture tests do not establish live provider connection, complete delivery, provider approval, model quality, latency, spend or device acceptance. Verify each intended provider with its authorized account and target deployment.

## Fixed release cases

The deterministic set is implemented in `backend/tests/test_performance_lab.py`, `test_lab_api.py`, existing connector/agent tests and `frontend/tests/lab.spec.ts`. Keep the cases fixed and add every production failure.

| Required case | Verification |
| --- | --- |
| No HRV for seven days | Missing-evidence decision remains `collect_more_data`; no zero/diagnosis |
| Old record fetched today | Freshness uses measurement time |
| Garmin plus original FIT workout | Exact overlap yields one activity and two source links; heterogeneous channels survive |
| Unknown sport subtype | Original FIT sport is preserved; unmatched discipline remains unknown |
| Midnight/DST | User local dates and DST event boundaries |
| Revised provider summary | Immutable revision and duplicate-ingest idempotency |
| Garmin load plus other scale | Unknown load is unavailable; provider tracks are never summed |
| Missing power | NP and power half-change remain unavailable |
| Explain low readiness | Versioned deterministic inputs; legacy heuristic visibly labeled; no reconstructed proprietary score |
| Malicious document | Quarantined until review; untrusted text has no approval authority |
| Restricted Strava input | Denial before snapshot/tool and old derivative retrieval |
| Foreign ID | Authenticated HTTP ownership checks across drafts/files/jobs/notifications/evidence |
| Model approval call | Tool unavailable; no mutation |
| Context edit | Exact hash, application approval, receipt and undo |
| Retry | One import/change/result; no duplicated local side effect |
| Changed target | Conflict; no overwrite |
| Hanging single tool | Wrapper timeout and owned audit |
| Italian/English | Identical evidence/action authority; translated deterministic explanation and UI |

Release gates include schema downgrade/upgrade, backend regressions, production frontend build, translation-key parity and Chromium flows with light/dark, mobile and automated WCAG checks. Live model grounded-claim correctness, unsupported semantic claims, p95 latency and cost per completed task need a separate recorded production evaluation; no results are invented here.

## Earlier verification record

The previous project validation record reports 514 backend tests, 29 Chromium
browser tests and four GitHub CI jobs passing on 2026-10-04, plus targeted API,
migration and release smoke checks. That is a historical report for the tested
revision; it does not verify later changes, the current checkout, a live
provider, native iOS behavior or private-alpha acceptance. Re-run the release
gates for the exact revision and target deployment before making those claims.

Review screenshots use synthetic records: [Today](ui/performance-today.png), [Lab](ui/performance-lab.png), [Changes](ui/performance-changes.png), [Data health on mobile](ui/performance-data-mobile.png).
