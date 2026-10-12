# Descriptive endurance metrics

The running pipeline was implemented and tested before cycling. Versions are `apex-running-v2` and `apex-cycling-v2`. Version 2 adds conservative effort-steadiness eligibility; cycling also rejects invalid or out-of-order power timestamps. The owned activity endpoint computes from current canonical activity inputs, recorded streams/laps, optional profile assertions and voluntary check-in RPE. An input digest includes corrected streams, laps and profile/check-in revisions; stale cached derivatives are not returned.

Every metric exposes `value`, `unit`, `recorded`/`calculated`, formula/version, source dependencies, prerequisites, availability/reason and limitations. Missing prerequisites return null, not an estimated value. EN/IT detail sections explain formulas and limits. Provider summary cadence is recorded; a valid time-weighted stream mean is calculated. Cadence conventions remain provider-specific rather than doubling an unknown running cadence.

## Running

| Metric | Formula and eligibility |
|---|---|
| Average pace | Recorded duration seconds / distance metres × 1000; positive duration/distance |
| Moving pace | Explicit recorded moving/timer seconds / distance × 1000; moving/timer time must be positive and no greater than recorded duration |
| Cadence | Recorded provider summary, otherwise time-weighted recorded cadence samples with >=90% coverage; convention retained |
| Vertical speed | Recorded ascent / full recorded duration × 3600 m/h; not a selected-climb speed |
| Split consistency | Population SD of split pace / mean split pace × 100%; >=3 unique valid splits of >=200m, covering 80–110% of activity distance |
| Aerobic efficiency | Time-weighted mean speed / mean HR; >=90% compatible recorded coverage, gaps <=5s, positive speed and HR |
| Cardiac drift | ((mean HR/mean speed) second moving half / first moving half − 1) × 100%; >=30 minutes valid moving data and a >=30 minute continuous effort, >=90% coverage, pauses excluded, time-weighted speed CV <=10% |
| HR-zone time | Actual provider zone durations, otherwise recorded intervals within explicit dated user-configured bounds; no estimated thresholds |
| Session-RPE load | Recorded duration minutes × voluntary RPE 0–10; separate `session-RPE min` unit |

Provider moving time is preserved when explicitly recorded (Strava moving time, Garmin movingDuration, FIT total_timer_time). Active timer time may include stationary effort; it is a documented provider definition, not a inferred pause detector. Missing speed/HR does not become an average-stream surrogate.

## Cycling

| Metric | Formula and eligibility |
|---|---|
| Mechanical work | Compatible average power × explicit moving/timer seconds / 1000 kJ; mechanical work, not metabolic calories |
| Apex Normalized Power | Fourth root of mean fourth powers of 30-second rolling power means; recorded 1 Hz power, >=95% coverage, >=5 minute continuous segment; no interpolation over gaps |
| Intensity Factor | Apex NP / explicitly confirmed FTP |
| Apex TSS-style | (seconds × Apex NP × IF) / (FTP × 3600) × 100; separate Apex calculation |
| Variability Index | Apex NP / average power from the same valid stream |
| Power–HR decoupling | ((mean HR/mean power) second moving half / first moving half − 1) × 100%; >=30 minute continuous valid power/HR effort, >=90% coverage, explicit pauses excluded, time-weighted power CV <=10% |
| Cadence, ascent, zones, RPE | Same recorded-input boundaries, cycling units/version; power zones additionally supported |

Power zeros are valid recorded samples; negative, non-finite and implausible power samples are rejected. Rolling windows never cross missing segments. FTP is eligible only when explicitly confirmed, dated no later than the activity, and at most 90 days old for that activity. This is a conservative product eligibility window, not a claim about physiological threshold stability. The activity-detail endpoint does not estimate FTP.

## Steady-effort eligibility

For valid paired speed/HR or power/HR intervals, let `dt` be the observed
interval duration and `x` the recorded speed or power. The gate uses:

`mean = sum(dt × x) / sum(dt)`

`CV = sqrt(sum(dt × (x − mean)^2) / sum(dt)) / mean`

Drift/decoupling requires positive mean effort and `CV <= 0.10`. This is a
transparent, conservative implementation eligibility cutoff, not a medical
threshold, physiological zone or injury predictor. It depends on recorded
speed/power variability, never on the resulting HR drift. A large HR change
alone does not make an otherwise eligible recording unavailable.

Alternating 120-second run blocks at 2/5 m/s and cycling blocks at 100/300 W
are ineligible. Constant-effort eligible examples still compute. The gate
does not establish that terrain, weather, sensor variation or unrecorded
effort changes are comparable; interpretation remains descriptive. Quality,
coverage, continuity and pause requirements apply before this gate. Rejected
efforts return null with `requires_steady_speed_effort` or
`requires_steady_power_effort`; unrelated recorded activity metrics remain.

## Legacy daily discipline calculations

`features/discipline.normalized_power` now shares the detail endpoint's
recorded 1 Hz extraction, >=95% coverage, >=300-second continuous segment and
complete 30-second rolling windows. There is no sample-and-hold filling of
sparse recordings. Timestamps must increase strictly and remain inside the
recorded duration. Invalid samples split segments; windows cannot cross gaps.
The scalar legacy API uses recorded duration because it has no moving-time
argument; the detail endpoint additionally excludes explicitly recorded pauses
when compatible moving-time and speed inputs are present.

Legacy variability uses the same eligible power samples as NP. Unavailable NP
also makes dependent efficiency and decoupling unavailable. Its existing
decoupling formula remains `100 × (EF1 − EF2) / EF1`, with `EF = NP / HR`;
it retains the legacy 20-minute minimum and VI <=1.05 gate, and now additionally
requires >=90% valid paired coverage, >=20 continuous minutes and power CV
<=10%. Missing HR intervals are not extended by filtering away missing rows.
Provenance versions are `aerobic-decoupling-v3` and `efficiency-factor-v2`.

Sparse golden recordings now expect null efficiency/decoupling, while separate
dense examples verify the formulas. Existing protocol-configured legacy FTP
and best-power calculations are unchanged; the activity-detail endpoint uses
only explicitly confirmed FTP and adds no estimate.

Configured zones carry an effective date and ordered, non-overlapping named bounds. Lower bounds are inclusive; upper bounds are exclusive. They apply only on/after the declared date, require >=90% valid recorded stream coverage and do not assign values outside the declared bounds. Actual recorded provider zones take precedence. They remain descriptive provider/user definitions, not inferred thresholds.

## Scientific and processing limits

- Mean ratios and drift/decoupling are descriptive summaries. Terrain, temperature, effort variation, sensors and pauses can change them; no causal or diagnostic conclusion follows.
- No running power estimate, inferred threshold, injury score, recovery prediction or performance prediction is added.
- Average pace uses the canonical recorded duration semantics; the moving metric identifies its explicit provider dependency separately.
- Provider load scales remain separate from session-RPE and Apex TSS-style. The day hero never adds them.
- A stream/lap input ceiling of 200,000/2,000 rows makes dependent metrics unavailable instead of calculating from silently truncated evidence.
- Historical comparison returns `not_computed`, not a fabricated compatible baseline.
- Measurements can disappear under existing retention/deletion policies. Dependent metrics then become unavailable.
