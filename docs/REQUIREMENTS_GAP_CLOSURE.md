# Follow-up implementation of the completeness audit

This delivery implements the actionable gaps found in `REQUIREMENTS_COMPLETENESS_AUDIT.md` against revision `14dece1`. It extends canonical profiles, activities, gym set logs and gear associations. No production deployment, updater resumption, real plan activation or AI permission change is performed.

## Changes

| Audited gap | Implementation | Evidence limits |
| --- | --- | --- |
| Measured goal progress | Optional typed goals for complete-week distance/duration, longest recorded distance, duration-specific power and exercise estimated 1RM. Explicit targets have compatible units, profile/source references and finite bounds. Saved weekly baselines are never silently promoted to targets. | Weekly targets use the latest completed local Mon–Sun week inside the selected range. Missing measurements, clipped weeks or incomplete history remain unavailable. Target attainment is not a race-performance prediction or a prescription. |
| Reachable comparison inputs | Activity detail now provides an explicit review/save/remove workflow for route identity, terrain, indoor/outdoor, time convention and easy/steady intent. Owner/provider checks, transaction locks, hash revisions and audit records protect writes. | These are labelled athlete assertions in a reserved metadata namespace, not provider-verified measurements. Existing imported context retains precedence. Outdoor comparisons still require actual eligible weather snapshots; the form cannot invent weather or certify climbs. |
| Complete workout education | Ordered education now includes repeat children, exact prescribed targets and duration/distance, strength details, and EN/IT block-specific mistakes and conservative alternatives. Education is hidden while a draft/editor is displayed so approved instructions do not masquerade as an unapproved prescription. | Guidance is generic, not individualized medical advice. Alternatives explain choices without changing the saved plan or inventing zones. |
| FTP source/methodology | Profile editing distinguishes manual, tested, imported and estimated assertions. Non-manual values require methodology; tests require a protocol, imports a source reference. Accepted assertion history preserves that metadata. | User confirmation does not independently validate a protocol. Estimated FTP remains visible as an assertion/history entry but is excluded from IF/TSS threshold calculations. No retrospective FTP history is fabricated. |
| Automatic interval identification | Activity detail and sport overview expose bounded repeated-effort candidates from recorded speed/power, with coverage/ordering/quality gates, versioned methodology, source references and explicit unavailable/no-pattern states. | Fixed 15-second bins and level/contrast rules may miss unusual duty cycles. Candidates do not prove session completion or physiological thresholds. Terrain and stops can mimic intervals. Grade-adjusted pace remains deliberately unsupported pending a defensible model. |
| Equipment historical comparisons | Same-type owned gear can be compared using one-to-one compatible canonical activity pairs. Results show individual recordings, units, source references, scoped summaries and confounding; usage counters are reused. | Comparisons cover the latest 500 activities per item, disclose truncation, and never imply a causal equipment effect. Different disciplines/routes/source conventions are not averaged into a composite score. Missing context/data stays unavailable. |
| Goal-linked strength analytics | A reachable strength overview reuses the Lab's shared recorded-set/Epley calculation and the canonical `gym` profile focus. It links compatible exercise estimates to explicit goals; weekly duration uses recorded strength activities. | Different exercise IDs are not combined. Missing weights are not zero. An estimated 1RM is not a tested maximum; sets alone do not imply workout duration. |

## Architecture and API

No new database migration or parallel canonical store is introduced. New optional goal/FTP fields live in the existing profile JSON; reviewed comparison assertions live separately from provider measurements in existing activity metadata. Existing profile revisions, immutable calculation inputs, approval boundaries and provider AI restrictions remain.

New endpoints are `GET/PUT /activities/{id}/comparison-context`, `GET /gear/{id}/comparison?other_gear_id=...` and `GET /athlete/sports/strength/overview`. Existing running/cycling overview and activity endurance responses gain goal/interval data. The Lab's gym progression and strength overview share a helper rather than maintaining two calculation engines.

The frontend adds measurable-goal and FTP provenance editing, reviewed comparison context, nested workout education, equipment comparisons and a strength navigation entry. Core functionality remains available without AI. EN/IT interfaces and translation parity are preserved.

## Verification

Local verification established profile/provenance persistence, estimated-threshold exclusion, comparison ownership and revision handling, interval quality gates, education nesting, equipment scoping and source isolation. The comparison integration fixture proves that saving context for two actual owned imported activities unlocks a previously unavailable measured aerobic comparison without inventing weather.

The first complete backend run recorded **1,314 passed, 1 skipped and 1 failed**. Its failure exposed default FTP metadata creating a historical assertion for an unchanged legacy snapshot; the implementation was corrected rather than weakening the regression. A subsequent focused gate passed **42 tests**, including that original regression, protection against older clients relabelling estimates, and all new owned API workflows. Earlier integration checks passed 126 tests. These overlapping counts must not be summed.

The first complete browser run recorded **187 passed, 1 skipped and 3 failures**. Traces showed cold development-module loading and a multi-screen navigation timeout. CI now tests the built production bundle, which the workflow builds first. Final complete browser and GitHub acceptance results are reported in the delivery message. TypeScript/production build, all **5 PWA tests**, **2,385-key EN/IT parity**, Python compilation and whitespace checks passed. Tests used dedicated synthetic database/Redis containers; real services were not reset.

The complete production-bundle browser run then recorded **189 passed, 1 skipped and 1 failed**: a pre-existing visual check imported a development-only ECharts module. That test now inspects actual rendered canvas pixels to verify the asymmetric midnight-to-08:00 fixture appears in the correct vertical position with a visible bar. All **9 tests in its file passed** after this correction. Final publication waits for the checks on the corrected commit, including release-image validation.

Production acceptance remains separate: remembered sessions behind the real reverse proxy, live Garmin, Telegram delivery and the host's actual updater/image/schema recovery require owner-side verification. Publishing source or an application image does not install the host controller. Follow `AUTO_UPDATES.md` and `TELEGRAM_CONTROL.md`; automation remains paused.

Verified climb analysis still needs actual imported segment measurements. Grade-adjusted pace still needs a reliable model. Neither is replaced with invented values to claim full completion of the original specification.

## Compatibility and rollback

Old profiles remain valid; FTP without source metadata retains manual-confirmed behavior. Old clients that omit optional provenance fields cannot assert a tested/imported protocol. Saving an unchanged threshold through an older client preserves existing provenance; normalizing defaults does not invent historical assertions. New clients require no schema migration. Rolling the application back should preserve stored JSON and user assertions, but older code may ignore goals/context annotations and would not recognize the estimated-FTP exclusion. A rollback must therefore review estimated FTP assertions and keep them out of older threshold calculations; do not automatically resume the updater or deploy an older image solely because these changes are additive.

Implementation was delegated into three non-overlapping domains (progress calculations, comparison context, education/equipment). The coordinator owns the shared profile contracts, integration, validation and publication.
