# Independent alpha-hardening review

Reviewed the complete `af5a45b55ea3907e5842ce326856dd1e69e9c181..25e6342ecc4f3b52bc6f198fbbf2629d7ecce1a7`
diff and its nine implementation/documentation commits. Findings below refer
to locations in **25e6342**, before the review fixes. Fixes are in the subsequent
review commit. Previous completion reports were treated as claims, not evidence.

**Recommendation: NOT READY TO MERGE.** The executable defects identified below
have focused fixes and regression coverage. Native Swift tests and an Xcode
build remain unexecuted, and the corrected branch has no verified production
image/release CI run. I have not merged or pushed main. Remote main was fetched
and remains `af5a45b`.

## BLOCKER

No independently reproduced BLOCKER code defect. Missing native/release
verification prevents a blanket merge recommendation; it is not evidence that
the native application fails to compile.

## HIGH

### H1 — Scoped native credentials gain watch authority on downgrade — FIXED

- Location: `backend/alembic/versions/0019_healthkit_bridge.py:42`.
- Behavior/risk: downgrade removed `device_tokens.scope` but retained active
  `healthkit_sync` token hashes. Earlier watch authentication has no scope
  distinction and can accept these credentials for private watch reads.
- Reproduction: seed separate watch/native tokens at head; downgrade to 0018.
  Before the fix, neither token is revoked. A scope removal must not grant a
  capability the native credential never possessed.
- Fix: revoke native tokens before removing scope; preserve watch tokens and
  existing revocations. Re-upgrade does not resurrect the native credential.
- Test gap: existing bridge tests checked current-head scope isolation, not
  populated rollback. Added a separate-database downgrade/re-upgrade regression
  to `tests/test_release_migration.py`.

### H2 — Concurrent provider writes lose canonical ownership and can deadlock — FIXED

- Location: `backend/app/connectors/garmin/normalize.py:155`, other provider
  normalization entry points, `backend/app/services/apple_health_import.py:217`.
- Behavior/risk: normalizers read and replace canonical JSON before acquiring
  the account evidence lock. A concurrent HealthKit transaction can lose its
  namespace/field attribution; Garmin can hold a biometric row while waiting
  for `changes`, opposite to HealthKit's lock order. This can also make later
  deletion clear a field belonging to another provider.
- Reproduction: hold an uncommitted account-locked HealthKit projection, then
  normalize Garmin stats in another PostgreSQL transaction. The normalizer
  must wait on the account advisory lock before reading/updating canonical rows.
- Fix: take the existing account lock first in Garmin, WHOOP, Oura, Strava,
  Technogym, COROS and CSV entry points; order Apple ZIP locks as
  `changes → apple_health_import`. FIT already used this order.
- Test gap: sequential normalizer fixtures could not catch this. Added real
  transaction/`pg_stat_activity` checks and persisted namespace/owner assertions
  in `tests/test_review_concurrency.py`.

### H3 — Computation, decisions and tool audits can restore erased derivatives — FIXED

- Locations: `backend/app/features/engine.py:762`,
  `backend/app/services/decisions.py:58`,
  `backend/app/agent/loop.py:151`,
  `backend/app/agent/entrypoint.py:118` and `:160`.
- Behavior/risk: reads and subsequent calculation/decision/audit writes lacked
  the erasure lock. Erasure could commit between those operations, followed by
  reinsertion of a score, decision or audit containing deleted observations.
  Mixed reads could also be labeled with a later snapshot revision. Taking a
  new lock only after chat-row writes introduces an opposite-order deadlock.
- Reproduction: hold `changes` in an erasure transaction; start computation,
  decision persistence or a bounded observation tool in another transaction;
  remove its inputs, then commit. The consumer must read after that boundary.
- Fix: lock before calculation/decision inputs and before tool retrieval through
  audit commit. Chat initialization takes `changes` before chat rows/locks;
  initial snapshot assembly also shares this boundary. Model calls occur outside
  these transactions. Reads for one account can now serialize at this boundary.
