# v0.1 daily-use audit and release candidate

Audit date: 17 October 2026 (Europe/Rome). Production baseline:
`5d516d4274a4cf4227466f7b8de1732b94674243`, verified through `/version`.

## Product acceptance target

An invited athlete should be able to connect their available source, understand
which data is current, review a dated training plan, open today's workout,
record its completion, and obtain useful coaching without losing work or
searching through research/administration screens. A tested release candidate
is separate from an installed production release and from physical-device validation.

## Audit method and boundaries

Actual Chromium navigation used the authorized account on `apex-health.it`,
including real account data. The audit opened Overview, plan review, Training,
Coach, Activities and activity detail, Sleep and night detail, Health metrics,
Calendar, Gear, Challenges, Lab tabs, and Settings. It exercised one real Coach
request and generated one unconfirmed gym draft. It did not activate a plan,
record fictitious completed exercise, remove existing data, invite people,
change health/AI consent, or send external messages. Screenshots and session
state are private workspace artifacts outside Git; no credentials or health
measurements belong in this report or fixtures.

Reading a section is not proof that every mutation works. Write-heavy flows
are verified separately using synthetic accounts and disposable databases.
Provider authorization, actual device delivery and the installed production
revision remain explicit acceptance checks.

## Confirmed findings and fix plan

| Priority | Finding and user consequence | Evidence | Workstream / acceptance |
| --- | --- | --- | --- |
| P1 | The primary plan-review action opens a long Lab Documents page. An undated draft cannot be activated, but the next required action is unclear. | Live Overview → Review plan draft → Documents | Dedicated Training plan workspace, draft readiness and explicit missing dates; review/activation remain separate. |
| P1 | A normal request combining recovery, recent training and the uploaded plan produces no useful coaching. | Live Coach receipt: `UNCITED_NUMERIC_TEXT`, successful tools, correction not attempted | Fix bounded correction and routing; preserve exact evidence checks and proposal approval. Repeat synthetic harness regressions; live model acceptance after deployment. |
| P1 | Completing all gym sets can leave the daily overview saying the session is planned. | Code: inconsistent status names, missing final-set status transition and cache invalidation | Validate/log sets transactionally, update completion status, refresh all relevant views. Verify reload and multi-page consistency. |
| P1 | Historical gym links open today's session. | Code: historical YourDay links omit date; Training hardcodes today | Preserve selected date, visibly distinguish history and prevent accidental historical edits. |
| P1 | A failed Coach request overwrites a follow-up draft typed while waiting. | Code: unconditional onError restoration while composer remains editable | Preserve follow-up, retain original failed question with explicit retry; regression covers recovery. |
| P1 | Data health says a feed is not measured while the same page's coverage table has current values. | Live Settings → Data health | Reconcile actual feed/value state and account checkpoints; expose an actionable recovery link. |
| P1 | Gym set logging permits invalid/duplicate state transitions and inconsistent completion counts. | Code audit during training workstream | Server validation, idempotency/concurrency and tenant-boundary regression tests. |
| P1 | Generated holds such as planks use repetitions for a duration target. | Live generated gym draft plus catalog defaults | Store seconds separately from repetitions, preserve historical records, and exclude timed holds from rep totals, lifted volume and estimated maximums. |
| P2 | Mobile training and coaching require opening More; desktop labels disappear and the layout moves on hover. | Live navigation and source | Four direct daily destinations; stable visible desktop labels; retain other sections and search. |
| P2 | Sync failure warnings are buried among metrics and have no direct recovery action. | Live Overview | Place actionable notice near today's workout; link to current sync diagnostics and retry connection. |
| P2 | Plain Italian training analysis is routed as medical intent. | Code: bare substring `analisi` | Phrase/boundary matching with real medical triggers preserved; retain classifier intent on fallback. |
| P2 | Sleep provider scores are labelled as Apex calculations; inconsistent bed-window inputs can show 100% efficiency. | Live Sleep list/night and source | Distinguish device estimates; do not derive confident efficiency from inconsistent inputs. |
| P2 | Activity rows say Unknown despite available source sport metadata. | Live Activities plus normalization/schema review | Show the recorded provider label when canonical sport is absent; never infer a sport or rewrite history. |
| P2 | Challenges show blank dates for all-time scope and Join even for members; rankings are not reachable from joined challenge cards. | Live Challenges plus API/UI review | Explicit scope/membership and working leaderboard entry. |
| P2 | Reports expand a long archive and display technical policy identifiers. | Live Lab → Reports | Keep latest readable, collapse archive entries, explain legacy verification state in normal language. |
| P2 | The gym table clips exercise targets on a phone. | Candidate screenshot inspection at 390px | Show exercise cards with visible sets, targets, rest and completion on small screens. |

## Work order

