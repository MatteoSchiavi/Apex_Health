# Scientific metric registry and calculation provenance

`backend/app/metrics/registry.py` is the canonical numeric and scientific definition layer. The API obtains its numeric catalog through `metric_catalog()` and scientific metadata through `MetricDefinition.to_dict()`. Definitions cover every catalog metric and the major baseline, discipline, load-carryover, and provider-context metrics. Localized frontend prose remains an adapter: `MetricExplanation`, `definitions.ts`, `explain.ts`, and `MetricEducationDisclosure` retain the existing deterministic disclosure UX.

Definitions state identity, display name, category, unit and scale, measured/provider/derived/heuristic kind, validation level, implemented formula version, actual input requirements, source eligibility, baseline requirements, missing-data behavior, interpretation, limitations, and allowed/prohibited claims. `scale` is the display divisor: recorded sleep seconds / 3600 gives hours. Provider estimates are explicitly proprietary; they do not inherit the validity of a measured physiological quantity. A deterministic calculation is not proof of physiological or predictive validation.

## Scientific interpretation

Recovery, readiness, sleep architecture, strain, systemic stress, load spike, and cross-discipline load carryover use heuristic transforms or normalization constants. These are descriptive estimates, without validated individual injury or illness probabilities or invented statistical confidence percentages. ACWR describes recent load relative to the longer window; its overlapping windows and arbitrary transform constants do not establish a universal optimal ratio band. Provider readiness/recovery/strain/Body Battery remain provider context and are not interchangeable with Apex outputs.

The renamed systemic-stress signal describes HRV drop, resting-HR elevation, respiration elevation, and stated journal soreness/fatigue. The load-spike indicator describes relative load changes. Historical terminology is handled by the database migration; new definitions and calculations use the neutral names.

FTP uses 0.95 times the best 20-minute recorded-power mean when the discipline enables the protocol. Finding such a window does not establish that an athlete performed a maximal test. Efficiency factor is a road-cycling power/HR proxy. Aerobic decoupling uses half-session normalized power/HR with independent, correctly aligned half offsets; its physiological interpretation remains experimental.

## Observation and baseline eligibility

Wellness baselines average observed days over `[D−28,D−1]`, excluding the assessed day, and require at least seven observations. Six observations produce an unavailable baseline, never a neutral physiological deviation. Percentage deviations also require a positive baseline denominator. The snapshot preserves each observed daily value and the actual observation count, window boundaries, and aggregation.

The HRV engine accepts the legacy `overnight_avg`/`5min` series and explicit `rmssd_overnight`/`rmssd_5min` types. SDNN and unknown reading types cannot enter that series. Known origins require a compatible semantic rule and explicitly recorded RMSSD method. Legacy-null origin/method rows form a separate un-attributed context, never a known provider's baseline. For the assessed day, the main provider wins when it supplies an eligible observation; otherwise a deterministic eligible context is selected from the latest observed day, preferring overnight context. Every baseline day must match that one origin, method and overnight/daytime context. Overnight observations are averaged; daytime observations use the median. Provider or measurement-context changes rebuild coverage rather than borrowing a previous source's baseline. Device identity is not persisted and remains a stated limitation. Apple SDNN must stay separate from RMSSD.

HRV origin/method and sleep origin are persisted for new normalized observations. Legacy-null attribution is preserved as unknown rather than backfilled by inference. Canonical biometric writers record the actual field supplier in `source_metrics._canonical_sources`; equal-value writes still transfer field ownership. The engine uses this explicit supplier for resting-HR observations and comparable baselines. It never infers a supplier from surrounding provider values. Legacy rows without this record have null provider and explicit unavailable attribution. Canonical table/row references and HRV observation timestamps are retained. Sleep architecture selects one coherent provider/night and respiration baselines use the same sleep origin. Provider-method compatibility follows `app/connectors/semantics.py`; shared units do not establish unconditional cross-provider or cross-device equivalence.

Load uses one selected method for both acute and chronic windows: recorded Garmin load or measured-HR Edwards TRIMP. These have separate scales and no unsupported conversion. Nonfinite, negative, boolean and malformed recorded-load values are ineligible and count as excluded unknown observations, never fabricated zeros. A missing load source is not a measured rest day. Without any eligible selected-method session evidence, acute/chronic load, ACWR and strain are unavailable. A date without recorded sessions can be described as zero only after eligible recorded history exists; this is an explicit recording assumption, not proof of complete capture. Recorded sessions with no eligible load leave day strain unavailable. Partially covered rolling sums retain selected observed loads and disclose excluded sessions.

