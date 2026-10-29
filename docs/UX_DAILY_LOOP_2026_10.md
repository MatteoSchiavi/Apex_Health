# Daily workflow UX review — 28 October 2026

This pass connects a practical loop: understand the day, ask a question using
its context, review any proposed change, and record what actually happened.
Apex's useful capabilities are its combination of training context, checked
evidence, explicit proposal approval and workout feedback. The interface needs
to make that combination usable through ordinary tasks.

## Research method and limits

This is a source-based task walkthrough informed by previous live audits and
the owner's authorized API checks, followed by automated UI regressions.
It is not representative user research or a fresh exploratory live-browser
session. No browser-control tool was available during this pass.

The earlier real-account check found saved athlete context and undated draft
plans, but no active workout on that day. The planning action therefore stays
primary when a draft needs review; Coach does not replace explicit scheduling.

## Product direction

AI insights and watch-connected training plans are already available elsewhere:
Garmin describes [Active Intelligence](https://support.garmin.com/en-AU/?faq=kWi5DoaMPZ4VCJBA0lFWP7),
and Runna documents [Garmin plan delivery and completed-workout sync](https://www.runna.com/integrations/garmin).
These public sources, consulted on 28 October, inform the direction; they do
not establish comparative usability or feature uniqueness.

The hypothesis for Apex is that athletes will return when they can understand
what to do, inspect the evidence for a suggested adjustment, approve it and
close the loop with their actual experience. This pass makes that sequence
discoverable from the day and workout they are already viewing. More metrics
or generic AI prompts alone would not test that hypothesis.

## Findings and implementation

| Task | Observed friction | Resulting behavior |
| --- | --- | --- |
| Decide what to do today | Scores and load precede the daily task; Coach is a separate destination with generic prompts. | The day and setup actions precede the metric blocks. The summary retains one primary action; a separate day-actions group exposes Coach and feedback. Workout details preserve the exact workout and date. |
| Ask a relevant question | The athlete must reconstruct the context and risks appending to an unrelated conversation or replacing an unfinished question. | Coach verifies the owned day/workout, then explicitly prepares an editable question for a new conversation. Existing text is retained until the athlete chooses replacement. |
| Review a proposal | Every assistant link opens the entire changes list with no indication of the relevant item. Editing leaves the athlete to find the replacement. The list's newest-50 limit also hides older proposals from saved conversations. | Typed proposal references open and focus the specific owned proposal, including older items resolved through an ownership-checked lookup; other proposals stay available. Saving an edit focuses the replacement for separate review and approval. Invalid, missing and failed loads have explicit recovery. |
| Continue after approval | The athlete has to find the workout again after a session change. | An applied session proposal links to its updated workout. Approval, rejection, editing and undo remain separate explicit actions. |
| Record post-workout feedback | Today hides the feedback form behind daily details and a second disclosure. | Visible Add/Review feedback links open the selected recording's existing form directly. Multiple recordings have separate links; a recording is not itself a saved feedback receipt. |

Navigation never sends a question, enables AI, consumes model budget, approves
a proposal or records completion. Context handoff contains account identity,
date and an optional workout ID, without notes, health values or prompt text
in the URL. Coach checks canonical ownership/date/session identity before
preparing a question. Historical questions name the date explicitly and ask
for missing evidence to be explained; live-model retrieval for historical
questions still requires acceptance testing.

The feedback entry opens and focuses only the selected activity. The requested
day uses the athlete's timezone. Missing activity context gives a retry and a
return-to-day action instead of opening a different recording's form.

## Validation and acceptance

Automated scenarios cover both languages, phone width, local midnight,
multiple recordings, exact save identity, unavailable context, preserved draft
text, consent-disabled preparation, in-flight replies, account changes,
specific proposal selection and the explicit approval boundary. Existing Coach
failure/deletion/evidence and decision-review regressions remain release gates.
Consult the PR checks for the final tested revision and counts.

The 29 October pre-merge review found that a background day refresh could
unmount an unfinished feedback form after a recording was associated, or after
a temporary fetch failure. The view now retains its current day while feedback
is dirty, saving or being reconciled. The query cache still receives updates
for explicit conflict review. Retention is scoped to the account, day and
workout/activity; navigation and account changes cannot transfer the draft.
Timer-driven regressions cover reassociation and failed refreshes in both daily
and workout views, plus date navigation and account isolation.

After deployment, ask a few athletes to perform these tasks without guidance:

1. Explain today's planned activity and find the reason to keep or review it.
2. Prepare and send a question about that exact day or workout, then inspect
   its evidence and identify any missing inputs.
3. Find the proposal from the answer, review it and return to the workout.
4. Add feedback to the intended recording on a phone, then revisit it.

Record task completion, wrong turns, points of uncertainty and time spent.
Ask athletes to explain what changed, why, and whether their feedback was saved
to the intended workout. Observe their first attempt before giving guidance.
An incorrect date/activity, an unexplained proposal or a saved result the
athlete cannot find is a failed task, even if the underlying request succeeds.
Passing UI contracts establishes the specified behavior; it does not establish
that athletes understand the flow or find the model's answer useful. Installed
candidate acceptance, configured live-model behavior and physical-device
delivery remain distinct from this source/test review.
