# Sex and physiological context audit — 8 October 2026

The current repository is not a male-only calculation system. All 38 metric
definitions were inspected, along with the feature engine, registered analytics,
lab ingestion/queries, provider normalizers, dashboard/sleep adapters, gym
planning, watch payloads, profile/export paths and AI/report generation. No
existing Apex equation uses a male-only metabolic, body-fat or Banister TRIMP
coefficient. The changes below repair missing profile context and scientific
presentation; they do not establish female-specific clinical validation.

## Profile and account paths

- Signup records the selected sex, defaulting to male for the current beta.
  Explicit female, other and unspecified choices remain possible. The existing
  settings selector updates the same account field. Existing unknown profiles
  are not rewritten to male.
- The anatomy is an interactive SVG with front/back male and female variants.
  It follows profile sex; an unknown profile uses the male **drawing only**.
  There is no diagram control that can diverge from the recorded profile.
- Scientific context never defaults missing/other sex to male. Coach snapshots,
  periodic reports, planning constraints and new calculation snapshots carry
  the actual account-owned sex, age when known, and recorded height.
- Sex, date of birth and height are included in the evidence revision. A change
  invalidates cached decision/analysis revisions and unapplied approvals. Profile
  edits share the account changes lock with approval and calculation paths.
  Calculations reload current profiles inside that boundary, including workers
  that received an older detached User object. Historical snapshots retain the
  context actually present at computation; legacy snapshots are not fabricated.
- Every registered metric now declares its sex handling in API definitions;
  new calculation records retain that declaration.

## Complete metric inventory

| Metrics | Current behavior for male and female profiles | Audit decision |
| --- | --- | --- |
| `resting_hr`, `hrv_ms`, `respiration`, `spo2` | Recorded source-compatible values; personal distributions, not male population cutoffs | Keep measurements and personal baselines. Explain possible hormonal influences on HRV/RHR without assigning a cause. |
| `weight`, `steps`, `floors`, `hydration` | Recorded quantities; no sex-dependent requirement or target calculation | Preserve recorded values; recorded hydration is not an intake prescription. |
| `body_fat`, `vo2max` | Vendor estimates, not Apex body-fat or fitness-category equations | Do not rescale by sex or invent sex/age percentile categories; the vendor's demographic configuration remains the user's responsibility. |
| `sleep_duration` | Recorded duration and declared hours conversion | Duration arithmetic is shared. Sleep debt uses an explicitly configured personal target, not an assumed sex target. |
| `provider_sleep_score`, `sleep_deep`, `sleep_rem`, `sleep_light`, `restlessness`, `whoop_sleep_performance` | Provider estimates/context | Preserve provider algorithm and scale. No inference about its sex-specific calibration. |
| `recovery`, `readiness`, `systemic_stress`, `load_spike` | Shared heuristic blends; recovery/stress use personal deviations where available | No validated female correction is specified for these Apex functional forms. Explicitly disclose missing sex/cycle/pregnancy calibration. |
| `sleep_score` | Shared heuristic REM/deep/efficiency transforms | Not a validated normal sleep architecture for either sex. Keep the experimental estimate; disclose absent sex/pregnancy calibration. |
| `strain` | Personal peak-relative load with an existing 300-unit floor | Shared heuristic; the floor is not a male physiological constant or a validated female threshold. |
| `acute_load`, `chronic_load`, `acwr` | Same-method window sums and overlapping-window ratio | Arithmetic is shared; no sex-specific ACWR injury/safety band. Edwards load uses Tanaka's shared adult HRmax regression. |
| `hrv_baseline`, `hrv_deviation`, `resting_hr_deviation`, `respiration_deviation` | The account's own comparable recorded history and deviations | Do not substitute a male reference distribution or infer cycle-adjusted baselines. |
| `cross_discipline_fatigue` | Load decay/own-discipline peak normalization | Shared unvalidated carryover heuristic, not a sex-calibrated fatigue measure. |
| `efficiency_factor`, `aerobic_decoupling` | Recorded cycling power/HR ratios and changes between session halves | No sex coefficient in this arithmetic; physiological interpretation remains context-dependent. |
| `estimated_ftp` | Explicit twenty-minute protocol configuration, 0.95 × recorded best twenty-minute power | No sex-specific multiplier. A qualifying recorded window does not prove a maximal protocol or individually validated FTP. |
| `provider_readiness`, `provider_recovery`, `provider_strain`, `provider_body_battery` | Vendor-specific estimates | Do not reverse engineer female components or treat incompatible provider scales as equivalent. |

Additional calculations were inspected: rolling sleep timing/consistency,
training distributions, activity statistics, calorie totals, gym set volume and
the Epley recorded-set estimate. They do not use sex-dependent population
constants. The Epley value remains an estimated maximum from recorded sets,
not a sex-specific normative strength classification. Rankings compare their
declared recorded quantities, not demographic-normalized clinical fitness.
Nutrition currently records intake; Apex does **not** calculate BMR, TDEE,
sex-specific daily nutrient requirements, pregnancy requirements, BMI risk,
eGFR, clinical anemia categories or body-fat reference categories. Adding
formula branches for absent calculations would be new features, not fixing
male constants in existing code.

## Heart-rate model: deliberately preserved