The load-spike distribution component requires seven prior active days. It is absent below that threshold and the remaining available ACWR component is renormalized. The formula version is `load-spike-v2`. Recovery now consumes Apex sleep architecture rather than an incompatible proprietary vendor sleep score, versioned `recovery-v2`. WHOOP sleep-performance percentage remains provider-specific context. The prior zero-valued cold-start component implied neutrality without supporting history and is no longer used. The aerobic-decoupling offset correction is versioned `aerobic-decoupling-v2`.

## Persisted calculation record

New engine computations write nullable `daily_features.calculation_provenance` with the score row, in the same upsert. Old rows remain null until explicitly recomputed from available source observations. The engine never reconstructs or approximates a past explanation at request time.

```json
{
  "schema_version": 1,
  "as_of": "2026-10-05",
  "timezone": "Europe/Rome",
  "metrics": {
    "recovery": {
      "metric": "recovery",
      "value": 72.5,
      "formula_version": "recovery-v2",
      "validation_level": "heuristic",
      "inputs": {},
      "components": {},
      "weights": {},
      "baselines": {},
      "sources": {},
      "missing_inputs": [],
      "missing_components": [],
      "coverage": {},
      "methodology": {}
    }
  }
}
```

This example shows structure only. Real snapshots populate raw calculation inputs, normalized component values, selected weight amounts, exact configuration row IDs/versions/effective instants, active normalized weights, observed baseline values/counts/windows, source records and missingness. Score values match the persisted numeric score rounded to six decimal places. Component transforms are shared with the score functions, preventing an independent explanatory approximation.

Raw inputs and normalized components are different: a recovery `hrv_deviation` input is percent deviation; its component is a 0..1 heuristic transform. A systemic-stress `hrv_drop` input is raw HRV deviation, with the transformed drop in its component. `sleep_quality` is the actual Apex architecture score from that same calculation row, not a proprietary vendor sleep score or measured sleep-quality percentage. Readiness stores its actual calculated recovery/sleep inputs, rather than re-reading the six-decimal rounded columns. Prior-day strain is included as a nested exact calculation record. Journal component methodology includes the observed soreness/energy means and counts. Load calculations preserve daily series, selected method and coverage; load carryover preserves separate discipline series.

`coverage` describes available components and effective weight sums, not statistical confidence. Missing sensor inputs, absent configuration weights and insufficient baselines must not be presented as normal physiology. Sensor completeness and formula coverage are separate concepts: a fully recorded sensor day can still lack a usable prior baseline or load source.

## Presentation contract

A presentation adapter must read the provenance from the exact `DailyFeature` row whose non-null value is assessed. `app.metrics.provenance.valid_snapshot` rejects absent/unsupported schema, mismatched local date, mismatched metric or score, absent formula identity and nonfinite nested numeric values. It does not fetch another day, recompute inputs, infer vendor identity or invent confidence.

Legacy ACWR's authentic same-row `training_load_acute`, `training_load_chronic`, and `load_metadata` contract remains valid. The JSON record adds provenance without weakening its finite-value, positive-denominator or method/unit checks. Measured observations stay under “Your context”; proprietary provider algorithms are not exposed as invented constituents. “Why today?” is available only for an authentic validated assessed-row calculation record. Known influences, personal P10–P90 ranges, and genuine calculation contributors stay distinct.

## Verification

`backend/tests/test_metric_registry.py` provides database-independent cases for catalog and scientific metadata coverage, exact weighted-score reproduction, selected weight version identities, baseline warm-up, missing load evidence, excluded sessions, HRV method separation, stale/invalid provenance, provider/method/measurement-context separation, coherent night selection, proprietary-score independence and second-half decoupling offsets. Existing feature-engine golden, API same-row ACWR, migration and frontend disclosure tests remain the integration gates. There are no runtime LLM calls in definition or provenance construction.

## Independent review corrections

CSV HRV without declared method/context is retained with origin `csv_import`,
null method and `reading_type=unspecified`. It cannot enter the RMSSD recovery
series. Migration 0022 adds this context; downgrade refuses while such readings
exist instead of relabeling or deleting them. Historical unattributed readings
are preserved and are not retroactively assigned a provider or method.

Composite weights must be finite and positive to participate. Disabled or invalid
weights do not claim active coverage. Canonical imports and calculation writes
share the account erasure lock. Native HealthKit deletions invalidate affected
calculation caches and their 28-day dependents, including adjacent sleep wake
dates; later computation uses the remaining recorded sources.
