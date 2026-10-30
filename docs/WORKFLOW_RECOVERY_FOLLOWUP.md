# Plan, workout and activity workflow follow-up

This review continues the daily-workspace work within Apex's original visual
identity. It addresses concrete interruptions in reviewing a plan, following a
workout, inspecting a recording and editing a Coach proposal.

## Findings and resulting behavior

| User task | Confirmed source-level problem | Resulting behavior |
| --- | --- | --- |
| Correct a saved plan | A failed background read, including an unrelated templates request, replaced the planning workspace and removed unsaved corrections. | Cached planning data keeps the selected review mounted. The failed read has an explicit retry; typed corrections survive. |
| Review and activate plan dates | An acknowledgment remained checked when a newer draft arrived. Date fields also remained editable while an older template preview was being generated. | Acknowledgment applies to the exact payload hash. Date controls stay locked during preview generation; changing the range clears the previous preview. Activation remains an explicit separate action. |
| Edit workout instructions | A failed reload could return cached data and discard edits. A successful reload discarded the server's pending draft. Route changes could reuse an earlier workout's editor state. | Only a successful, matching reload replaces local work. The current server review remains available, and account/session keys isolate editors and late responses. |
| Recover a workout read | Initial read failures had no local recovery or escape. Background errors hid the editor. | Retry and calendar navigation are available. Cached instructions and unfinished editing remain visible with an explicit refresh-failure message. |
| Inspect activity laps and sources | Switching tabs unmounted the session, discarding unfinished feedback and comparison context. | The session stays mounted while hidden. Returning to it retains edits; GPS maps resize when shown again. |
| Recover activity data or samples | Failed activity refreshes removed the feedback form. Activity/sample failures offered no retry. | Cached records, samples and forms remain available with a clear stale notice. Initial failures offer retry and the activity log; sample retry leaves feedback intact. |
| Edit a Coach proposal | Fields stayed editable while replacement was pending; the response then closed the editor and lost newer text. Switching or closing editors could discard dirty work. | Pending fields are locked. Closing, switching or showing the full proposal list requires explicit confirmation before discarding changes. The replacement still requires separate approval of its own hash. |

No new palette, logo, type system, score interpretation, schedule, workout
completion or automatic proposal approval is introduced. Existing account/date,
historical/protected workout, revision and consent boundaries remain in place.

## Evidence and remaining acceptance

Findings came from tracing the actual source and failure paths. Automated
interaction regressions use synthetic accounts and delayed/failing API fixtures
against the built application, including English/Italian, dark/light and phone/
desktop cases. Consult the pull request and final CI for the tested revision and
counts. Production-stack checks remain release gates.

Browser-control tools were unavailable in this session. This review therefore
does not establish fresh exploratory use of the owner's real account, an actual
completed Garmin production sync, real-phone keyboard behavior or the usefulness
of the configured live model. Those remain separate acceptance tasks. Further
normal-user review is still needed for sport analyses, the remaining evidence
views and a complete first-use journey with invited athletes.
