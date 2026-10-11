# Reliability and planning implementation map

This map records the initial source audit for the reliability/UX/multisport request.
Production reports are user-provided context, not incidents reproduced in this workspace.
No production deployment, timer resumption or actual athlete-plan activation is authorized.

## Existing foundations

The repository already has ordered multisport profiles, optional onboarding, encrypted reviewed documents,
reviewable plan drafts, explicit activation, protected sessions, revision checks, canonical recorded activities,
confirmed plan associations, session check-ins and local-date/DST-aware day composition. Running/cycling
metrics have formulas, versions, dependencies, coverage checks and explicit missing-data reasons. Remembered
sessions already have persistent cookies, sliding renewal, absolute expiry, CSRF and server revocation.
Core deterministic functionality does not require AI.

## Confirmed source defects and implementation order

| Phase | Evidence | Smallest coherent change | Verification |
| --- | --- | --- | --- |
| 0 | `infra/auto_update.py::update` checks labels but stops before inspecting candidate migration compatibility | Immutable release/forward-migration preflight before any downtime, explicit paused recovery | Offline old-image/new-schema, missing graph, bad metadata, registry failure and recovery orchestration tests |
| 0 | GitHub CI container initialization failed from Docker Hub anonymous pull quota, including TimescaleDB after Redis mirror fix | Make release prerequisites resilient while retaining TimescaleDB/pgvector fidelity | Registry availability and workflow checks; no claim of a new release until CI passes |
| 0 | Existing owner Telegram sender is outbound-only; host controls are a pending requested extension | Private-owner allowlist, persistent replay cursor/outbox, shared deployment lock, confirmed disruptive operations, transition notifications | Offline authorization, replay, lock, delivery, health/recovery and generated systemd unit tests |
| 1 | `agent/loop.py::validate_answer` rejects valid whole-response fenced JSON; decimal binding differs between English and Italian | Strict envelope normalization and shared decimal interpretation without relaxing evidence | Realistic response-shape, qualitative conversation, valid/invalid measured-claim and correction regressions |
| 1 | `tasks/provider_sync.py` retries normal overlaps and reports partial ingestion as total failure; status API drops stream-failure counts | Distinct overlapping/partial/auth/persistent outcomes and explicit alert/recovery policy | Attempt timestamps, partial stream ingestion, retry/deduplication and status-contract regressions |
| 1 | Remember Me is implemented, but production persistence failure is unverified | Verify restart, proxy/cookie policy, expiry and revocation before changing auth | Isolated backend and browser restart journeys |
| 2 | `AthleteProfilePanel` lacks multi-day availability and keeps stale saved status after another edit | Bulk local-time editor, accurate dirty/save/conflict states, compact sections | EN/IT accessible profile save/reload, weekdays, exceptions, invalid ranges and failures |
| 2 | `athlete_day.your_day` and `YourDay` conflate no workout with no context | Server-authoritative context/plan/draft/rest-day state and precise next action | Profile/no-plan, pending draft, active rest-day, recorded/multiple activity and cache updates |
| 2 | Document workflow only extracts dated `ReviewedPlan`; recurring/context proposals are missing | One review journey separating confirmed profile proposals, recurring templates and dated activation | Mixed import saves context without activation; templates have no undated placeholder sessions |
| 3–5 | Legacy and new NP disagree on sparse streams; interval efforts pass steady-effort drift gates; daily distance combines sports | Shared eligibility, per-sport totals, canonical typed/versioned workouts and deterministic progression | Sparse/interval/missing-data tests, prior-30-day long-run reference and multisport integration |
| 6–7 | Progress, equipment/weather context and granular sharing are partially present or missing | Extend canonical records after reliability and planning release gates | Evidence/provenance/consent and appropriate product workflow acceptance |

## Evidence and limits

Focused isolated probes reproduced Coach fenced-JSON/Italian-decimal false rejections, interval drift eligibility,
and legacy normalized power from two samples. Existing pure running/cycling tests passed (16 and 10 cases).
Audits did not reproduce production browser/proxy behavior or execute production updates. Backend test fixtures
truncate tables and reset schema/Redis; integration runs must target dedicated disposable infrastructure.

Readiness remains conditional on actual tests, image publication and owner verification of the paused server.
Infrastructure scripts require a deliberate host checkout update/reinstall; publishing an application image does
not update those installed scripts. Changes must not resume automatic updates or overwrite production state.