[Tanaka, Monahan and Seals (2001)](https://pubmed.ncbi.nlm.nih.gov/11153730/)
reported the shared `208 − 0.7 × age` relationship, with no difference between
the male and female regression lines in their study. Apex implements Edwards
zone-duration weights; it does not implement the exponential Banister TRIMP
equation that has sex-specific coefficients. Applying those coefficients to
Edwards would change the method incorrectly.

[Gulati et al. (2010)](https://pubmed.ncbi.nlm.nih.gov/20585008/)
derived a different equation from symptom-limited stress tests in asymptomatic
women. That is evidence for a particular population/protocol, not a reason to
silently replace the current mixed-sex adult model for every female athlete.
Individual age-predicted HRmax uncertainty remains visible. A user-verified
measured maximum and explicit model selection would require additional work.

## Laboratory results and donation context

The [WHO 2024 hemoglobin guidance](https://www.ncbi.nlm.nih.gov/books/NBK602185/table/ch5.tab2/)
distinguishes sex, age and pregnancy context. Sex alone does not determine a
correct clinical interpretation. The app therefore preserves the actual
laboratory's supplied intervals rather than declaring every woman nonpregnant
and applying an invented universal female normal range.

Both lab entry surfaces now accept optional lower/upper bounds in the result's
units; Health metrics displays the reported intervals and Lab preserves its
existing out-of-interval display. Bounds are not prefilled from a male or female
template. Reversed or nonfinite intervals are rejected. Ordered-but-unreported
markers remain null and no longer crash list/trend serialization. Migration
`0023` makes the value column nullable to match that ingestion contract; it
rewrites no measurements and refuses downgrade while null measurements exist.

Ferritin still prioritizes the report's lower bound. Its configured 30 ng/mL
fallback is an existing configurable product/donor threshold, **not** a universal
clinical iron diagnosis. The legacy `normal` flag only means not below that
threshold; donation context now explicitly says it is not proof of healthy iron
status or donation clearance. Future donation records are excluded from an
as-of query. Eligibility remains the user/laboratory-recorded date; no
country-, age- or sex-dependent donor eligibility schedule is inferred.
The [WHO ferritin guidance](https://www.who.int/publications/i/item/9789240000124)
also requires inflammation and other context, which Apex does not diagnose.

## Reproductive physiology: real limitations, not completed features

Female profile selection does not imply menstruation, cycle phase,
contraception, pregnancy, menopause or hormone treatment. Those states are not
structured physiological inputs today. Explicit user reports can be stored in
the existing notes/context/check-in paths, but this is **not** a cycle tracker,
pregnancy safety engine or hormone-aware model.

[Schmalenberger et al. (2019)](https://pubmed.ncbi.nlm.nih.gov/31726666/)
supports menstrual-cycle variation in vagal activity. That is a reason to
consider reported context, not an individual phase diagnosis from wearable HRV.
[McNulty et al. (2020)](https://pubmed.ncbi.nlm.nih.gov/32661839/)
reports variable effects and supports individual responses rather than a
universal phase-based performance correction. AI/report prompts explicitly
forbid inferring these states or inventing demographic corrections.

## Deliberately not implemented

1. Arbitrary female multipliers for Recovery, Readiness, Strain, ACWR, sleep or
   training prescriptions: no validated Apex calibration supports them.
2. Replacing Tanaka with Gulati solely because sex is female: populations and
   protocols differ; preserve the existing documented shared model.
3. Universal female lab normality, iron diagnoses or donation eligibility:
   require applicable laboratory/clinical context and jurisdiction.
4. Cycle-phase inference, pregnancy/menopause/hormonal-treatment corrections:
   require explicit structured inputs and validated intended-use models.
5. Recomputing provider VO2max, body fat, calories or proprietary scores:
   Apex lacks their algorithms/calibration; configure demographics at the source.

## Verification

Focused browser checks cover profile-driven male/female SVGs, unchanged
exercise filtering, signup defaults, settings persistence, both lab entry
forms and display of a supplied female hemoglobin interval. Backend checks
use a separate disposable PostgreSQL database and test Redis. New tests use
hand-calculated expected scores, demonstrate each account's own HRV baseline,
verify stale-worker profile refresh, profile revision/approval invalidation,
owned coach/report context and null laboratory measurements. No live provider
account, production data or live AI clinical outcome validation is involved.

Verification completed: 191 scientific/profile/lab/security backend checks;
42 additional report/agent/profile consumer checks; all 69 hermetic agent
evaluations; 32 focused browser checks (including corrected follow-up runs);
production frontend build and English/Italian key/placeholder parity. The
evaluation memory-session adapter was updated to accept `populate_existing`
because it always reads current stored rows; expected scenario outcomes were
not weakened. Migration upgrade and downgrade/refusal were exercised against
PostgreSQL. These checks verify implementation behavior, not physiological
validation of the product's heuristic scores.

Final pre-push review also found a stale-profile race: authentication could
load a profile before an edit committed, and a decision could then combine
old physiological context with a new revision. Decision and coach readers
now reload the profile inside the account lock; report data packs also
refresh their session's profile. Three regression cases use a separate
database session to change sex and timezone after the reader loaded its
profile. The decision localization fixture now persists its requested
locale instead of trying to override the authenticated account with a
detached object. Migration-refusal verification checks that the installed
revision stays unchanged, rather than hardcoding the previous head.

The final local checks cover all 883 backend cases across the full suite
and affected follow-up runs, including opt-in import verification of all
three original Garmin FIT files. All cases passed in their final runs.
Browser verification passed all 121 standard checks and the opt-in test
of those original database presentations (122 total). Production build,
1463-key English/Italian parity, five PWA checks, 26 deterministic runtime
replays, 27 updater checks and generated systemd-unit validation also pass.
Private FIT files and their derived verification data remain outside Git.

For deployment, apply migration `0023` with `uv run --frozen alembic upgrade head`
from the backend directory, deploy the rebuilt frontend and restart API/workers.
This review only exercises a disposable test database; it does not migrate
or change provider settings on a running user's deployment.
