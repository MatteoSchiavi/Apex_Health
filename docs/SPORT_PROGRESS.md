# Running and cycling progress

`GET /athlete/sports/{running|cycling}/overview` is authenticated and read-only.
Optional `start` and `end` are inclusive account-local dates. The default is 84
inclusive days ending on account-local today; the maximum is 730 days. UTC SQL
bounds respect DST. Calendar buckets derive from `start_time` and the account's
current timezone, so an old stored `local_date` cannot move an activity into the
wrong day. No AI, remote provider calls, plan activation, or profile writes occur.

## Response contract

The response contains `sport`, `version`, `range`, `state`, `quality`, `totals`,
`weekly`, `monthly`, `recent_activities`, `best_efforts`, `power_duration`,
`long_run_progression`, `aerobic_trend`, `consistency`, `adherence`, `goal_context`,
`ftp`, `body_mass`, and `advanced_metrics`. Every metric includes `value`, `unit`,
`kind`, `formula`, `formula_version`, `source_dependencies`, `availability`,
`unavailable_reason`, `limitations`, `prerequisites`, and `quality`.

Volume buckets sum finite nonnegative recorded metres, seconds and ascent metres,
count canonical activities, and disclose observed-field counts and partial
coverage. No observed field produces `null`; recorded zero remains zero. Empty
weeks have known activity count zero, with unavailable measurement totals. Missing
recordings are not evidence that the athlete did no training. Weekly buckets start
Monday; partial boundary weeks are explicit. Consistency is active observed weeks
/ observed calendar weeks × 100, plus distinct training-day and activity counts.
Provider source quantities remain separate; provider Strain is never added to
session-RPE or Apex TSS-style load.

## Deterministic comparisons

For each eligible running activity, long-run distance change is
`(current_distance_m / longest_prior_30d_distance_m - 1) × 100`. The reference is
the longest owned run with positive finite distance and duration, full/partial
source quality, and a start in `[current_start_UTC - 2592000 seconds, current_start_UTC)`.
The interval is exactly 30 × 24 elapsed hours, including earlier same-day runs;
the current/same-timestamp and later activity starts are excluded. UTC instants
keep DST from changing the observation duration. A historical
reference may precede the requested overview range. Equal longest distances use
earliest start, then ID. The result exposes current/reference IDs and distances,
reference date/start timestamp, and inclusive start/exclusive end UTC timestamps
with `window_duration_s=2592000` and `window_unit=elapsed_seconds`.
No reference or incomplete history produces `null`. This descriptive comparison
does not define safe percentages or predict injury.

Adherence considers due sessions in owned confirmed/active/completed plans,
respecting activation/supersession dates. Completion requires a user-confirmed
activity association or explicit completed check-in. Partial/skipped check-ins
remain distinct and unresolved sessions are not automatically skipped. The
formula is completed / confirmed due sessions × 100; association confirms session
identity and does not certify prescribed intensity or distance. No same-day
matching is attempted. Feedback is returned by actual activity identity.

Recorded best efforts require explicit provider `best_efforts` entries with
positive `distance_m`, `duration_s`, and `duration_convention` (`elapsed` or
`moving`), bounded by the activity's own recorded totals. Minima are calculated
separately per provider, exact distance and convention. These are source-recorded
claims, not independently validated race results; unqualified efforts are absent.
Current importers may not supply these explicit fields.

Speed/HR trends compare the latest eligible activity to the earliest matching
eligible activity on a prior local day. They require explicit provider
`comparison_context` (`effort_type=easy|steady`, route ID, terrain, indoor boolean,
`time_convention=elapsed|moving`), identical provider/discipline/context and HR
means within 3 bpm. Streams need 90% coverage, gaps ≤5s, a continuous 30-minute
segment and time-weighted speed CV ≤10%. Moving convention requires reliable
recorded moving time. Outdoor comparisons additionally require recorded
`temperature_c`, `relative_humidity`, `wind_speed_kmh` with differences ≤3°C,
10 percentage points, and 5 km/h. Missing fields, including the current weather
connector's absent humidity, produce insufficient evidence. The formula is
`(current time-weighted speed / reference time-weighted speed - 1) × 100`.
Eligibility cutoffs are implementation rules, not physiological thresholds;
matching context does not establish causality.

## Cycling and supported activity calculations

Cycling works with activity and HR alone. Detail metrics reuse
`running_metrics` / `cycling_metrics` from `ENDURANCE_METRICS.md`, including
eligible NP, VI, configured/recorded zones, cardiac drift/decoupling and separate
session-RPE load. Cycling speed/HR efficiency uses the existing time-weighted
speed/HR formula with bicycle, coasting, wind and surface limitations. Fixed-width
HR, speed, cadence and power distributions sum recorded interval seconds without
interpolation (gaps ≤5s; ≥90% coverage); these are distributions, not inferred zones.

Best power at 5, 15, 30, 60, 300, 600, 1200, 1800 and 3600 seconds is the maximum
rolling sum / duration inside contiguous recorded 1Hz segments. It reuses the
existing `dense_power` gate: ≥95% coverage, ≥5 minutes continuous recording,
valid bounded power, and pause handling from recorded moving time. Windows never
cross gaps. Each range maximum identifies the winning activity and source. Sparse
power cannot produce an exact curve. Neither a 20-minute best nor 0.95 times that
best is presented as validated FTP. Linear rolling sums avoid the legacy
sample-hold helper's unsuitable batch complexity.