- Test gap: memory evaluation fixtures substitute locks and cannot demonstrate
  isolation. Added real PostgreSQL calculation, decision and tool-audit races;
  existing agent/draft integration tests also run with the corrected ordering.

### H4 — Unknown HealthKit sports merge with unrelated provider activities — FIXED

- Location: `backend/app/services/healthkit_ingest.py:254`, especially `:268`.
- Behavior/risk: a time/duration candidate was rejected only when *both*
  disciplines existed and differed. Unknown native sports and unclassified
  provider activities could merge on time alone. This contaminates provenance
  and can exclude a valid Garmin activity from AI by attaching a restricted
  native source link.
- Reproduction: upload workout type 3000 over a Garmin run, or a native run over
  an unclassified activity at the same time. Both previously reused the row.
- Fix: require a known native discipline matching the candidate's known
  discipline; otherwise retain a separate activity.
- Test gap: the existing matching-running case verified only the compatible
  path. Added both incompatible/unknown cases to `test_healthkit_bridge.py`.

### H5 — Metadata can forge or replace evidence handles — FIXED

- Location: `backend/app/agent/loop.py:245`; independent evaluation indexing in
  `backend/evals/scorers.py` had the same trust mistake.
- Behavior/risk: recursive traversal accepted observation IDs, analysis handles
  and analysis references anywhere in tool output, including arbitrary provider
  metadata. Nested data could mint evidence or overwrite a genuine handle.
- Reproduction: put `{id: observation:9:1, metric: resting_hr, value: 99}` inside
  an otherwise genuine observation's device metadata. A claim citing 9:1 was
  returned as verified despite no such observation being issued.
- Fix: stop at issued observation/analysis records; exclude free-form payloads,
  metadata and user assertions from handle discovery; validate handle shape.
  Expanded analysis evidence now preserves its registered recipe identity.
- Test gap: shape tests and prose-injection scenarios did not attack nested
  structured handles. Added observation/analysis/reference forgeries and an
  independent scorer mutation case. Existing evaluations alone would not have
  caught a trust error shared by runtime and scorer.

### H6 — HealthKit sample deletion leaves cached scores indefinitely — FIXED

- Location: `backend/app/services/healthkit_ingest.py:437`.
- Behavior/risk: tombstones removed source projections but retained daily and
  discipline calculations derived from them. An older night's deleted sleep
  could continue to appear as a non-null recovery/readiness/sleep score; nightly
  computation of yesterday does not repair historical dates.
- Reproduction: ingest staged sleep, compute its day, delete the source UUID,
  then query stored daily features. Before the fix the derived score survived.
- Fix: invalidate the affected calculation dates and their 28-day dependents.
  Sleep includes adjacent wake dates because episode grouping can cross midnight.
  Replays of the same acknowledged batch remain idempotent.
- Test gap: existing deletion tests asserted ledger/projection changes only.
  Added an actual compute → delete regression and window-edge assertions.

### H7 — Generic source erasure wipes explicitly owned other-provider data — FIXED

- Locations: `backend/app/api/lab_assets.py:549` and `:588`.
- Behavior/risk: Garmin/WHOOP/Oura/COROS/CSV erasure deleted *all* account wellness
  and every feed state. The new origin/field-owner contract contradicted the
  retained premise that all canonical wellness was unattributed legacy data.
  Erasing Garmin could destroy native HealthKit or WHOOP values, Oura HRV and
  another provider's permission-denied status.
- Reproduction: seed native HealthKit sleep/biometrics, mixed WHOOP-weight and
  Garmin-steps fields, Oura HRV and an Oura permission-denied feed. Erase Garmin.
  Before the fix these unrelated records were removed.
- Fix: erase matching-origin or genuinely unknown legacy sleep/HRV, clear only
  matching/unknown biometric fields, strip the erased provider namespace and
  delete only its feed states. Preserve explicit alternate ownership. Stress
  readings still have no origin and remain within the disclosed legacy scope.
