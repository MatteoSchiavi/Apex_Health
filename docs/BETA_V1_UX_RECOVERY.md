# Beta V1 UX recovery and browser verification

This change recovers the daily overview, simplifies training navigation and
fixes gym suggestions that previously depended on weekday defaults and stale
drafts. Coach conversation deletion now has a discoverable contextual action
and a reviewable confirmation.

## Browser audit and complaint inventory

The existing production application was inspected with an authorized account
through actual Chromium interactions on 14 routes, plus activity detail.
Requests that could write to production were intercepted. No production
conversations, plans, permissions or athlete recordings were changed. No AI
provider requests were made. Private screenshots and API snapshots stay outside
Git in `/workspace/apex-cloud/beta-private`.

| Complaint / finding | Priority | Root cause and correction | Verification |
| --- | --- | --- | --- |
| Your Day dominates the dashboard | P1 | Association, feedback, protection and totals were permanently expanded. A compact summary now shows state, title, at most two measurements and one primary action; remaining controls stay in keyboard-accessible details. | Actual live-data preview at 1440px and 390px; planned, recorded, historical, skipped, rest and multi-session browser cases. |
| Important scores are hard to find | P1 | Scores were present in the API and rendered below the large daily panel. The four score cards now precede Your Day; unavailable scores retain explicit missing states. | All four visible values matched authorized API responses at both widths. Calculation contracts were preserved. |
| Load summary has misleading scope and units | P1, independently found | The old footer called a 7-day daily average a weekly total and labeled it TSS despite provider load. Summary and chart now identify 7/28-day daily averages and the actual source unit. | Browser/API comparison and compatible trend assertions; respiration remains covered. |
| Sport sidebar clutter | P1 | Running, Cycling and Strength were separate permanent entries. They are internal Training sections, with selected state on desktop and mobile. | EN/IT browser tests, direct routes, search entries and activity-to-sport links retained. |
| Prominent sharing controls | P2 | Sidebar and training/detail links distracted from the primary workflow. Sharing now lives in Settings → Privacy & Sharing. | New destination and legacy route verified; backend permissions and revocation retained. |
| Repeated leg suggestions / stale drafts | P0 | Weekday selection, title-only template handling and unconditional reuse omitted completed set history and approved prescriptions. See the deterministic correction below. | A–J regression cases, persisted database tests and actual browser generate/refresh/confirm journey. |
| No gym generation without a template | P1, independently found | The generation control depended on a recurring template. An explicit generation action is now available without one. | Browser regression through generation and confirmation. |
| Approved gym load targets are invisible | P1, independently found | Targets were present in exercise notes but omitted from the review table. Prescribed sets, repetitions and notes/load are visible before approval; completion is displayed separately. | Actual backend browser review; equal repetition ranges and unknown rest display checked. |
| Stale confirmation error survives refresh | P1, independently found | Refresh did not reset the failed confirmation mutation. Successful refresh now clears it; conflict copy directs the athlete to refresh and review. | Actual sync → 409 → refresh → reviewed confirmation; browser regression. |
| Coach deletion is difficult to discover | P1 | The existing ownership-scoped DELETE endpoint worked, but its UI action was obscure. Named conversation menus and an accessible confirmation dialog expose it. | Cancel, active/inactive deletion, reload persistence, cached-message removal, keyboard/mobile and API failure cases. Real deletions used synthetic chats only. |
| Disabled-AI disclosure buries mobile chat history | P1, independently found | A full consent panel preceded the Coach heading. A compact disclosure now follows the heading; the complete unticked consent form remains accessible inside it. | EN/IT mobile browser coverage and actual isolated-backend capture. Sending remains disabled without access; an empty conversation no longer scrolls the page to the composer on entry. |

The initial live audit reported no JavaScript errors or failing HTTP responses.
These observations describe the inspected routes, not every possible production
state. The inability to reproduce absent score calculations is recorded as a
layout diagnosis rather than a new calculation fix.

## Measured overview recovery

| Viewport | Previous daily card | Revised daily card | Revised score strip | Horizontal overflow |
| --- | ---: | ---: | ---: | --- |
| 1440px | 630px | 208px | 130px | None |
| 390px | 835px | 280px | 256px | None |

The first score previously began around y=975px on desktop and y=1268px on
mobile. The revised score strip appears above Your Day. Measurements used the
same authorized day and real API data, rendered through a local read-only
preview of the modified production bundle. Production was not deployed.

## Deterministic gym correction

Generation loads owned recent set logs, completed recordings, imported exercise
details where available, feedback/check-ins, profile preferences, approved
workouts and upcoming endurance sessions. Actual approved exercise prescriptions
and targets take precedence over generic weekday groups. Unknown exercise or
intensity information stays unknown; a missing catalog match does not invent a
workout.

Scheduling alternatives apply to suggestions. Confirmed, protected, completed,
manually prescribed or started/logged sessions are retained. Conflicts identify
their recorded evidence and require review. The observation window describes
training history; it does not assert a universal physiological recovery rule.
Repeated exercises remain available for continuity and progression.

GET requests never refresh a draft. Explicit generation/refresh retains the
plan identity and creates an audit revision with before/after snapshots and an
input fingerprint. Repeated unchanged generation is idempotent. Confirmation
checks both the reviewed revision and current training inputs, so a new sync
cannot approve a stale suggestion. Scoped locks coordinate these operations
with related writes.

