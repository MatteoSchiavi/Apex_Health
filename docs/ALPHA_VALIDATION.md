# Alpha validation

## Daily interpretation and decision feedback (B4 + A5)

The existing deterministic daily decision now also returns `state`, `headline`, `key_changes`, `contributors`, `data_coverage` and `recommended_action`. The original action, reasons, evidence, baselines, alternatives and limitations remain available to the UI and agent snapshot. State is one of `stable`, `adjustment_suggested`, `recovery_suggested` or `insufficient_data`. English and Italian text is deterministic. No new readiness score or prediction is introduced.

`key_changes` compares the latest available observation with a comparable personal baseline from the existing source-specific baseline service. Stale observations remain in inspectable evidence but have no current value or delta in the interpretation. Missing baselines and deltas remain null; the existing sleep-duration rule has no personal sleep baseline. Signal coverage describes available data, not confidence in a physiological benefit.

The Overview places the daily interpretation before raw metric cards and still shows an incomplete-data interpretation when today's overview is empty. Source values remain accessible through the existing metric cards and expandable decision evidence. Evidence, alternatives and subjective check-ins use progressive disclosure. Historical days preserve their saved interpretation and do not offer a current-day subjective check-in. “Ask Apex” links to the existing coach surface; it does not approve a change.

Feedback reuses `DecisionRecord.outcome`. The existing required state remains unchanged. Optional fields capture influence on the plan (`yes`, `partly`, `no`), perceived usefulness, a reason in the existing `notes` field, session completion, RPE, soreness, pain, feeling unwell, an activity, a proposal and a planned session. Partial updates merge only fields explicitly submitted, preserving earlier feedback. Explicit null clears an optional value. This records user reports, not verified health or training outcomes.

Every linked record must belong to the signed-in user. Activity and planned-session dates must match the decision date. A session proposal must refer to the same planned session and date; the endpoint fills its planned-session link when omitted. A delivered plan proposal must reference a session from its resulting plan when both links are supplied. Dated journal proposals and plan-week proposals must also be coherent with the decision date. Undated proposals must have been created on the decision's local day. Failed validation writes neither an outcome nor a utility event. Feedback never invokes the change executor or modifies a session. The established before/after review, exact payload hash approval, expiry, execution receipt and undo boundaries remain in place. Session proposals can be edited for duration, description and reason: saving creates a replacement proposal, marks the old draft superseded and requires a separate review and approval of the new exact diff and hash. Approving the original draft is hidden while its edit form is open.

The `decision_feedback_submitted` utility event stores only the decision ID. Notes, symptoms, RPE and soreness stay in the athlete's decision outcome and are not copied into event metadata. Influence, usefulness and execution are not evidence of a physiological benefit; no outcome-driven personalized model or automatic recommendation tuning is added in this alpha.

## Targeted validation

- `backend/tests/test_decision_learning.py`: structured interpretation, source comparisons, stale/missing evidence, Italian text, symptom override, authenticated partial feedback, bounded inputs, record ownership, coherent dates, proposal/session matching, telemetry minimization and no execution side effects.
- `frontend/tests/decision-learning.spec.ts`: overview order, evidence disclosure, optional feedback, linked post-session data, incomplete current overview, Italian mobile rendering and accessibility, and a mobile edit → replacement preview → separate exact-hash approval flow.
- Existing `backend/tests/test_performance_lab.py`, `backend/tests/test_lab_api.py` and `frontend/tests/lab.spec.ts` continue to cover the established decision and draft approval boundary.

Validation recorded on 2026-10-07: the complete backend suite passes (801 tests), including all decision/feedback cases. All five new decision-learning browser cases pass with system Chromium, including Italian mobile accessibility and edit → replacement preview → separate approval, alongside the existing daily-decision/exact-hash approval cases. Frontend TypeScript, production build, English/Italian key parity (1,430 keys) and PWA checks pass. The complete browser run passed 95/99 cases; four new alpha/sync selectors failed, were corrected, and all four pass on targeted reruns. These results cover synthetic application behavior, not live-model quality or physical-device behavior.

Backend tests require explicitly disposable PostgreSQL and Redis services and `APEX_TEST_DATABASE_RESET=1`; the repository's test fixtures rebuild the schema and flush Redis. Coordinate a single backend test runner. Normal validation uses synthetic browser records and deterministic backend data, with no live provider, LLM or credential calls.

## Small alpha review

Use a small consented cohort with a recorded starting period. For each participant, inspect whether they can connect an eligible data source, understand coverage limitations, locate the evidence for a decision, review an exact proposed change, and leave optional influence/usefulness feedback. Check both English and Italian, mobile layouts, empty days, stale syncs, historical dates, rejected proposals and partial session completion.

Review aggregate usage and user reports separately: proportion of eligible decision views with voluntary feedback, distribution of influence/usefulness responses, proposal review/accept/reject behavior, and recurring missing-data or navigation problems. Denominators must name the eligible population and time window. A higher acceptance rate is not a health or performance claim. Evaluate usefulness through task completion and participant explanations before making any recommendation-quality claim.

Record build and test results in the implementation ledger. Public release, wider recruitment, provider production approval and scientific outcome calibration remain separate decisions.
