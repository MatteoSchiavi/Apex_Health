import type { MetricTrend } from "../../../app/api";
import type { EducationFact, MetricExplanation } from "./contract";
import { educationText as text, metricEducationDefinitions } from "./definitions";

// Only concrete source identifiers supplied by the observation API. A generic
// 'observations' origin is not a provider, and account/device preferences are not provenance.
const sourceLabels: Record<string, string> = {
  garmin: "Garmin", whoop: "WHOOP", oura: "Oura", apple_health: "Apple Health",
  apple_healthkit: "Apple HealthKit", coros: "COROS", technogym: "Technogym", fitbit: "Fitbit",
};

/** Deterministic adapter over current API data; no requests and no physiological formulas. */
export function explainMetric(trend: MetricTrend): MetricExplanation | null {
  const definition = Object.hasOwn(metricEducationDefinitions, trend.metric) ? metricEducationDefinitions[trend.metric] : undefined;
  const latest = [...trend.points].reverse().find(point => point.value != null && Number.isFinite(point.value));
  if (!definition || latest?.value == null) return null;
  const fact = (label: string, value: number, signed = false): EducationFact => ({
    label: text(label), display: { value, metric: trend.metric, unit: trend.unit, signed },
  });
  const canonical = trend.definition?.id === trend.metric ? trend.definition : null;
  const semanticType = canonical?.kind === "provider" ? "provider_proprietary"
    : canonical?.kind === "measured" ? "measured"
    : canonical?.kind === "derived" || canonical?.kind === "heuristic" ? "apex_derived"
    : definition.semanticType;
  const explanation: MetricExplanation = {
    identity: { metric: trend.metric, label: text(definition.label) },
    semanticType,
    heuristic: canonical?.kind === "heuristic",
    context: [fact("metricEducation.current_value", latest.value)],
    definition: text(definition.definition),
    whyItMatters: definition.whyItMatters ? text(definition.whyItMatters) : undefined,
    knownInfluences: definition.knownInfluences.map(key => text(key)),
    actionableFactors: definition.actionableFactors.map(key => text(key)),
    methodology: definition.methodology.map(key => text(key)),
    provenance: [],
    limitations: definition.limitations.map(key => text(key)),
  };
  const ref = trend.reference_range;
  // A stale band must not be described as the current value's personal baseline.
  if (definition.personalRange && ref && ref.as_of === latest.date) {
    const band = ref.empirical_range;
    if (ref.state === "available" && band && band.every(Number.isFinite) && band[1] >= band[0]) {
      if (ref.median != null && Number.isFinite(ref.median)) {
        explanation.context.push(fact("metricEducation.vs_baseline", latest.value - ref.median, true));
      }
      const state = latest.value < band[0] ? "below" : latest.value > band[1] ? "above" : "within";
      explanation.context.push({ label: text("metricEducation.range_status"), display: text(`metricView.range_${state}`) });
    }
    if (Number.isInteger(ref.sample_count) && ref.sample_count >= 0) {
      explanation.context.push({ label: text("metricEducation.comparable_data"), display: text(trend.metric === "hrv_ms" ? "metricEducation.coverage_nights" : "metricEducation.coverage_days", { count: ref.sample_count }) });
    }
    const source = Object.hasOwn(sourceLabels, ref.origin) ? sourceLabels[ref.origin] : undefined;
    if (source) explanation.provenance.push(text("metricEducation.source_value", { source }));
  }
  const levels = ["measured", "provider_proprietary", "deterministic_derived", "established_formula", "heuristic", "experimental", "research_only"];
  if (canonical && levels.includes(canonical.validation_level)) {
    explanation.methodology.push(text(`metricEducation.registry.validationLevels.${canonical.validation_level}`));
  }
  const calculation = trend.calculation_inputs;
  const expected = definition.contributorMetrics;
  if (semanticType === "apex_derived" && latest.value >= 0 && expected?.length &&
      calculation?.metric === trend.metric && calculation.as_of === latest.date &&
      calculation.contributors.length === expected.length &&
      expected.every(metric => calculation.contributors.filter(input => input.metric === metric).length === 1) &&
      calculation.contributors.every(input => Number.isFinite(input.value) && input.value >= 0 && input.unit.trim()) &&
      // ACWR's stored chronic input must exist and be positive. No ratio is recalculated here.
      calculation.contributors.every(input => input.metric !== "chronic_load" || input.value > 0) &&
      new Set(calculation.contributors.map(input => input.unit)).size === 1) {
    explanation.actualCalculation = {
      asOf: calculation.as_of,
      contributors: expected.map(metric => {
        const input = calculation.contributors.find(input => input.metric === metric)!;
        return { label: text(metricEducationDefinitions[metric].label), display: { ...input } };
      }),
    };
    // Only known, curated summaries of the persisted method; unfamiliar IDs are omitted.
    if (["garmin_recorded", "edwards_trimp"].includes(calculation.methodology ?? "")) {
      explanation.methodology.push(text(`metricEducation.methods.${calculation.methodology}`));
    }
  }
  const snapshot = trend.calculation_provenance;
  const object = (value: unknown): value is Record<string, unknown> => value != null && typeof value === "object" && !Array.isArray(value);
  const exact = semanticType === "apex_derived" && snapshot && snapshot.metric === trend.metric
    && snapshot.as_of === latest.date && Number.isFinite(snapshot.value)
    && Math.abs(snapshot.value - latest.value) <= 0.000001
    && typeof snapshot.formula_version === "string" && snapshot.formula_version.trim()
    && object(snapshot.inputs) && object(snapshot.components) && object(snapshot.weights)
    && object(snapshot.baselines) && object(snapshot.sources) && object(snapshot.coverage)
    && Array.isArray(snapshot.missing_inputs) && snapshot.missing_inputs.every(input => typeof input === "string")
    && Object.values(snapshot.components).every(component => object(component)
      && typeof component.active === "boolean"
      && (!component.active || (typeof component.normalized_weight === "number" && Number.isFinite(component.normalized_weight) && component.normalized_weight >= 0)));
  if (exact) {
    explanation.limitations = explanation.limitations.filter(item => item.key !== "metricEducation.limits.composite_inputs_unavailable");
    explanation.methodology.push(text("metricEducation.registry.formulaVersion", { version: snapshot.formula_version }));
    if (["sufficient_coverage", "limited_coverage", "see_source_coverage"].includes(snapshot.coverage.status)) {
      explanation.methodology.push(text(`metricEducation.registry.coverage.${snapshot.coverage.status}`));
    }
    const inputNames: Record<string, string> = {
      hrv_deviation: "hrv_deviation", hrv_drop: "hrv_drop", resting_hr_deviation: "resting_hr_deviation",
      resting_hr_elevation: "resting_hr_elevation", sleep_quality: "sleep_quality", prior_day_strain: "prior_day_strain",
      respiration_elevation: "respiration_elevation", journal_soreness_fatigue: "journal_soreness_fatigue",
      recovery: "recovery", sleep_architecture: "sleep_architecture", acwr: "acwr", rem_pct: "rem_pct", deep_pct: "deep_pct",
      total_sleep_s: "total_sleep_s", awake_s: "awake_s", active_days: "active_days", day_load: "day_load", mean28: "mean28", std28: "std28",
    };
    const operands: Record<string, string[]> = { efficiency: ["total_sleep_s", "awake_s"], acwr_spike: ["acwr"], load_spike: ["day_load", "mean28", "std28", "active_days"] };
    const activeInputs = new Set(Object.entries(snapshot.components)
      .filter(([, component]) => component.active && component.normalized_weight != null && component.normalized_weight > 0)
      .flatMap(([name]) => operands[name] ?? [name]));
    explanation.calculationDetails = Object.entries(snapshot.components)
      .filter(([, component]) => component.active && Number.isFinite(component.value)
        && component.normalized_weight != null && Number.isFinite(component.normalized_weight) && component.normalized_weight > 0)
      .flatMap(([name, component]) => [
        { label: text("metricEducation.registry.componentValue", { input: name }),
          display: { metric: "normalized_component", value: component.value!, unit: "fraction" } },
        { label: text("metricEducation.registry.effectiveWeight", { input: name }),
          display: { metric: "normalized_weight", value: component.normalized_weight!, unit: "fraction" } },
      ]);
    if (trend.metric !== "acwr" && calculation?.metric === trend.metric && calculation.as_of === latest.date
      && Array.isArray(calculation.contributors) && calculation.contributors.length
      && new Set(calculation.contributors.map(input => input.metric)).size === calculation.contributors.length
      && calculation.contributors.every(input => Object.hasOwn(inputNames, input.metric) && activeInputs.has(input.metric)
        && Number.isFinite(input.value) && input.value === snapshot.inputs[input.metric] && typeof input.unit === "string" && input.unit.trim())) {
      explanation.actualCalculation = { asOf: latest.date, contributors: calculation.contributors.map(input => ({
        label: text(`metricEducation.inputNames.${input.metric}`), display: { ...input },
      })) };
    }
    const labelInputs = (inputs: string[]) => inputs.filter(name => Object.hasOwn(inputNames, name));
    // Missing-input labels stay locale keys, with no invented values.
    for (const input of labelInputs(snapshot.missing_inputs)) {
      explanation.limitations.push(text("metricEducation.registry.missingInput", { input }));
    }
    for (const [name, component] of Object.entries(snapshot.components)) {
      if (!component.active) explanation.limitations.push(text("metricEducation.registry.missingComponent", { input: name }));
    }
    for (const [name, baseline] of Object.entries(snapshot.baselines)) {
      if (object(baseline) && Number.isInteger(baseline.observed_days) && baseline.observed_days >= 0
        && Number.isInteger(baseline.required_days) && baseline.required_days > 0) {
        explanation.provenance.push(text("metricEducation.registry.baselineCoverageNamed", {
          baseline: name, count: baseline.observed_days, required: baseline.required_days,
        }));
      }
    }
    for (const [name, source] of Object.entries(snapshot.sources)) {
      if (!activeInputs.has(name) || !object(source)) continue;
      const provider = typeof source.provider === "string" && Object.hasOwn(sourceLabels, source.provider) ? sourceLabels[source.provider] : undefined;
      if (provider) explanation.provenance.push(text("metricEducation.registry.inputSource", { input: name, source: provider }));
      else if (source.attribution === "unavailable") explanation.provenance.push(text("metricEducation.registry.sourceUnavailable", { input: name }));
    }
    for (const [name, weight] of Object.entries(snapshot.weights)) {
      if (object(weight) && Number.isInteger(weight.version) && weight.version != null && weight.version > 0) {
        explanation.provenance.push(text("metricEducation.registry.weightVersion", { input: name, version: weight.version }));
      }
    }
  } else if (semanticType === "apex_derived" && trend.metric !== "acwr") {
    explanation.limitations.push(text("metricEducation.registry.snapshotUnavailable"));
  }
  return explanation;
}
