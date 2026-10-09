# One athlete system

Apex stores optional, ordered gym/running/cycling priorities for each account. An empty selection is valid. Priorities order planning context and the daily hero; they never filter the discipline catalog, recorded activities, events, or legacy gym plans. No health answer is required. The five onboarding steps can be completed later, and the permanent free-text field is editable, exportable and deletable.

The existing stack remains FastAPI, SQLAlchemy/PostgreSQL, Redis/Celery and React/TanStack Query/i18next. The new implementation adds no runtime dependencies. Existing session authentication, CSRF protection, account scoping, encrypted documents, evidence eligibility, redacted audit records and typed change execution remain authoritative.

## Shared context and identities

`athlete_profiles` uses the account ID as its primary key. Profile writes carry `expected_revision`; stale writes return 409, and deletion retains an empty revision tombstone so stale editors cannot restore deleted notes. `/me` exposes the profile and effective AI state and accepts an optional nested athlete-profile update. Existing clients can omit every new field.

Dated profile targets have one existing `user_events` record per focus. Calendar and Coach read those same records. They are date-only: their local midnight timestamp is a storage boundary, not an asserted start hour. Edit/remove the target through Profile, including after timezone changes. Events created directly in Calendar remain supported for every existing sport.

Reviewed document drafts become `training_plans`/`planned_sessions` only after explicit confirmation. `/athlete/day` joins those identities with owned recorded activities, explicit activity-to-plan links and check-ins. Overview, Training and Activity Detail use the same API. Legacy gym day plans remain visible with their existing separate identity; Apex does not guess a link to recorded strength workouts.

Days use the account's timezone and UTC timestamp boundaries rather than trusting imported `local_date`. DST days can have 23 or 25 hours. Historical queries apply activation/supersession dates and retain completed/partial/skipped identities from superseded baselines. Importing a plan today does not invent its historical adoption.

A candidate association uses the same local day and sport, with recorded duration within 20% of a known planned duration. Candidates always require confirmation. Explicit links are owned and one-to-one; an athlete can keep an activity independent. Repeated check-in/association requests do not create duplicate sessions. Distinct workouts on one day remain distinct, including repeated runs and other sports.

Daily totals include only known duration, distance, ascent, calories and voluntary session-RPE units, with per-field coverage. No Garmin load, WHOOP Strain or TSS-style values are added together.

## Planning and review

Unanswered subjective flags remain unknown. Up to twenty owned daily check-ins, including explicitly reported RPE and bounded untrusted notes, are shared with coaching context with coverage/truncation metadata.

The shared deterministic constraints include ordered priorities, declared weekly time, local availability windows, rest day, events, life-event limits and self-reported pain/unwell context. Recorded activity duration replaces linked planned duration; unplanned activity time also consumes the day/week budget. Skipped sessions do not consume planned time. Completed or skipped workouts remain historical records; adaptations target upcoming sessions.

Protected workouts/plans reject mutation proposals. Activating another document baseline also rejects protected upcoming workouts until protection is explicitly removed. The day UI exposes that control. Protection changes advance the plan revision and audit the identity, without logging athlete text.

Adaptations remain minimal typed diffs, with original/proposed fields, reason, evidence, missing support, objective status, expiry, exact-hash approval/rejection, receipt and undo. A rest alternative defers the objective; other edits conservatively report it as uncertain. Apex does not claim that a shorter workout preserves a physiological outcome. Existing separate sport/provider load tracks remain authoritative.

## Migrations

| Revision | Additions |
|---|---|
| `0024` | Optional athlete profiles, version/provider-bound voluntary AI consent, atomic account/category budget ledger |
| `0025` | Encrypted versioned document drafts; active-baseline provenance; plan/workout protection and revisions; distance/time/intensity targets; owned activity links and session check-ins |
| `0026` | Unique optional profile-focus event mapping and date-only calendar semantics |

Upgrade with the repository's normal backed-up deployment migration process (`alembic upgrade head`). There is no consent backfill or mandatory profile backfill. A populated pre-feature plan survives upgrade and an empty-feature downgrade/re-upgrade in migration tests. Downgrading removes the new feature storage; export/back up any feature data first. Repository tests ran against disposable databases, not the configured live data volume.

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET/PUT/DELETE | `/athlete/profile` | Own optional context; revision-controlled writes/deletion |
| GET | `/athlete/disciplines` | Full existing sport catalog |
| GET | `/athlete/ai` | Own effective state, consent identity and daily/category budget |
| PUT | `/athlete/ai/consent` | Separate voluntary grant/withdrawal |
| GET | `/athlete/day?date=YYYY-MM-DD` | Account-local planned and recorded day |
| PUT | `/athlete/activities/{id}/association` | Explicit owned association or independence |
| PUT | `/athlete/checkins` | Revision-controlled shared-session check-in |
| GET/POST/DELETE | `/athlete/life-events[/{id}]` | Temporary declared schedule/readiness constraints |
| GET | `/lab/plan-drafts` | Decrypted owned reviewed structures |
| POST | `/lab/documents/{id}/plan-drafts` | Manual structure or authorized AI extraction |
| POST | `/lab/plan-drafts/{id}/confirm` | Exact reviewed baseline activation |
| PUT | `/lab/plans/{id}/protection` | Explicit plan protection |
| PUT | `/lab/planned-sessions/{id}/protection` | Explicit workout protection |
| GET | `/activities/{id}/endurance` | Current-input versioned running/cycling metrics |

Existing `/me`, `/events`, `/lab/documents`, changes and account-export endpoints are extended. The export includes athlete context, consent, budget ledger, plan drafts, plans, workouts, associations and check-ins; original document bytes remain individually downloadable in Documents.

## Product limits

Association candidates are suggestions, not completion evidence. Workout times and intensity targets can remain unknown. Historical comparison is deliberately `not_computed` until a compatible sport/source/unit/quality/context cohort exists. FTP and configured zones are current dated user assertions, not inferred or automatically maintained histories. Legacy gym templates retain their older identity and engine. This release adds constraints and minimal reviewable adaptations, not a new season optimizer or physiological prediction model.

See [ENDURANCE_METRICS.md](ENDURANCE_METRICS.md), [AI_CONSENT.md](AI_CONSENT.md), [TRAINING_PLAN_DOCUMENTS.md](TRAINING_PLAN_DOCUMENTS.md) and [ATHLETE_VALIDATION.md](ATHLETE_VALIDATION.md).
