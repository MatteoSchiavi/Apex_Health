# Understand this metric

Metric detail pages include a collapsed educational disclosure after the latest
value, personal range and immediate interpretation, and before the history chart.
It uses native disclosure semantics, the existing design tokens, and English and
Italian copy. Expanded sections stack on phones and use two columns at the
existing `md` breakpoint. Opening it performs no requests, inference or calculation
of physiological scores.

## Contract and current source

`frontend/src/features/biometrics/education/contract.ts` defines
`MetricExplanation`: identity, semantic type, contextual facts, optional actual
calculation contributors, definition, possible influences, modifiable factors,
methodology, provenance and limitations. Text references the existing locale
catalog; numeric facts retain metric identity and units for the shared unit
preferences and duration formatter.

`MetricEducationDisclosure` renders that contract. It does not import the
education definitions, calculate scores, select sources or reconstruct formulas.
`definitions.ts` supplies the current small curated metadata source;
`explain.ts` deterministically adapts it and the existing metric response into
the contract. A future canonical metric registry can replace or enrich that
source/adapter while preserving the component and metric-detail placement.

Known influences are separate from actual calculation contributors. Their
presence does not mean that Apex observed them today or identified a cause.
General actions are deliberately conservative; values do not generate
personalized prescriptions.

## Semantic behavior and coverage

| Behavior | Current coverage |
| --- | --- |
| Measured / recorded; **Your context** | Resting heart rate, overnight HRV, respiration, SpO₂, sleep duration, weight, steps, floors, recorded fluid intake |
| Provider estimate; **Your context** | Device sleep score, estimated body fat and VO₂ max, sleep-stage durations, restlessness |
| Apex-derived; **Why today?** only with a valid stored input snapshot | ACWR |
| Apex-derived; **Your context**, no input reconstruction | Recovery, readiness, strain, Apex sleep-architecture score, HRV deviation, acute and chronic load |

Measurement versus estimate describes the currently imported data, not clinical
accuracy. Sleep duration is explicitly described as a device estimate, and logged
fluid intake is not a measurement of body hydration. The proprietary-provider
category means Apex does not have that source's exact calculation.

For personal-range metrics, the context uses the existing API's P10–P90 band,
median and comparable observation count over the preceding 28 days, excluding
the assessed day. The median comparison is distinct from the chart's selected
window mean and the separate `delta_30d` statistic. Missing, invalid or stale
bands do not create a baseline comparison. Coverage is never inferred from the
chart point count. A band describes recorded history, not clinical thresholds.

Provider identity is shown only when the existing observation response supplies
a recognized source for that assessed date. It is never guessed from account
preferences, an active device, a generic `observations` origin or adjacent data.
Many legacy/provider trends lack reliable source identity; their provenance is
omitted rather than fabricated.

## Actual ACWR inputs

The existing `/metrics/acwr` response optionally includes `calculation_inputs`:
metric identity, assessed date, stored acute/chronic load values and units, and
the persisted load-method identifier. These fields are read in the same bounded
database query and from the same `DailyFeature` row as the latest displayed ACWR
point. The score and its physiological calculations are unchanged; there is no
database migration and no additional frontend request.

The backend rejects missing/nonfinite inputs, invalid load values, a nonpositive
chronic denominator or absent method/unit metadata. The adapter also rejects
wrong metric/date, incomplete/duplicate constituents and incompatible units.
The frontend displays these inputs; it does not recompute the ratio or invent
weights, causal directions, availability percentages or formula versions.
Unknown method identifiers receive no invented methodological description.

## Deliberate limits before the scientific refactor

- **Recovery:** its history stores the resulting score but not the full exact
  constituent snapshot: resting-HR deviation, the original HRV baseline,
  prior-day strain, effective weights and available-component normalization.
  Re-querying surrounding data could produce different inputs after an import
  or revision. Its safe definition/general methodology remain available, but
  **Why today?** is omitted. Persisted contributor formalization belongs to the
  future scientific architecture work.
- **Other Apex composites and load aggregates:** current trend responses do
  not expose complete calculation snapshots. Their documented methodology is
  general; no exact-day contributor breakdown is reconstructed.
- **Illness and injury risk estimates:** no new disclosure is attached. Their
  heuristic probability-like names and scientific interpretation need the
  future review; generic educational placeholders would give unjustified
  authority. Existing pages and their warnings remain available.
- **Full methodology documentation:** the compact disclosure already presents
  the reliably available methodology and limitations. A separate drawer or
  documentation subsystem would duplicate that content at this stage.
- No scientific metrics, provider semantics, score weights, baselines, database schema
  or existing immediate interpretations were migrated by this feature.
- The disclosure fits at 320 px without adding overflow. The existing app
  header and history selector extend past that very narrow viewport, even
  with the disclosure closed; that broader responsive cleanup is outside this
  feature. Phone checks at 390 px also verify the whole page fits.

## Verification

`frontend/tests/metric-education.spec.ts` covers deterministic contracts,
semantics, unsupported/missing/stale data, locale content, input authenticity,
default collapsed state, pointer/keyboard toggles, accessible state and focus,
unchanged hero/chart geometry, graph ordering, request-free toggles, responsive
English/Italian content and automated accessibility. The existing metric
interpretation tests remain in place.

`backend/tests/test_metric_calculation_inputs.py` verifies same-row ACWR
snapshots, ownership/date boundaries, invalid metadata/values, absence of stale
fallbacks and lack of invented contributors for Recovery and measured values.