The A–J cases cover yesterday's lower-body logs, approved upper-body work,
tomorrow's intervals, no activity, strength without exercise details, repeated
generation, sync-invalidated drafts, protected sessions, legitimate repetition
and multiple weekly strength sessions. Additional cases cover exact approved
targets, unknown exercises, imported history and persisted ownership/audit
behavior.

## Journeys and evidence

All write journeys used disposable databases and synthetic athletes, separate
from the existing services. Destructive pytest fixtures used another dedicated
database and Redis instance.

- **A — New athlete:** selected Running + Gym (the application's strength focus),
  entered five weekday availability windows and four weekly hours, saved and
  reloaded the profile. Overview retained missing scores and an explicit plan
  creation/review action. No plan activation or AI consent was implied by saving.
- **B — Multisport:** opened a running recording and its sport progress, viewed
  Cycling/Strength progress and recorded lower-body gym sets, and returned to
  Training/Overview. Unavailable analytics were labeled. The fixture's gym
  history is represented by actual set logs rather than a fabricated device
  strength recording.
- **C — Planning:** inspected the approved multisport session and calendar,
  generated the prescribed upper-body draft, repeated an unchanged refresh,
  introduced a synthetic new set, observed rejection of stale confirmation,
  explicitly refreshed and confirmed the reviewed revision. Approved targets
  survived the sequence. Proposed workout changes also retain separate review
  and approval browser coverage.
- **D — Coach:** inspected history and transcripts, canceled deletion, deleted
  inactive and active synthetic chats, reloaded and checked server readback
  (204 deletion, 404 deleted details). Browser fixtures exercise new-chat
  contextual questions and 502/503 recovery without invoking a paid provider.
  A production AI-answer journey was deliberately not run.
- **E — Data management:** visited synchronization status, metrics, sleep,
  equipment, profile and privacy/sharing, then returned to Overview. Existing
  device connections and permission grants were not changed.

Synthetic screenshots and machine reports are saved in
`/workspace/apex-cloud/beta-evidence`: `onboarding-journey.json`,
`data-multisport-browser.json`, `gym-browser-evidence.json`,
`coach-api-journey.json` and `coach-compact-result.json`, with corresponding
desktop/mobile PNGs. Authorized live before/after screenshots remain private in
`beta-private`; no credentials or athlete data are included in this commit.

## Validation and release boundary

Local validation:

- Backend: **1347 passed, 1 skipped**, using the dedicated test database/Redis.
- Full browser regression: **215 passed, 1 skipped**; it also found one missing
  Quick Access navigation regression. The links were restored inside the
  secondary recovery/details area. **All 37 affected browser tests passed on
  the final rebuilt bundle**, including that case, Coach, gym review, daily
  state, journal and respiration coverage. GitHub runs the entire suite again
  for the pushed commit.
- Deterministic Coach evaluations: **26/26 passed** with synthetic fixtures.
- Production TypeScript/Vite build, **2438 matching EN/IT locale keys**, and
  **5/5 service-worker tests** passed; `git diff --check` passed.
- Final actual-backend journey captures: **32 desktop/mobile captures**, no
  page/console or HTTP errors, and no document-level horizontal overflow.
  The gym journey intentionally observed a stale-confirmation **409** before
  successful refresh/review/confirmation. The Coach deletion journey separately
  checked the expected **404** for deleted synthetic conversation details.

Production deployment and updater resumption remain owner actions. Successful tests do not
claim that every unknown exercise prescription or unrecorded measurement is
available; those states remain explicit and reviewable.

## Follow-up: scores and overnight HRV after the local day changes

The October 14 live browser check reproduced a separate availability bug:
Overview showed four missing scores and missing overnight HRV, while the
detail pages contained valid October 13 measurements. Partial current-day
biometrics kept the dashboard anchored to October 14 even though these metrics
had no current-day value. The previous layout audit used a day with available
scores and did not cover this transition.

The default Overview now reads the latest available score and signal from the
same 90-day metric endpoint used by its detail page when the current-day value
is missing. It displays the actual measurement date. Available current-day
values, including zero, take precedence. Explicit date selections retain
missing values instead of borrowing measurements from another day. The daily
workout view remains on the requested day.

When all current-day load values are missing, its summary and chart use one
dated dashboard snapshot, preserving the source unit and compatible averages.
Signals such as overnight HRV retain their selected chart window, with a dated
latest reading available even when it lies outside that shorter window. No
metric calculations, athlete records or plan approvals are changed.

Read-only Chromium previews at 1440px and 390px verified that all four score
values and overnight HRV matched the real detail-page API responses. Neither
view had page errors, failing HTTP responses or horizontal overflow. The
mobile score strip remained compact at 284px. Private before/after evidence is
in `/workspace/apex-cloud/score-private`; credentials and health screenshots
are excluded from Git.

Regression cases cover the new-day transition in English/Italian, legitimate
zero values, historical date selection, empty/error responses, overnight HRV
outside the short chart window, and coherent load date/unit selection.

Follow-up validation: the full 224-case browser run passed 222 cases and skipped
one; it identified excessive card height with Italian mobile labels. After
reducing mobile padding, all 24 focused Overview tests passed on the rebuilt
production bundle, including that case. Locale parity (2441 keys), the build,
all five PWA tests and diff checks passed. GitHub repeats the full release
workflow for the published commit.
