# Analysis and evidence workflow follow-up — 2 November 2026

This continues the normal-user workflow review from PR #9. Findings came from
tracing the current application and exercising synthetic browser scenarios.
Apex's existing tokens, typography, palette and panel geometry are retained.

## Findings and resulting behavior

| Task | Problem | Resulting behavior |
| --- | --- | --- |
| Expand a calendar day's activity log | Period buttons changed selection while the date query kept results pinned to one day. | Choosing a period clears the pinned date. The period survives opening a detail, Back and reload. The page identifies its actual day/range, and browser Back restores the day. Invalid date links explain the fallback. |
| Read a failed metric, night or sport analysis | Some failed reads replaced navigation with an error, without a local retry. | Recovery controls remain with the page's navigation and date/period controls. Available cached results stay visible with an explicit stale notice. Sleep stages and endurance evidence retry independently of their parent records. |
| Compare sport progress over a chosen interval | Date fields could differ from the displayed results, and leaving the page discarded the applied interval. | Results identify the server's actual interval. Applied dates are in the route, survive Back/reload and follow navigation between sport pages; unfinished field edits do not change the results. Invalid linked intervals are explained. |
| Inspect a metric from Health | The detail silently used its own default period and returning lost the search and category. | The selected period opens in the detail. Search, category and period survive the return journey and reload. Typing a search replaces its history entry rather than adding one per character. |
| Run the actual API-backed application in development | Vite did not proxy athlete, HealthKit or API-prefixed admin/feedback requests, so SPA HTML could replace API responses. | The missing API roots are forwarded. A temporary HTTP backend verifies actual forwarding, query strings, POST/CSRF headers and frontend-only routes. |
| Read Health on a phone | Desktop column headings remained visible despite the intended responsive rule, consuming space above the measurement. | A separate responsive wrapper hides the headings on phones and retains them on desktop. |
| Inspect the activity behind a calculation | Activity-ID arrays and provenance references were plain numbers or technical strings. | Known activity references open the corresponding owned activity detail; raw provenance remains available for inspection. Unknown source types are not guessed. |
| Edit comparison context | A failed refresh unmounted the editor; a newer revision could replace unfinished route/context edits or review. Changing providers discarded the current draft. | The editor and exact revision stay mounted while dirty/reviewing/saving. Newer data is identified; explicit reload replaces the draft only after a successful read. A changed revision cannot be approved from the old review. Provider changes require discarding unfinished work and stay disabled while saving. |
| Continue onboarding through a connection failure | A failed profile refresh hid the unfinished athlete-context form. | The same controlled editor remains mounted with a retry, preserving its typed text. Explicit reload accepts only a successful read, never cached data from a failed read, and locks fields until that read finishes. |
| Review sleep around local midnight | Sleep history relied on the server's default calendar day. Malformed date links could reach invalid dates/navigation. | Requests explicitly use the athlete's local 42-day window. Invalid night dates do not trigger a read and offer the history link. |
| Resume a destination after signing in | Only the pathname survived session recovery, dropping day, filters and section. | The full internal destination is restored. Return URLs are parsed and restricted to the current origin's athlete workspace. |

Metric, sleep, activity-log and comparison-context queries touched by this pass
include account identity. Existing query-prefix invalidation remains compatible.
No health formula, backend contract, provider credentials, consent, training
completion or proposal approval rule is changed. Navigation remains read-only.

## Validation and acceptance boundary

The new browser scenarios use synthetic accounts and API fixtures. They cover
read errors and retries, background refreshes, newer revisions, provider changes,
invalid dates, local midnight, retained DOM/editor identity, explicit review,
Back/reload and absence of training mutations from navigation. Both languages,
both themes and phone/desktop viewports are represented.

A fresh real-account exploratory browser is not available in this environment.
A completed production Garmin sync, usefulness of live Coach answers, physical
phone keyboard behavior and unaided invited-athlete journeys remain acceptance
work. These fixes do not establish that the whole application is finished.
Production promotion follows the release gates; the live version must be verified separately from these synthetic scenarios.

Production TypeScript/build, EN/IT key parity, PWA checks and the complete UI
suite are the validation gates for this change. Consult the pull request for
the exact tested revision and final counts. Synthetic phone/desktop captures
were also inspected for navigation, recovery actions, layout and overflow.