1. Repair loss of work, completion state, evidence handling and inconsistent data states.
2. Integrate the daily workflow: Training owns plan review and execution; Coach
   links to the same planning/proposal paths; navigation makes these discoverable.
3. Run targeted regressions, full backend and browser suites, deterministic
   agent evaluations, production build, localization/PWA and release checks.
4. Retest the built candidate at desktop and phone widths, including the actual
   synthetic backend for plan review, workout logging and persistence.
5. Create a reviewable release candidate. Verify deployment identity and repeat
   the real Coach/plan/workout journeys on the installed revision before calling
   the live site ready for friends.

## Remaining product scope

Optional integrations whose provider setup is absent must remain clearly
unavailable. Fitbit nutrition, partner integrations and native HealthKit/watch
support cannot be certified by mocked browser tests. Real training choices,
plan activation and consent remain athlete decisions. Garmin's historical
failed attempts require diagnosis and a completed account sync still needs
verification; incoming measurements alone do not establish full sync success.

## Verification log

Candidate: [PR #5](https://github.com/MatteoSchiavi/Apex_Health/pull/5).
Verification continued on 23 October 2026. No production deployment is implied
by these results.

- Production frontend build and TypeScript check pass; English/Italian have
  2,549 matching translation keys. All five PWA tests passed on `405256c`;
  the final combined revision runs them again in CI.
- The complete GitHub Actions run for `405256c` passed 1,412 backend tests
  and 248 browser tests, with one intentional skip in each suite. Its frontend,
  pytest, agent-evals, updater and backend-release jobs all passed. Subsequent
  fixes require a fresh successful run on their exact commit.
- All 26 deterministic Coach evaluations and all 81 updater tests pass.
  Installer shell validation and generated systemd unit verification pass.
- Actual Chromium with the built SPA and a synthetic account on a separate
  FastAPI/PostgreSQL/Redis stack verified explicit date review and plan
  activation, gym confirmation, repetition and timed-set logging, completion,
  persisted state after reload, and desktop/phone layouts.
- The 23 October synthetic onboarding check passed over real local HTTP,
  PostgreSQL and Redis: invitation redemption, profile persistence without
  granting AI consent, empty states, reusable invitation after an email
  conflict, source review, explicit plan activation and persistence after
  logout/login. The release smoke now continuously checks profile/consent,
  plan activation, completion, rejected stale edits and account isolation.
- Follow-up browser regressions cover legacy missing-set recovery, workout
  completion from its detail screen, historical activity context, mismatched
  identities, saved-vs-local check-in review and existing-email recovery.
- A real backend plus 390px Chromium acceptance run verified a new friend's
  invitation signup, initial Overview, workout completion and persisted
  feedback after reload, with no page errors or horizontal overflow. Plan and
  profile setup for that run used the API and is not claimed as a complete UI
  onboarding journey. Screenshots prompted a shorter check-in with optional
  feedback collapsed and saved plain-text workout descriptions shown directly.
- A separate database migration probe verified upgrade from populated 0029,
  preservation of historical reps/weights, the new in-progress state and
  timed records, atomic rejection of a lossy downgrade, and safe downgrade
  and re-upgrade when no timed records remain.
- Final full-suite and production-stack gates run in the PR's GitHub Actions
  workflow, including API smoke, worker restart, backup/restore and failed
  restore atomicity. Consult the current PR revision's checks; previous runs
  do not certify a later commit. A Redis registry quota failure was resolved
  by using the verified public image mirror for CI.
- The 23 October final run exposed a date-dependent test fixture: its fixed
  September measurement had aged out of the rolling 30-day query. The test
  now requests an explicit end date. A separate frontend run exhausted its
  job timeout while downloading Chromium OS dependencies; setup now has a
  larger allowance while browser execution retains its own 10-minute limit.
- All five release checks subsequently passed on `a9482b5`, including the
  production-stack smoke, workers and encrypted backup/restore. The later
  association-recovery change passes its production build and 12 focused
  browser tests locally and requires its own complete CI run before release.

## Self-assessment: what was actually covered

The route inventory and the main daily workflows have been reviewed. Every
line, integration and possible user state has not been exhaustively audited.
Finding more defects during this second pass is evidence that the list is
iterative, not proof that all defects are now known. Automated regressions
establish specific behavior; they do not establish product usefulness for a
new athlete or successful delivery to a physical device.

| Feature group | Evidence established | Acceptance still needed |
| --- | --- | --- |
| Overview, navigation and data freshness | Live read/navigation audit; responsive browser regressions | Installed-candidate phone navigation and current Garmin account completion |
| Plan import, explicit dates, review and activation | Built SPA with real disposable API/database; reload verified | Athlete's intended plan and actual source documents |
| Gym workout execution | Built SPA with real disposable API/database: confirm, repetitions, seconds, completion and reload; migration preservation probe | Actual athlete workout on installed candidate |
| Coach and proposed changes | Live failure reproduced; routing, bounded correction, consent and evidence regressions; deterministic evaluations; UI recovery tests | Useful response from the configured live model after deployment |
| Activity, sleep, health, calendar, gear, challenges and Lab | Live read audit; backend and browser regressions | All write variants have not been exercised through the real UI/backend together |
| Invitation, login and account isolation | Production-stack smoke plus real local onboarding/profile/plan persistence; roles, CSRF, isolation and logout | Full first-use UI journey and owner-controlled invitation of actual testers |
| Profile, consent, check-ins, sharing, exports and account deletion | Backend tests and browser contract coverage where present | Combined real UI/backend journeys, especially recovery and revocation |
| Owner administration and deployment | Owner UI read audit; updater tests, production-stack worker restart and encrypted backup/restore checks | Installed host updater status, migration preflight and running revision |
| Provider connections, phone/watch and external notifications | Connector fixtures and configuration/availability checks | Actual provider authorization, device delivery and physical-device behavior |

All 16 findings in the original table have corresponding implementations.
That means the scoped fix list is implemented, not that every row has passed
live acceptance. The 20 October review found four further concrete issues:

1. A legacy gym session with set 2 saved and set 1 missing repeatedly submits
   the already saved set. Return the first missing set number and preserve
   historical log values.
2. A conflicting check-in edit can repeatedly submit a stale revision. Keep
   local edits, reload the current saved values and require an explicit choice
   before saving again.
3. Joining with an already registered email reports generic login failure.
   Explain that the account exists and direct the user to log in.
4. The primary workout detail destination exposes instructions and export but
   no completion action. Put the existing completion/feedback form beside
   that workout, using its exact date, session and associated activity.

The final screenshot review also shortened that form to the session result,
optional effort and note, with other feedback behind an optional disclosure.
Workouts without structured blocks now show their saved description and
planned duration rather than only explaining that no blocks exist.

These follow-up fixes and their targeted regressions belong to the same PR.
The final combined commit must pass all release checks before deployment.

A focused independent review on 23 October found one additional recovery
case: publishing a refreshed activity association could unmount a conflicting
check-in before the athlete chose which edits to retain. The review now keeps
the refreshed day private until the athlete uses the saved version or saves
their edits. Writes retain the opened workout/activity as their stable target;
reassociation cannot redirect a workout's note to a different workout. A local
"skipped" result remains visible but requires an explicit valid result when
an activity has since been recorded. Browser regressions cover both daily and
workout-detail forms, both review choices and reassociation to another workout.

Garmin's reopened Personal and Business APIs change the integration roadmap.
The [verified research and migration plan](GARMIN_API_REOPENING_2026_10.md)
separates owner-only ingestion from multi-user authorization and workout
delivery. The owner-only Personal API pilot and authorized live key validation
were completed in the 25 October follow-up; see the
[implementation and acceptance evidence](PERSONAL_API_ACCEPTANCE_2026_10.md).
That local validation does not establish installation on the production host.
Business authorization for multiple athletes and watch delivery remain separate.

The next step is deployment preflight and installed-version acceptance after
the candidate passes those checks. Production still returned `5d516d4` on
23 October. Repository code cannot establish whether the host's installed
updater is current or enabled: the deployment guide records a recovered,
paused installation. Obtain host `status`, `doctor` and `verify` results before
attempting recovery or resuming its timer. Do not equate merging/publishing an
image with installing it.

## Production acceptance and rollout

1. Require successful checks on the exact release commit, including the
   production-stack job. Review migration 0030 and take a verified backup.
2. Deploy the tested image through the existing updater. Confirm `/version`
   matches the intended commit before retesting the site.
3. Repeat the real recovery/plan Coach question and inspect its evidence and
   proposed changes. Synthetic model evaluations do not guarantee a useful
   response from the configured live provider.
4. Verify a completed Garmin account sync and measurement freshness separately.
   The 19 October recheck observed incoming measurements during an active sync
   alongside historical failed attempts. It did not establish a completed full
   sync or diagnose those historical failures; credentials should not be
   assumed invalid solely from that counter.
5. Have an athlete review and activate their intended schedule, then record an
   actual workout. Synthetic acceptance did not alter real completed exercise,
   activate the owner's plan, or grant consent on their behalf.

Migration 0030 leaves historical units unchanged because their provenance is
insufficient to reinterpret them. Once timed records exist, reverting to code
that assumes non-null repetition counts is unsafe. The migration refuses to
discard those records during downgrade: export/review them or follow the
verified restore procedure, accounting explicitly for post-backup writes.

Optional provider setup, native iPhone/watch delivery and physical-device
behavior remain unverified. The scoped authorization/isolation review found no
concrete cross-account bypass; this is not a claim of exhaustive security
certification. Private live screenshots and session state stay outside Git.
