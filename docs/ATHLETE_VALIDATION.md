# Athlete system implementation and validation

Implemented on branch `work` from `f9774bb`, preserving the initially clean repository and existing stack. The change spans optional athlete context, the shared calendar/day/session spine, reviewed document baselines, deterministic metrics, voluntary AI access and budgets, conservative adaptations, bilingual UI and regression coverage. No live deployment or external-provider verification is claimed.

## Results

| Check | Result |
|---|---|
| Full backend suite at the integration checkpoint | **964 passed, 1 skipped**; 144 existing dependency/test warnings |
| Final affected backend, agent, gym and migration regressions | **204 passed** |
| Final AI access/budget/agent/report regressions after exhausted-state and incomplete-usage changes | **131 passed** |
| Final running/cycling formula and provider-zone provenance regressions | **26 passed** |
| Final complete Chromium browser suite | **136 passed, 1 skipped** |
| Production frontend build | Passed (`tsc -b` and Vite) |
| EN/IT localization check | Passed: **1,777 keys in parity** |
| PWA/service-worker tests | **5 passed**, including new athlete/plan/endurance APIs remaining network-only |
| Whitespace/diff check | Passed |

The targeted backend reruns cover changes made after the full-suite checkpoint; their counts overlap and are not additional distinct tests. Both skipped cases are the existing opt-in original-private-FIT verification without supplied private recordings. Browser checks include WCAG 2 A/AA axe scans, 390px mobile and desktop traversal, light/dark themes and English/Italian. Early browser runs lost a reused development server or raced a page reload; the final complete run used its own fresh server and passed.

Tests used a disposable PostgreSQL database (`hcc_athlete_test` plus temporary migration databases) and separate Redis service. Existing configured application records were not reset or migrated. Providers in authorization/extraction/agent tests were bounded fixtures; no athlete text was sent to a live AI provider for validation.

For reproduction, explicitly point `DATABASE_URL` and `REDIS_URL` at disposable test services first, then use the repository's reset guard:

```sh
# From backend, with disposable database/Redis environment configured:
APEX_TEST_DATABASE_RESET=1 uv run --frozen pytest -q
# From frontend:
npm run build
npm run check:i18n
npm run test:pwa
CI=1 npx playwright test
```

## Covered behavior

- Optional zero/one/two/three ordered priorities, invalid values, client-tier manipulation, persistence, revision conflict, export and deletion tombstones.
- Shared date-only target events, profile-managed edit/removal, all existing sport visibility, multiple same-day sessions and repeated runs.
- Reviewed encrypted document draft/confirmation/revision, missing dates/durations, ambiguity acknowledgement, exact hash retry, protection and explicit baseline replacement.
- Planned/completed/partial/modified/skipped/unplanned states, explicit association, shared check-in identity, account ownership, historical supersession and local/DST boundaries.
- Recorded time replacing linked planned time, unplanned time consuming budgets, weekly/rest/life-event/window constraints, reviewable exact adaptation and undo.
- Consent absent/accepted/withdrawn/provider-mismatch/server-disabled, no unauthorized provider or embedding invocation, basic read-only authority, per-category pre-call exhaustion, atomic concurrent reservations, incomplete/failed-call accounting and effective disabled status on account exhaustion.
- Running/cycling numerical formulas, zero/non-finite/missing inputs, pause/stream/split coverage, dated configured zones, provider-specific zone provenance, confirmed/stale/future FTP and separate load units.
- Actual bounded agent runtime/evaluations, source eligibility, malicious document/tool authority cases and in-flight erasure protections.

## Product decisions and limits

Migrations are `0024`, `0025`, `0026`; all API additions and extensions are listed in [ATHLETE_SYSTEM.md](ATHLETE_SYSTEM.md). Existing account tiers remain stored as `cheap_only`/`full`, with effective `disabled`/`basic`/`full` access. Consent is never backfilled. Budget days reset in UTC; training days use the account timezone.

