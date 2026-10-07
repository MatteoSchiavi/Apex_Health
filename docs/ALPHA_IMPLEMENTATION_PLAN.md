# Alpha implementation ledger

## Verified baseline

- Repository: MatteoSchiavi/Apex_Health
- Branch: work
- Original checkout: 06c69adef99c4c20f300637cb4a3ff590886bf3f
- Starting implementation HEAD: af5a45b55ea3907e5842ce326856dd1e69e9c181
- Commit timestamp: 2026-10-07T12:05:36Z
- Commit: Add deterministic metric education disclosures
- Inspection timestamp: 2026-10-07T13:21:54.669400+00:00
- Working tree was clean. No AGENTS.md files found.
- Initial sandboxed fetch failed; approved sandbox escalation successfully fetched origin. `git ls-remote --symref origin HEAD` verified main / af5a45b55ea3907e5842ce326856dd1e69e9c181. Fast-forwarded work to current default HEAD before implementation.
- Read README, PERFORMANCE_LAB, STACK, AUDIT_2026_10, SECURITY, APPLE_HEALTH, COACH_SETUP.

## Reverified discrepancies

- SleepSession did not contain the source_metrics field already used by the Oura normalizer; additive migration 0020 fixes this actual schema mismatch.
- No generic sync_log table, persisted provider retry schedule or experiment-completion action exists; the implementation reports these limits rather than inventing them.

- A1 is confirmed: maintenance references nonexistent activities.metrics.
- Original checkout lacked B1 education files; fetched default HEAD contains the completed education architecture exactly as described. Initial discrepancy resolved by fast-forward. Preserve MetricExplanation/MetricEducationDisclosure and ACWR snapshot semantics.
- Existing DecisionRecord outcomes, typed drafts/approval, FeedState, provenance, source eligibility and durable jobs are established contracts to reuse.

## Ownership and integration

Lead owns migrations, ORM changes, scientific registry, provider semantics, agent tools, shared frontend API and security boundaries. Delegates may propose contract/schema changes, but only lead integrates them. Independent tests must not concurrently reset the shared database. No live provider/LLM calls or credentials required for normal CI.

| Task | Status | Implementation / verification | Remaining human dependency |
|---|---|---|---|
| A1 | DONE | Actual scheduled prune/VACUUM tested on migrated PostgreSQL; full activity plus canonical average HR required before removing old streams; incomplete rows retained. | None for code; operator owns backup/retention settings. |
| A2 | DONE | Repository-evidenced provider matrix, maturity API and badges; fixture coverage distinguished from live/production validation. | Real approvals and connector soak before changing maturity. |
| A3 | DONE | Reuses FeedState/Integration for per-feed attempts, success, measurement freshness, sanitized failure, real checkpoint and explicit unknown retry state. | Live outage/reconnect observation. |
| A4 | DONE | Fixed first-party event vocabulary, minimal metadata, owner aggregates, hooks for existing actions and telemetry retention. | Cohort interpretation. Experiment completion has no existing action; its reserved event is not fabricated. |
| A5 | DONE | Optional influence/usefulness and linked session outcomes reuse DecisionRecord; ownership/date checks, merge semantics and minimized event metadata. | Consented athlete feedback. |
| A6 | DONE | Explicit embedding owner FK/index, known-owner backfill, verified owner on write and owner-plus-source filters on search. Unknown legacy rows remain nullable and invisible. | Optional operator review of quarantined legacy vectors. |
| A7 | DONE | CI-executed regression tests for unsafe affirmative scientific copy; negations and historical migration documentation remain allowed. | Scientific review of future wording/formulas. |
| A8 | DONE | Dedicated free deterministic runtime-eval CI job, JSON/Markdown artifacts, release dependency; normal backend tests cover the answer boundary too. | GitHub workflow execution after a separately authorized push. |
| A9 | DONE | README/STACK/PERFORMANCE_LAB, lifecycle, provider, scientific, validation and manual-action documents reflect current code and limits. | None. |
| B1 | DONE | Canonical registry; neutral metric column migration; exact forward calculation snapshots and existing deterministic education adapter; missingness, source/method baselines and sparse-load fixes. | Prospective scientific calibration is explicitly outside alpha implementation. |
| B2 | PARTIAL | Complete backend/native source/web pairing implementation and automated backend/browser coverage; deterministic Xcode project and 11 Swift tests supplied. | Swift/Xcode build and tests, signing, physical iPhone/background-delivery validation unavailable on Linux. |
| B3 | DONE | 26 reference/attack scenarios through production loop and tools; epistemic taxonomy, exact numeric handles, lexical causal/medical safeguards, negative scorer tests and gated optional live command. | Paid live-model benchmark and semantic/clinical assessment were not run. |
| B4 | DONE | Daily interpretation before metrics, progressive evidence, preserved typed approval, replacement draft edits and intervention feedback. All five new browser cases pass. | Observe utility over the consented alpha period. |
| B5 | DONE | Real Garmin transport boundary with current unofficial implementation; explicit unimplemented official adapter and migration plan. | Garmin approval, credentials and supplied official schemas. |
| B6 | DONE | Source/method/context portability contract, unit conversion versus provider context, source-coherent HRV/sleep/resting-HR baselines; WHOOP sleep performance stays separate. | Device-identity metadata unavailable in legacy canonical HRV rows. |
| B7 | DONE | Actual table/hypertable/index and retention review; maintenance corrections and theoretical sizing without a cloud rewrite. | Measure alpha storage growth on the intended host. |

