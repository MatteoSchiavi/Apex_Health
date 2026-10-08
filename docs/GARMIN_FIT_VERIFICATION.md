# Original Garmin strength recording verification

8 October 2026. Scope: the three original recordings supplied after the
`b6ac98a` release. This supplements the earlier synthetic-only verification;
it is not another review of the entire alpha program. The originals and private
derived JSON/screenshots are excluded from Git. No production account was used.

## Findings and corrections

**HIGH — Exported session timestamp removes sets and samples — FIXED.**
Location: `backend/app/services/fit_import.py`, `import_original` session
projection, now centralized in `session_end` (line 26) and `project_original`.
All three exports repeat the session start in the session summary's timestamp.
The previous code treated it as the end: every strength set failed the
half-open session window, and streams after the first sample were discarded.
Reproduce with any of the three originals on `b6ac98a`; unbounded set parsing
returns sets, while session-bounded parsing returns zero. The fix uses recorded
elapsed duration when the timestamp cannot be an end, includes pauses and
allows half-second whole-timestamp rounding for the final stream sample.
The existing synthetic test supplied a correct end timestamp and could not
catch the export shape. A new synthetic regression includes a repeated start,
pause, late set, final sample and genuinely out-of-window sample.

**MEDIUM — Numeric category arrays and unrelated title indices mislabel
movements — FIXED.** Location: `backend/app/services/exercise_catalog.py:124`
and `:147`, `fit_exercises`. fitdecode decodes scalar category enums but leaves
arrays numeric. The previous lookup produced numeric labels and missing body
groups; category zero also fell through a truthiness check. The third file
has independently ordered exercise-title catalogue indices and workout-step
indices: joining those indices mislabeled squat sets as calf raises and
deadlifts as squats. The fix decodes the selected category through the bundled
FIT enum and matches optional titles by category/subtype identity. Unknown
first detections remain unknown; alternative guesses do not become extra
exercises. The original scalar-only fixture lacked array and title messages.
The regression now verifies category zero, arrays, conflicting title indices,
subtypes and unknown-first detections with known alternatives.

**MEDIUM — Duplicate uploads cannot repair old parser projections — FIXED.**
Location: `backend/app/services/fit_import.py:109`, existing-import branch.
Previously, a matching owned hash returned immediately, leaving an empty gym
view even after a parser update. Repeat uploads now reproject the linked owned
activities under the existing account/import locks. Missing samples are inserted
without duplicate offsets; existing encrypted originals and source links are
retained. A regression simulates an old empty exercise projection and truncated
stream, repeats the upload, and checks repaired data, one original/link/activity
and separate ownership when another account uploads the identical bytes.
The earlier idempotency test checked duplicates but not repair after a parser
change; it should have included this scenario.

**NO ISSUE within this scope:** no schema or migration changes, new provider
credentials, outbound provider calls or shared API contract changes. Unknown
movement classifications are retained rather than filled from heart rate,
other users' text or alternative watch guesses. The original encrypted bytes
are preserved and independently compared with each supplied file.

## File results

| Original file | Active records | Rep-based sets shown | Reps shown | HR samples retained | Sets with unspecified movement |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20618693487_ACTIVITY.fit | 31 | 31 | 274 | 5,721 | 8 |
| 21080191904_ACTIVITY.fit | 22 | 22 | 191 | 3,973 | 2 |
| 24617577487_ACTIVITY.fit | 25 | 21 | 227 | 4,195 | 9 |

The third recording has four ACTIVE records with no repetitions: bike,
warm-up, chop and calf raise. The rep-based gym contract cannot display these
as counted rep sets. They remain in the preserved original; supporting timed
exercise duration would need a separate API/UI change. No repetition counts
were invented. The unspecified sets retain their recorded reps and weights
but cannot justify a body region. Watch-classified names are recorded
classifications, not proof that the watch identified the movement correctly.

## Verification and remaining deployment work

Local targeted backend run: **31 passed**, including real-file import, byte
preservation, independent raw ACTIVE/repetition/weight comparisons, every
original record timestamp/heart rate, activity-detail/stream API projections,
repeat uploads and account isolation. Chromium: **9 passed**, including actual
database/API presentations for all three originals and all sport-view
regressions. Each enabled body region was keyboard-selected and checked against
the displayed exercise list. Browser authentication and unrelated account
navigation remain fixtures; this does not prove a live server import. Private
screenshots were inspected for the gym presentation.

To repeat privately, put original `.fit` files in a local directory and set
`APEX_FIT_VERIFICATION_DIR`. On a **disposable test database** with the standard
test environment, run `tests/test_original_strength_recordings.py` along with
the synthetic regressions. Set `APEX_FIT_VERIFICATION_OUTPUT` to an absolute
private JSON output path; pass the same variable to Playwright for
`tests/original-strength-recordings.spec.ts`. Without these variables the
private-file tests skip; synthetic regression tests still run in CI. Never set
`APEX_TEST_DATABASE_RESET=1` on a production database.

Owner action: deploy the tested fix, then upload these three originals through
the existing FIT import. Already imported files repair their own projections.
Previously synced Garmin activities may merge only when the existing sport,
start-time and duration reconciliation checks match. No production import or
server deployment was performed here. Missing exercises not recorded by the
watch and genuinely unknown classifications cannot be backfilled by inference.

The earlier synthetic-only validation could not verify these actual recordings;
the separate tests above now establish these three file shapes.
Native/device, real provider authorization, 03:00 production execution and
backup verification gates in VERSION_COMPLETION remain unchanged.