FTP is the current explicitly confirmed dated profile assertion, ≤90 days old
and not after the comparison date. Source is `athlete_profile`, mode
`manually_confirmed`; confirmation is not test-protocol validation. Accepted canonical profile FTP changes now append owned `AthleteEntry` records
with kind `ftp_assertion`, measurement date, watts, source `user_confirmed`, and
profile revision, in the same transaction. Exact retries and unrelated changes do
not append duplicates. Existing profile thresholds are never retroactively
backfilled. `advanced_metrics.ftp_trend` returns the accepted assertion history
for the range, with assertion timestamp and ID; legacy fractions of 20-minute
power remain separate estimates. Goals expose the saved
context; a saved weekly baseline is not automatically a prescribed target.

Body mass reuses owned current available `weight` observations in canonical kg,
within the preceding 30 days and not after the comparison instant. Existing
plausibility validation, flags and analysis exclusions apply. Origin, acquisition,
revision and measurement timestamp remain explicit. Recorded provider mass is
not automatically user confirmed. FTP W/kg uses the eligible overview-end mass;
best-power W/kg uses eligible mass at that activity's start. The formula is watts
/ recorded kg. Future, excluded, incompatible or stale readings yield `null`.

Running dynamics return recorded provider-specific `running_dynamics` values
only for explicit unit-qualified keys: ground-contact time (ms), vertical
oscillation (cm), stride length (m), vertical ratio (%) and left contact balance
(%). Finite implementation bounds reject malformed records; provider values are
never averaged or inferred. Current normalizers may not preserve these inputs.

`distance_half_split` compares pace over equal-distance halves. It uses exact
lap-half distance boundaries with 95–105% activity-distance coverage and a common
timer/elapsed/moving convention, or complete recorded elapsed speed coverage
(sample gaps ≤5s, speed-integrated distance within 5% of activity distance).
Second-half pace / first-half pace minus one, ×100, defines positive (slower),
negative (faster) or even splits. The stream method explicitly uses a sample-hold
approximation; it never bridges missing recordings. Lap timer time is not
silently presented as elapsed time. Separately named lap-average HR/cadence/power
histograms disclose that lap means are not sensor-sample distributions. Recorded
cadence/HR/power relationships use time-weighted Pearson covariance / product of
standard deviations, requiring 90% paired coverage, ≥5 contiguous minutes,
sample gaps ≤5s and nonzero variance. Correlation is not causal guidance.

Critical speed estimates OLS distance-time slope only from at least three
owned distinct explicitly verified maximal race/time-trial records in the
preceding 180 elapsed days. `verified_performance` must declare seconds/metres,
elapsed convention, comparable provider/surface and certified-course,
track-lap or calibrated-treadmill distance method. Eligible durations span 3–20
minutes with at least 300s spread and ratio ≥2; R² ≥0.95, positive slope and
nonnegative distance intercept are explicit implementation gates. The response
reports slope (m/s), distance intercept, R², contributing IDs, timing window and
estimated-model limitations. Unqualified ordinary runs cannot fit this model.

Running endurance durability and cycling fatigue resistance are explicitly
labelled **descriptive efficiency-retention proxies**: late-half effort/HR
efficiency divided by early-half effort/HR efficiency, ×100, in eligible recorded
steady sessions. They require explicit easy/steady context, ≥90% coverage,
≥30 continuous minutes and effort CV ≤10%; cycling uses recorded power.
They do not measure fatigue physiology or exhaustion capacity. Comparable-route
progress reuses the strict recorded route/context/HR matching rules above.
Climbing comparisons require verified recorded segment identities, elapsed
seconds/ascent metres, same provider/discipline/terrain/effort type, distance and
ascent within 2%, and explicit compatible temperature/humidity/wind. Their rate
formula is ascent metres / elapsed seconds ×3600, compared between activities.
Segment scanning is capped at 1,000 entries and reports budget coverage; GPS never
guesses routes or climbs.

Missing compatible recordings report `data_missing` or protocol-specific reasons.
GAP and automatic interval detection still report `unsupported_model`: no
validated method is installed, and the overview does not invent one.

## Bounds and validation

The activity query includes at most 10,000 canonical owned activities plus one
truncation sentinel. Running additionally reads the exact preceding 30-day long-run window and up
to 180 days of recent qualified critical-speed history. Stream
counts select complete recent activities within a 500,000-row request budget;
there is no downsampling for numerical calculations. A count change during
loading invalidates stream calculations. Laps are bounded to 10,000 rows for
20 recent activities; exceeding the cap disables lap calculations. Plans and
body-mass history each have 10,000-row bounds. Truncation is explicit;
incomplete running history cannot produce a longest-reference comparison or
consistency/adherence claim. Power maxima disclose the loaded-history limit.

Pure regression tests cover ranges/DST, missing and actual-zero inputs, longest
references, adherence, dense/sparse power, effort conventions, context eligibility,
mass and distributions. Integration tests cover authentication, account/sport
isolation, timezone correction, canonical source deduplication, confirmed plans,
HR-only mode, mass provenance/exclusions, and budget honesty. Run integration
tests only with the explicitly authorized disposable database runner; the normal
repository fixtures rebuild their configured schema.

## Canonical focus configuration

`AthleteContext` supports prioritized (default) or balanced focus modes, selected
supporting focuses, per-sport weekly minute allocations, and dated seasonal
priority lists. Referenced focuses must be selected; allocations are nonnegative
integers and cannot exceed a configured weekly time budget. Seasonal ranges are
inclusive, increasing, nonoverlapping, and have unique nonempty priorities.
Defaults do not make an empty athlete profile ready.

The shared constraints, Training Day and sport goal context expose
`focus_configuration` with mode, effective priorities, supporting sports,
allocations and the active dated season. Prioritized mode orders existing planned
sessions by effective preferences; balanced mode orders them by scheduled time.
Saved seasonal preferences never generate, activate or alter workouts.