Daily associations require confirmation even when deterministic candidates exist. Missing values stay unavailable; protected upcoming workouts must be explicitly unprotected before a replacement baseline can activate. Manual plan review and local deterministic views work without AI. A shorter workout's objective is conservatively uncertain; rest defers it.

Historical endurance comparison is intentionally not computed without a compatible cohort. There is no FTP estimate, physiological prediction, injury-risk score, running-power estimate or diagnostic/medical claim. Legacy gym templates keep their older identity; this release does not replace the existing gym engine or implement a season optimizer. Configured zones and FTP are current dated user assertions, not a new assertion-history subsystem. Stream/lap limits reject dependent calculations instead of silently truncating evidence.

Deployment, physical AI-processing location, remote retention and operator legal-notice facts remain the operator's deployment responsibilities. Withdrawal blocks subsequent processing but cannot recall an already sent request or erase historical/backup/provider copies. No home-server, native-device or live provider smoke test was performed. See [AI_CONSENT.md](AI_CONSENT.md), [ENDURANCE_METRICS.md](ENDURANCE_METRICS.md) and [TRAINING_PLAN_DOCUMENTS.md](TRAINING_PLAN_DOCUMENTS.md).

## Logical commits

- `0c1d2e8` — feat: persist athlete priorities and gate AI with consent and atomic budgets
- `836b93d` — feat: add reviewed plan baselines and shared daily session identities
- `fc6691e` — feat: calculate versioned running metrics from recorded evidence
- `d47f1b2` — feat: add cycling power metrics with confirmed dated FTP gates
- `d695394` — feat: connect profile events and recorded sessions to shared training constraints
- `e5975db` — feat: support explicit dated zones and recorded cadence and timer inputs
- `766ebd5` — fix: gate embeddings and preserve uncertain AI charges with explicit consent fixtures
- `001e954` — fix: retain session history and require explicit protection removal for baseline replacement
- `e96782c` — fix: keep incomplete usage reserved and report exhausted AI access as disabled
- `72769cc` — feat: add bilingual progressive athlete context and shared daily session flows
- `8e3091e` — fix: identify the recorded provider partition in zone provenance

Documentation and this validation report are committed as the final documentation change.

## Modified files

