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
| P2 | Mobile training and coaching require opening More; desktop labels disappear and the layout moves on hover. | Live navigation and source | Four direct daily destinations; stable visible desktop labels; retain other sections and search. |
| P2 | Sync failure warnings are buried among metrics and have no direct recovery action. | Live Overview | Place actionable notice near today's workout; link to current sync diagnostics and retry connection. |
| P2 | Plain Italian training analysis is routed as medical intent. | Code: bare substring `analisi` | Phrase/boundary matching with real medical triggers preserved; retain classifier intent on fallback. |
| P2 | Sleep provider scores are labelled as Apex calculations; inconsistent bed-window inputs can show 100% efficiency. | Live Sleep list/night and source | Distinguish device estimates; do not derive confident efficiency from inconsistent inputs. |
| P2 | Activity rows say Unknown despite available source sport metadata. | Live Activities plus normalization/schema review | Show the recorded provider label when canonical sport is absent; never infer a sport or rewrite history. |
| P2 | Challenges show blank dates for all-time scope and Join even for members; rankings are not reachable from joined challenge cards. | Live Challenges plus API/UI review | Explicit scope/membership and working leaderboard entry. |
| P2 | Reports expand a long archive and display technical policy identifiers. | Live Lab → Reports | Keep latest readable, collapse archive entries, explain legacy verification state in normal language. |

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
plan activation and consent remain athlete decisions. Garmin's current
connection failure requires diagnosis; hiding the warning is not a repair.

## Verification log

Implementation and verification are in progress. Record final commands/results
and remaining blockers here when the candidate is complete; historical audit
reports are background, not acceptance evidence for this revision.
