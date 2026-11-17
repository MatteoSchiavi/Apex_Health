# Workflow review and applied improvements

Scope: app route inventory, frontend and API code review, synthetic browser workflows, and disposable-database tests. No real workouts, provider credentials or production accounts were changed in these simulations. The exact cause of the reported production check-in failures cannot be identified without that deployment's logs; the failure paths below are demonstrated in code and tests.

## Applied changes

| Workflow | Friction found | Result |
| --- | --- | --- |
| Open Today | Failed AI attempts were cached as an empty generic message for the entire morning/afternoon. Strict formatting discarded otherwise grounded responses. Any global data revision during generation discarded the response. | Validated prose is compacted locally to three lines. Each line has its own visual row so the next step is not hidden by a wrapping status sentence on phones. Provider failures, grounding failures, exhausted budgets and pending concurrent requests show a labelled, three-line readout from current recorded observations. Comparable prior-week readings include coverage; sparse data stays explicit. Only removed/replaced evidence invalidates an answer. Safe fixed reason codes are logged, without health content or provider error bodies. |
| AI check-in quota | A 650-token response reserved the default 4096-token output allowance, unnecessarily rejecting requests near the account budget. | Reservation uses the requested output limit while retaining conservative input budgeting. Short check-ins explicitly disable optional reasoning on supported GLM/DeepSeek models so the small output budget goes to the answer; ordinary chat settings remain unchanged. The durable claim still precedes external I/O; a failed or ambiguous attempt still consumes its slot. No scheduler, automatic retry or catch-up is added. Erasure during generation cannot restore content. |
| Find an existing plan | Planning discovered source documents, extraction drafts and templates, but did not independently list active training plans. An athlete with an existing plan could land in the import flow. | Account-scoped active-plan discovery shows the existing baseline, upcoming sessions and protected/recorded states. It handles a rest day, plans without source documents, historical dates and read failures without implying the user must recreate the plan. |
| Adjust an existing plan | No direct route from the active baseline to a performance-based review. | “Adjust upcoming loads” carries only owned account/date/plan identifiers to Coach. Coach verifies the current plan before preparing an editable question. The question asks for comparable performance, feedback/RPE and constraints, preserves the structure/goals, and requests session proposals through existing preview/approval tools. No message is auto-sent and no plan is auto-replaced. |
| Preserve training history | Partial results were omitted from some historical-edit guards; session proposals could target old sessions. | Server-side proposal checks reject past, recorded, partially completed, completed, skipped and protected sessions, and superseded plans. A test applies an approved adjustment to one editable future session and proves the existing plan and other sessions remain intact. |
| Follow a structured workout | Instructions and editing shared the same primary surface; no focused way to progress through approved blocks. | An optional workout guide displays one approved top-level block at a time, including repeat instructions, with keyboard focus and Previous/Next controls. The final action leads to voluntary result recording. Navigation does not log sets, infer performance or mark completion. Editing stays available as a secondary action. The guide uses current approved instructions even while a separate proposal is pending. Changed workout targets require a fresh instruction review before guided execution. |
| Analyse an activity | No direct contextual Coach entry from activity details. | “Analyse with Coach” verifies the owned activity against its day, then prepares an editable question about actual metrics, splits, plan comparison and feedback. It does not send automatically or alter the plan. |
| Return to an activity list | The header's return link discarded the selected period; sport filtering existed only in component memory. | Period and sport survive detail navigation, the visible return link and reload. Only known list parameters from the same account are carried back. |

## Remaining workflow inventory

These flows were reviewed against their existing recovery and identity contracts. Existing protections were retained; they do not require additional confirmation screens.