- [.env.example](../.env.example)
- [README.md](../README.md)
- [backend/alembic/versions/0024_athlete_context_ai_consent.py](../backend/alembic/versions/0024_athlete_context_ai_consent.py)
- [backend/alembic/versions/0025_reviewed_training_baselines.py](../backend/alembic/versions/0025_reviewed_training_baselines.py)
- [backend/alembic/versions/0026_profile_calendar_events.py](../backend/alembic/versions/0026_profile_calendar_events.py)
- [backend/app/agent/entrypoint.py](../backend/app/agent/entrypoint.py)
- [backend/app/agent/loop.py](../backend/app/agent/loop.py)
- [backend/app/agent/routing.py](../backend/app/agent/routing.py)
- [backend/app/agent/tools.py](../backend/app/agent/tools.py)
- [backend/app/api/athlete.py](../backend/app/api/athlete.py)
- [backend/app/api/athlete_sessions.py](../backend/app/api/athlete_sessions.py)
- [backend/app/api/chats.py](../backend/app/api/chats.py)
- [backend/app/api/coach.py](../backend/app/api/coach.py)
- [backend/app/api/endurance.py](../backend/app/api/endurance.py)
- [backend/app/api/lab_assets.py](../backend/app/api/lab_assets.py)
- [backend/app/api/me.py](../backend/app/api/me.py)
- [backend/app/api/schedule.py](../backend/app/api/schedule.py)
- [backend/app/api/training_documents.py](../backend/app/api/training_documents.py)
- [backend/app/connectors/garmin/normalize.py](../backend/app/connectors/garmin/normalize.py)
- [backend/app/core/config.py](../backend/app/core/config.py)
- [backend/app/main.py](../backend/app/main.py)
- [backend/app/models/__init__.py](../backend/app/models/__init__.py)
- [backend/app/models/athlete.py](../backend/app/models/athlete.py)
- [backend/app/models/athlete_training.py](../backend/app/models/athlete_training.py)
- [backend/app/models/coach.py](../backend/app/models/coach.py)
- [backend/app/models/training.py](../backend/app/models/training.py)
- [backend/app/queries/search.py](../backend/app/queries/search.py)
- [backend/app/reports/periodic.py](../backend/app/reports/periodic.py)
- [backend/app/schemas/athlete.py](../backend/app/schemas/athlete.py)
- [backend/app/schemas/athlete_training.py](../backend/app/schemas/athlete_training.py)
- [backend/app/schemas/ui.py](../backend/app/schemas/ui.py)
- [backend/app/services/ai_access.py](../backend/app/services/ai_access.py)
- [backend/app/services/analytics.py](../backend/app/services/analytics.py)
- [backend/app/services/athlete_calendar.py](../backend/app/services/athlete_calendar.py)
- [backend/app/services/athlete_constraints.py](../backend/app/services/athlete_constraints.py)
- [backend/app/services/athlete_day.py](../backend/app/services/athlete_day.py)
- [backend/app/services/changes.py](../backend/app/services/changes.py)
- [backend/app/services/cycling_metrics.py](../backend/app/services/cycling_metrics.py)
- [backend/app/services/endurance_metrics.py](../backend/app/services/endurance_metrics.py)
- [backend/app/services/evidence.py](../backend/app/services/evidence.py)
- [backend/app/services/fit_import.py](../backend/app/services/fit_import.py)
- [backend/app/services/gym_advisor.py](../backend/app/services/gym_advisor.py)
- [backend/app/services/replanning.py](../backend/app/services/replanning.py)
- [backend/app/services/training_time.py](../backend/app/services/training_time.py)
- [backend/evals/harness.py](../backend/evals/harness.py)
- [backend/tests/helpers/ai.py](../backend/tests/helpers/ai.py)
- [backend/tests/helpers/domain_db.py](../backend/tests/helpers/domain_db.py)
- [backend/tests/test_agent_drafts.py](../backend/tests/test_agent_drafts.py)
- [backend/tests/test_alpha_events.py](../backend/tests/test_alpha_events.py)
- [backend/tests/test_athlete_context.py](../backend/tests/test_athlete_context.py)
- [backend/tests/test_athlete_training.py](../backend/tests/test_athlete_training.py)
- [backend/tests/test_coach_deepseek.py](../backend/tests/test_coach_deepseek.py)
- [backend/tests/test_cycling_metrics.py](../backend/tests/test_cycling_metrics.py)
- [backend/tests/test_migrations.py](../backend/tests/test_migrations.py)
- [backend/tests/test_performance_lab.py](../backend/tests/test_performance_lab.py)
- [backend/tests/test_release_coach.py](../backend/tests/test_release_coach.py)
- [backend/tests/test_release_migration.py](../backend/tests/test_release_migration.py)
- [backend/tests/test_report_erasure.py](../backend/tests/test_report_erasure.py)
- [backend/tests/test_reports.py](../backend/tests/test_reports.py)
- [backend/tests/test_review_concurrency.py](../backend/tests/test_review_concurrency.py)
- [backend/tests/test_running_metrics.py](../backend/tests/test_running_metrics.py)
- [docs/AI_CONSENT.md](../docs/AI_CONSENT.md)
- [docs/ATHLETE_SYSTEM.md](../docs/ATHLETE_SYSTEM.md)
- [docs/ATHLETE_VALIDATION.md](../docs/ATHLETE_VALIDATION.md)
- [docs/DATA_LIFECYCLE.md](../docs/DATA_LIFECYCLE.md)
- [docs/ENDURANCE_METRICS.md](../docs/ENDURANCE_METRICS.md)
- [docs/PERFORMANCE_LAB.md](../docs/PERFORMANCE_LAB.md)
- [docs/SECURITY.md](../docs/SECURITY.md)
- [docs/STACK.md](../docs/STACK.md)
- [docs/TRAINING_PLAN_DOCUMENTS.md](../docs/TRAINING_PLAN_DOCUMENTS.md)
- [frontend/src/components/data.ts](../frontend/src/components/data.ts)
- [frontend/src/features/activities/ActivityDetailPage.tsx](../frontend/src/features/activities/ActivityDetailPage.tsx)
- [frontend/src/features/athlete/AiConsentPanel.tsx](../frontend/src/features/athlete/AiConsentPanel.tsx)
- [frontend/src/features/athlete/AthleteProfilePanel.tsx](../frontend/src/features/athlete/AthleteProfilePanel.tsx)
- [frontend/src/features/athlete/ConfiguredZones.tsx](../frontend/src/features/athlete/ConfiguredZones.tsx)
- [frontend/src/features/athlete/EnduranceMetrics.tsx](../frontend/src/features/athlete/EnduranceMetrics.tsx)
- [frontend/src/features/athlete/LifeEvents.tsx](../frontend/src/features/athlete/LifeEvents.tsx)
- [frontend/src/features/athlete/PlanDocumentPanel.tsx](../frontend/src/features/athlete/PlanDocumentPanel.tsx)
- [frontend/src/features/athlete/SessionCheckin.tsx](../frontend/src/features/athlete/SessionCheckin.tsx)
- [frontend/src/features/athlete/YourDay.tsx](../frontend/src/features/athlete/YourDay.tsx)
- [frontend/src/features/athlete/types.ts](../frontend/src/features/athlete/types.ts)
- [frontend/src/features/coach/CoachPage.tsx](../frontend/src/features/coach/CoachPage.tsx)
- [frontend/src/features/lab/CalendarPage.tsx](../frontend/src/features/lab/CalendarPage.tsx)
- [frontend/src/features/lab/ChangesPanel.tsx](../frontend/src/features/lab/ChangesPanel.tsx)
- [frontend/src/features/lab/LabPage.tsx](../frontend/src/features/lab/LabPage.tsx)
- [frontend/src/features/lab/shared.tsx](../frontend/src/features/lab/shared.tsx)
- [frontend/src/features/lab/types.ts](../frontend/src/features/lab/types.ts)
- [frontend/src/features/legal/LegalPage.tsx](../frontend/src/features/legal/LegalPage.tsx)
- [frontend/src/features/overview/OverviewPage.tsx](../frontend/src/features/overview/OverviewPage.tsx)
- [frontend/src/features/settings/SettingsPage.tsx](../frontend/src/features/settings/SettingsPage.tsx)
- [frontend/src/features/training/TrainingPage.tsx](../frontend/src/features/training/TrainingPage.tsx)
- [frontend/src/locales/en.json](../frontend/src/locales/en.json)
- [frontend/src/locales/it.json](../frontend/src/locales/it.json)
- [frontend/tests/athlete-system.spec.ts](../frontend/tests/athlete-system.spec.ts)
- [frontend/tests/audit-ui.spec.ts](../frontend/tests/audit-ui.spec.ts)
- [frontend/tests/decision-learning.spec.ts](../frontend/tests/decision-learning.spec.ts)
- [frontend/tests/fixtures.ts](../frontend/tests/fixtures.ts)
- [frontend/tests/lab.spec.ts](../frontend/tests/lab.spec.ts)
- [frontend/tests/overview-refinement.spec.ts](../frontend/tests/overview-refinement.spec.ts)
- [frontend/tests/service-worker.cjs](../frontend/tests/service-worker.cjs)
- [frontend/tests/ui.spec.ts](../frontend/tests/ui.spec.ts)