- Test gap: the special native erasure path had preservation tests, but generic
  erasure had not been retested against the new provenance contract. Added a
  mixed-provider regression with fresh database reads.

### H8 — Wellness-only changes do not invalidate irreversible erasure approval — FIXED

- Location: `backend/app/api/lab_assets.py:444` (preview revision/hash), with
  `backend/app/services/evidence.py:362` (general evidence revision).
- Behavior/risk: the general revision does not fingerprint canonical wellness.
  Counts and that revision can remain identical after CSV/other canonical-only
  values change, allowing a deletion preview's old hash to approve changed data.
- Reproduction: preview Garmin erasure, change a Garmin-owned biometric value
  without adding rows or observation revisions, then submit the original hash.
  It must return 409 and require a fresh preview.
- Fix: serialize preview reads and stream a content fingerprint of the relevant
  wellness records. Reuse the native fingerprint helper rather than introducing
  another approval system. Native fingerprint order/contents are preserved.
- Test gap: prior stale-preview tests changed observation revisions, not
  canonical-only values. Added this same-count mutation to the erasure test.

## MEDIUM

### M1 — New CSV HRV masquerades as an eligible legacy overnight series — FIXED

- Location: `backend/app/services/csv_import.py:388` and `:397`.
- Behavior/risk: new generic HRV columns were written with null origin/method and
  `overnight_avg`. The intentional legacy-unknown path then admitted these new
  unspecified readings into recovery baselines without knowing RMSSD vs SDNN
  or overnight vs daytime context.
- Reproduction: import the daily CSV fixture; before the fix the new readings
  were eligible for the legacy recovery series.
- Fix: retain `csv_import` ownership, null method and `unspecified` context;
  exclude them from RMSSD calculations. Migration 0022 expands the existing
  constraint and refuses downgrade while these rows exist, preventing relabeling
  or loss. Historical unattributed readings are not retroactively rewritten.
- Test gap: the old CSV test explicitly expected invented `overnight_avg`.
  Updated it to test retained value, honest context, recovery exclusion and
  idempotency; populated downgrade refusal is tested separately.

### M2 — Nonpositive blend weights violate score bounds and coverage — FIXED

- Locations: `backend/app/features/scores.py:147`,
  `backend/app/metrics/provenance.py:21`.
- Behavior/risk: negative configured weights were included whenever their total
  was positive. Components `{a:1,b:0}` with weights `{a:2,b:-1}` produced 200/100.
  Zero-weight components were also reported as active/sufficient coverage even
  though the presentation correctly omitted their contribution.
- Fix: share a finite-positive weight predicate between blend and provenance;
  disclose inactive invalid/disabled weights. Invalid nonfinite weights are not
  serialized as JSON numeric provenance.
- Test gap: golden/registry tests used positive weights and could reproduce an
  invalid calculation from the same recorded components. Added bounds/coverage
  and strict JSON serialization cases for NaN/positive and negative infinity,
  plus fixed hand-calculated Recovery 64, Readiness 56, Strain 18 and ACWR 1
  examples that do not derive expectations by calling implementation helpers.

### M3 — Numeric membership does not verify a metric or prose unit — FIXED, BOUNDED

- Location: `backend/app/agent/loop.py:314` (numeric membership validation).
- Behavior/risk: an exact resting-HR claim of 50 allowed prose saying “HRV is
  50 ms.” The observation's actual unit could also differ from the quoted prose.
  Analysis claims did not validate declared units. This can turn a truthful
  structured value into an unsupported physiological statement.
- Fix: explicit English/Italian measurement bindings and common units are
  checked for the supported measurement labels. Baseline statistics borrow
  their metric/unit only from the registered baseline result. Unsupported
  analysis-unit assertions fail closed; boolean values cannot justify numbers.