| Journey | Reviewed behavior and regression coverage |
| --- | --- |
| Login, invitation, expired session, account switch | Return location/date is preserved; cached data and drafts remain account-scoped. `login-return-context`, `remember-me`, account/ownership API tests. |
| Quick setup and advanced configuration | Short sport/context form remains the default, advanced configuration remains available, AI consent remains separate and voluntary. Unsaved changes survive failed refreshes until explicit reload. `today-checkin-setup`, `profile-explicit-reload`, `athlete-system`. |
| Garmin connect, sync and data coverage | Personal API key only, visible sync progress/recovery, no legacy password integration. Official-data provenance and missing values retained. `garmin-personal`, `sync-health`, connector ingest tests; endpoint inventory in `GARMIN_API_COVERAGE.md`. |
| New plan import, template dates and activation | Source → explicit review → dates → activation remains available alongside the current plan. Draft review stays mounted during read failures. Undated templates are not active plans; protected plans cannot be superseded silently. `athlete-import`, `training-planning`, `plan-workflow-recovery`, `athlete_training`. |
| Gym execution, structured instructions, completion, associations | Set recording and post-session feedback retain exact planned/recorded identities, revisions and conflict recovery; no automatic association or double counting. `beta-navigation-gym`, `v01-workout-completion`, `workout-workflow-recovery`, structured-workout and athlete-training APIs. |
| Coach conversations, pending replies, proposals, approval, undo | Context handoffs preserve unsent questions and require explicit replacement. No new chat request occurs until Send. Proposed changes remain separate from approval; exact hashes, revisions, constraints, expiry and ownership remain enforced. `coach-context`, `redesign-coach`, `proposal-review-path`, `review-pending-safety`, performance-lab tests. |
| Metric, sleep, sport and activity history | Selected dates/ranges stay in navigation; recorded versus derived values and missing data remain distinct. Failed refreshes retain usable data. `history-read-recovery`, `sport-range-navigation`, `metric-navigation-context`, activity recovery suites. |
| Calendar, availability, illness and life events | Declared constraints remain shared with planning; failed refreshes preserve event edits. `feedback-calendar-recovery`, calendar and athlete-training APIs. |
| Equipment, maintenance and sport settings | Shared equipment center and ownership boundaries retained; failed reads/writes keep local edits recoverable. `equipment-center`, `equipment-workflow-recovery`, `education-equipment`. |
| Food, journal and daily feedback | Explicit saves, optional details, historical dates, conflict handling and drafts retained. `account-food`, `journal`, `daily-feedback-path`, `comparison-draft-recovery`. |
| Lab documents, analyses, data repair and erasure | Source consent, provenance, job states, retry/reload distinctions and erasure remain explicit. `lab`, `data-health-recovery`, performance-lab and erasure tests. |
| Sharing, social, notifications, PWA and administration | Sharing remains opt-in and revocable, private data stays private, feedback remains user-initiated, installed app navigation/version visibility retained. `sharing`, `admin-feedback`, `admin-release`, `pwa-install`, navigation and service-worker tests. |

## Practical limits

The plan adjustment path is a grounded Coach workflow with reviewable session duration/type/description changes. It does not claim a calibrated automatic TSS/intensity optimiser. Insufficient performance evidence should lead to questions or keeping the baseline. The workout guide is an instruction reader, not watch execution or a timer. Recorded check-in fallback is explicitly non-AI, reports observed values and coverage, and does not invent readiness or medical conclusions.

New simulations cover English/Italian, light/dark, phone/desktop, existing drafts, a plan with completed/protected/editable workouts, activity context, safe list return, guide progression without writes, and labelled summary recovery. See the commit's validation report for executed test results.

## Validation

- Full backend regression: **1,508 passed, 1 skipped**. Final focused backend run after provider/date refinements: **97 passed**.
- Full browser regression: **420 passed, 1 skipped**. Final summary layout and activity-date refinements were checked again in focused browser runs.
- Deterministic Coach evaluations: **26/26 passed**.
- Locale parity and production build passed; service-worker **5/5**, development proxy **11/11**, updater **81/81**.
- The GitHub workflow on the pushed commit repeats the full suites and release validation against the final tree.
- Release CI exposed an interrupted HTTP/2 transfer fetching PostgreSQL's signing key. The image build now uses HTTPS over HTTP/1.1 with bounded retries and timeouts for that download; the updated command successfully fetched the public key locally.
- Plan adjustments and undo now advance the plan revision. Earlier instruction drafts become stale, and changed duration/type/instructions require a fresh block review before guided execution. A pending proposal does not prevent following the still-current approved workout. Instructions are never silently rescaled or replaced by an unapproved proposal.
