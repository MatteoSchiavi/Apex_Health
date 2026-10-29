# Daily workspace redesign — 29 October 2026

The earlier daily-workflow repairs left the product looking and feeling like
the same long dashboard. This pass changes the composition of Today, Training
and Coach, together with the shared navigation and controls.

## Design decisions

| Previous friction | Redesigned behavior |
| --- | --- |
| A large introduction, setup checklist and many equally prominent cards compete with the next task. | Today starts with one prominent daily action. Desktop puts supporting evidence beside it; phone puts the action first. Setup is a compact expandable strip. |
| A completed recording can dominate the headline while the action opens a different, unfinished workout. | The focus panel names the remaining session and shows its planned targets. A lone recording needing feedback offers its own check-in as the primary action. |
| Health charts and history make every visit a long scroll. | Four dated score readouts remain visible. Recent activity and sleep are compact; deeper trends, stages, load and calendar open explicitly. The load shortcut opens and reaches its chart. |
| A health-dashboard refresh failure can remove the entire day view and unfinished feedback. | Actual day actions stay mounted independently. Cached health values are marked as last loaded with a retry; initial failure never fabricates scores. |
| Desktop navigation gives every feature equal priority. | Today, Training, Coach, Activities and Health are primary. Tools remain available through a labeled disclosure that reveals the current route. Phone retains four destinations and More. |
| Training mixes execution, plan management, events and sport analytics. | Train today, Your plan and Progress are separate workspaces. A real gym plan prioritizes execution. Planning preserves the selected day without inventing scheduling dates. |
| Conversation history, repeated guidance and tall panels push the message box below the screen. | Coach uses a compact header, secondary history and a conversation area sized for the viewport. Context intake and expanded history can use normal document flow. |
| Suggested questions can overwrite unfinished text. | Selecting a starter preserves existing text until the athlete explicitly chooses replacement. Preparing text never sends it. |
| Proposal comparisons expose technical keys and repeat approval explanations. | Known fields have readable labels and units. Unknown changes remain visible. Technical identifiers and hashes remain available in details; approval and edit/review boundaries are unchanged. |

The original monochrome/orange palette, sharp panel geometry, Geist type and
black/white primary controls are preserved. The changes address hierarchy,
navigation and workflow density within that existing language. Existing
dark/light preferences remain in effect. Primary controls have a 44px minimum
touch target.

## Rendered previews

These are screenshots from passing interaction scenarios using synthetic
fixtures, not the owner's records. They include dark/light themes and both
languages; viewport screenshots show the controls visible before scrolling.

- [Today on desktop](ux-redesign/today-desktop.png)
- [Today on a phone](ux-redesign/today-phone.png)
- [Coach on a phone](ux-redesign/coach-phone.png)
- [Active training in Italian on a phone](ux-redesign/training-phone.png)

## Boundaries preserved

- Unscheduled, confirmed rest, draft plans, planned sessions and recorded
  activity remain distinct. No new readiness interpretation or workout is
  invented by the interface.
- Explicit dates do not borrow older scores. Latest readings retain their
  actual date; zero and missing measurements remain distinct. Load values,
  units and charts use the same snapshot.
- Feedback retains its account/day/workout identity and unfinished text through
  background refreshes. Training execution and rest timers survive workspace
  switches. Navigation does not log a set, activate a plan or approve a change.
- Coach keeps consent, budget, pending/error/retry behavior, account-scoped
  conversations and editable drafts. Proposal approval still requires the
  current payload hash, and editing still requires separate approval.
- Existing routes and planning/gym anchors continue to work. Search,
  notifications, settings, owner administration and secondary tools remain
  reachable with keyboard and touch controls.

## Validation and assessment

This is an implementation and automated visual/interaction review, informed by
earlier real-account findings. It is not an unaided user study. Browser-control
tools were unavailable for a fresh exploratory session; the existing test
runner generated synthetic-data screenshots for visual inspection.

Checks cover English/Italian, dark/light, 390px and 1440px layouts, primary-action
visibility, composer and active-workout controls above phone navigation,
keyboard discovery, planning dates, unknown proposal fields, exact feedback
targets, preserved drafts and absence of training mutations from navigation.
Visual review found the first Coach composer and active gym controls still
below the fold; the implementation was refined rather than accepting those
screenshots as sufficient. Consult final CI for the tested revision and counts.

After installation, ask athletes to find their next task, execute or review a
workout, ask a contextual question and identify exactly what a proposal changes.
Observe the first attempt without coaching. Record wrong turns, missing
controls, uncertainty and whether the evidence changes a useful decision.
Phone software-keyboard behavior and real configured-model answer quality
still need installed-device acceptance.

This pass does not rebuild the structured workout editor, plan-authoring tools,
individual sport pages or all evidence-detail views. Their original styling
is retained; further workflow redesign should follow observed task failures.