- Test gap: the independent scorer had a few binding patterns but runtime did
  not. Added HRV/SpO2/weight/temperature misbinding, incompatible units and typed
  baseline positive/negative tests. An old fixture labeled an unlabeled median
  as HRV; it now supplies the actual registered metric/unit contract.
- Limit: this remains a lexical boundary, not proof of arbitrary paraphrases,
  causal truth or clinical safety. No semantic/clinical validation is claimed.

### M4 — Sync Health hides capability/permission states and overwrites missingness — FIXED

- Location: `backend/app/services/sync_health.py:22` and `:47`.
- Behavior/risk: `not_supported`, `not_exposed` and `permission_denied` became
  `unknown`. An old measurement timestamp could turn explicit `not_measured`
  or `pending_sync` into `stale`, hiding the persisted reason for missing data.
- Fix: retain all supported feed states; apply measurement staleness only to
  available/partial/complete states. Add matching English/Italian labels.
- Test gap: prior tests checked available→stale and redaction only. Added
  capability, permission, pending and missing-measurement cases.

### M5 — Native wire limits disagree with the server — STATIC FIX, NATIVE UNVERIFIED

- Locations: `ios/ApexHealthBridge/Sources/Core/Contract.swift:107`,
  `ios/ApexHealthBridge/Sources/App/BridgeModel.swift:41`,
  `backend/app/schemas/healthkit.py:48` (source identity) and `:38` (pairing name).
- Behavior/risk: the native client accepted a 100-character device name and
  500-character source names/bundles; the server accepts 60/256 respectively.
  A locally accepted request could fail with 422 and a queued upload could pause
  without an acknowledgement/anchor advancement.
- Fix: align limits, count Unicode scalars, reject empty source names and enforce
  pairing-code minimum length. Add source-identity boundary tests in Swift.
- Test gap: prior backend tests could not establish what the Swift client emits;
  the original Swift tests were never executed here. There are now 12 declared
  Swift test methods, with **zero executed in this review**.
- Required verification: run `swift test` and the documented simulator Xcode
  build on a Mac; then signed physical-device replay/deletion/permission and
  background checks. Do not treat static inspection as a passing native gate.

## LOW

- `docs/METRIC_EDUCATION.md:20` and its later “deliberate limits” described the
  pre-hardening registry/composite limitations as current. Marked it as history
  and linked the current registry contract. Updated registry documentation for
  unknown CSV context, weight eligibility, locking and deletion invalidation.
- `frontend/src/locales/en.json:536` and the matching Italian `synth` block
  retained unused diagnostic/autonomic and “optimal 0.8–1.3” claims. These keys
  have no active synthesis renderer, so this was not an observed UI defect.
  Replaced the unsupported copy with descriptive training context.

## NO ISSUE / reviewed boundaries

- Migrations 0017–0021 preserve existing signal values, avoid invented historical
  provenance and quarantine unknown embedding owners. The populated migration
  regression also exercises transactional rejection of older provider-ID
  collisions. Downgrades necessarily discard columns/tables introduced by the
  removed version; this is not a lossless rollback promise.
- `app/queries/search.py` checks both embedding owner and current source owner;
  legacy null owners do not appear in retrieval. No reproduced cross-user
  embedding leak. Concurrent duplicate embeddings remain a possible maintenance
  concern, not an ownership bypass demonstrated in this review.
- Recovery uses Apex sleep architecture, proprietary provider sleep performance
  stays distinct, and ACWR uses one selected load method for both windows.
  The method/coverage and heuristic floor are disclosed; ratios and fixed
  transforms are not clinical targets or injury predictions. No fabricated
  literature citation or statistical confidence was found in the registry.
- Current native auth checks scope, expiry, revocation and disabled accounts;
  pairing consumption, UUID immutability, batch-hash replay and checkpoints are
  account/device bounded. Cookies do not enter the native CSRF exemption.