## Deliberate exclusions / skipped decisions

- Preserve the existing metric education UX, DecisionRecord, FeedState, scoped device tokens and typed draft executor; no parallel replacement abstractions.
- Do not reconstruct historical score constituents or guess historical sources. New exact records apply when a day is computed; old records honestly lack provenance.
- Do not turn unknown embedding ownership into guessed ownership or delete legacy vectors to force NOT NULL. They are quarantined from search; all new writes require verified ownership.
- Do not fabricate experiment-completed events without a completion action, provider retry state without durable scheduler evidence, live-provider maturity or paid-model quality results.
- Do not invent Garmin official wire schemas or treat Apple SDNN as RMSSD. WHOOP sleep performance is not a generic sleep-architecture score.
- Preserve original historical migrations and legacy audit documents as historical evidence; additive migrations implement current changes.
- No public SaaS, billing, cloud storage rewrite, App Store publication, autonomous approval or outcome-driven personalized model.

## Final integration validation (2026-10-07)

Runtime implementation commit: `37016b390f23b946adba185647e60f3c27969069`; subsequent documentation commits do not alter executable code.

- Complete migrated backend suite: **801 passed**, 140 warnings, 114.20 seconds. Fixtures exercise schema downgrade/base/upgrade/head and explicitly disposable PostgreSQL/Redis only; no concurrent reset runners.
- Free runtime evaluations: **26/26 passed**; all nine scorers pass for each reference/attack trace. Expected excessive-tool attack closes at its bound rather than converging. This is synthetic replay, not model-quality evidence.
- Complete Chromium suite: **95/99 passed** initially; all four failing new alpha/sync cases pass after correcting heading semantics/selectors, on one clean final targeted run (**4/4**). No remaining browser test failure. No second complete-suite run is claimed.
- All five decision-learning cases, exact calculation-record education, Italian mobile/accessibility and HealthKit pairing/revocation cases passed in that complete run.
- `npm run check:i18n`: **1,430 keys**, English/Italian parity. `npm run test:pwa`: **1 passed**. `npm run build`: TypeScript and production bundle pass.
- Updater: **27 unittest cases passed**. Python compilation and `git diff --check` pass.
- Native plists/scheme parse and Xcode project regeneration is deterministic. Swift/Xcode were absent: **11 supplied Swift tests not executed**.
- Production image `apex-alpha-review:local` built from the runtime commit: release auth/CSRF/invite/role/CSV/account-isolation smoke passes; four worker round trips pass; pending job survives Redis/worker restart; encrypted backup restores matching counts/checksums across **75 tables**, including ciphertext; SQL-error and interrupted-archive restores remain atomic.
- Local disposable release services were used; no live provider/LLM calls, public deployment or GitHub CI execution is claimed. Final delivery includes exact commands and commit list.

Earlier integration failures were corrected and followed by the complete backend rerun: provider aggregation SQL binding, JSON-null outcomes, composite contributor import, HRV provider selection import, scoped watch management, obsolete score/night assertions and retention fixture isolation. Golden formula expectations were independently derived from raw fixture data (GOLDEN_FORMULA_CHANGES.md).

Manual dependencies and post-validation decisions are recorded in [MANUAL_ALPHA_ACTIONS.md](MANUAL_ALPHA_ACTIONS.md). They do not substitute for implementable repository work.
