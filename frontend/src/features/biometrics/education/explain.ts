import type { MetricTrend } from "../../../app/api";
import type { EducationFact, MetricExplanation } from "./contract";
import { educationText as text, metricEducationDefinitions } from "./definitions";

// Only concrete source identifiers supplied by the observation API. A generic
// 'observations' origin is not a provider, and account/device preferences are not provenance.
const sourceLabels: Record<string, string> = {
  garmin: "Garmin", whoop: "WHOOP", oura: "Oura", apple_health: "Apple Health",
  coros: "COROS", technogym: "Technogym", fitbit: "Fitbit",
};

/** Deterministic adapter over current API data; no requests and no physiological formulas. */
export function explainMetric(trend: MetricTrend): MetricExplanation | null {
  const definition = Object.hasOwn(metricEducationDefinitions, trend.metric) ? metricEducationDefinitions[trend.metric] : undefined;
  const latest = [...trend.points].reverse().find(point => point.value != null && Number.isFinite(point.value));
  if (!definition || latest?.value == null) return null;
  const fact = (label: string, value: number, signed = false): EducationFact => ({
    label: text(label), display: { value, metric: trend.metric, unit: trend.unit, signed },
  });
  const explanation: MetricExplanation = {
    identity: { metric: trend.metric, label: text(definition.label) },
    semanticType: definition.semanticType,
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
  const calculation = trend.calculation_inputs;
  const expected = definition.contributorMetrics;
  if (definition.semanticType === "apex_derived" && latest.value >= 0 && expected?.length &&
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
  return explanation;
}