- Typed proposal edits produce new reviewable hashes and supersede the old
  draft. Exact approval, ownership, changed-target/evidence rejection, receipts
  and undo integration cases remain enforced. No self-approval tool was found.
- Alpha events use fixed vocabulary and whitelisted IDs/provider/error/metric
  identifiers. Prompt, reply, symptom and raw-health payloads are absent from
  event metadata; aggregates are owner gated. This is separate from private
  health-bearing agent audit history, which has its own retention/erasure path.
- Stream retention uses real summary columns and preserves incomplete/no-summary
  streams, canonical activities and unprocessed raw payloads. Real PostgreSQL
  retention/task tests run; no cold-storage/partition policy is claimed.
- All 99 browser cases pass, including draft edits/approval, metric provenance,
  optional feedback, native pairing, provider status, responsive layouts and
  accessibility. These use synthetic API fixtures, not a deployed backend.

## Independent verification

- Backend full suite: **832 passed, 140 warnings**, 103.03 seconds, after all
  executable review fixes; `/tmp/apex-independent-final.log`. Earlier failures
  were corrected and followed by this full rerun. The warnings are existing
  deprecation/fixture warnings, not silently skipped test failures.
- Complete browser suite: **99/99 passed**, system Chromium, two workers,
  3.6 minutes; `/tmp/apex-independent-browser.log`.
- Deterministic runtime replay: **26/26 passed**, production loop/typed tools,
  synthetic memory fixtures; `/tmp/apex-independent-evals-final/`. These fixtures
  do not verify database isolation or observed live-model quality.
- TypeScript/production frontend build, English/Italian **1,433-key parity** and
  PWA test passed. `git diff --check` passed.
- Disposable PostgreSQL `hcc_test`/Redis test services only. Backend runners were
  serial. No live provider, paid LLM, private production data or public deployment
  was used.

## Completion claims that cannot be verified as stated

1. “Final implementation” / all completed tasks: the defects above contradict a
   blanket correctness claim. Native completion was already explicitly PARTIAL;
   source inspection cannot upgrade that status.
2. Prior backend/browser/evaluation numbers are historical reports. They do not
   prove current-head correctness; this review records new runs independently.
3. The claimed earlier image/worker/restart/backup/restore drill tested executable
   commit 37016b3. This review did not independently reproduce that release stack
   and it does not contain these review fixes or migration 0022. A new tested
   immutable production image/release CI run is still required.
4. Native compilation, Swift test execution, signing, actual permission behavior,
   physical-device replay/deletion and background reliability are unverified.
5. Live provider readiness/approval, provider soak results, paid-model reliability,
   athlete interviews, measured utility/benefit and clinical formula validity have
   no independent evidence here. Fixture success and declared support metadata
   cannot establish them; production support flags remain false.
6. Golden-fixture arithmetic can be checked against stored inputs/documented
   formulas, but the report's historical assertion that its author never used
   engine output to derive expectations cannot be independently reconstructed.
   New fixed-number examples and adversarial boundary tests supply additional
   independent evidence, rather than trusting that process claim.

## Deliberately not implemented / skipped decisions

- No new clinical calibration, statistical confidence, universal ACWR target,
  arbitrary-language semantic judge or automated physiological-benefit model.
  Those would be new features and require evidence not available in this review.
- No guessed legacy HRV/provider/device attribution or embedding ownership.
  Existing unknown legacy contexts stay explicit; new CSV data cannot enter them.
- No provider approval, official Garmin adapter, direct Google Fit connector,
  production-support badge promotion or native distribution claim without real
  credentials/build/device evidence.
- No architectural rewrite of the education disclosure, typed proposal approval,
  canonical activity merging, retention layout or deprecated `HRMAX_FALLBACK`
  compatibility export. Generic erasure still explicitly includes whole merged
  activities and unknown legacy wellness; reconstructing alternate projections
  is a separate design change, not performed silently during this review.
- No merge to main while native build/test and corrected-image release gates
  remain unverified. The review fixes stay on `work` for inspection.
