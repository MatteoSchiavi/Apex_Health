import type { EducationText, MetricSemantics } from "./contract";

export interface MetricEducationDefinition {
  label: string;
  semanticType: MetricSemantics;
  definition: string;
  whyItMatters?: string;
  knownInfluences: string[];
  actionableFactors: string[];
  methodology: string[];
  limitations: string[];
  personalRange?: boolean;
  /** Inputs the current backend can expose as a persisted, same-date snapshot. */
  contributorMetrics?: string[];
}

const keys = (group: string, values: string[]) =>
  values.map((value) => `metricEducation.${group}.${value}`);
const definition = (
  label: string,
  semanticType: MetricSemantics,
  definitionKey: string,
  options: {
    whyItMatters?: boolean;
    personalRange?: boolean;
    contributorMetrics?: string[];
    factors?: string[];
    actions?: string[];
    methods?: string[];
    limits?: string[];
  } = {},
): MetricEducationDefinition => ({
  label,
  semanticType,
  definition: `metricEducation.metrics.${definitionKey}.definition`,
  whyItMatters: options.whyItMatters
    ? `metricEducation.metrics.${definitionKey}.why`
    : undefined,
  knownInfluences: keys("factors", options.factors ?? []),
  actionableFactors: keys("actions", options.actions ?? []),
  methodology: keys("methods", options.methods ?? ["recorded_value"]),
  limitations: keys("limits", options.limits ?? ["recorded"]),
  ...(options.personalRange ? { personalRange: true } : {}),
  ...(options.contributorMetrics
    ? { contributorMetrics: options.contributorMetrics }
    : {}),
});

/**
 * Localized prose adapter. Backend registry metadata controls scientific kind,
 * validation and formula versions; exact calculation records supply operands.
 * Consumers retain MetricExplanation; no physiological formulas run here.
 */
export const metricEducationDefinitions: Record<string, MetricEducationDefinition> = {
  systemic_stress: definition("biometrics.systemic_stress", "apex_derived", "systemic_stress", {
    factors: ["sleep", "recent_training", "measurement_context"],
    methods: [], limits: ["estimate_not_clinical"],
  }),
  load_spike: definition("biometrics.load_spike", "apex_derived", "load_spike", {
    factors: ["recent_training", "load_method"],
    methods: [], limits: ["load_aggregate", "estimate_not_clinical"],
  }),
  resting_hr: definition("biometrics.resting_hr", "measured", "resting_hr", {
    whyItMatters: true,
    factors: ["sleep", "recent_training", "stress", "illness", "temperature", "hydration", "measurement_context"],
    actions: ["resting_hr"],
    methods: ["observed_range"],
    limits: ["measured"],
    personalRange: true,
  }),
  hrv_ms: definition("metricView.hrv_ms", "measured", "hrv_ms", {
    whyItMatters: true,
    factors: ["sleep", "recent_training", "stress", "illness", "temperature", "hydration", "measurement_context"],
    actions: ["hrv_ms"],
    methods: ["observed_range"],
    limits: ["measured"],
    personalRange: true,
  }),
  respiration: definition("biometrics.respiration_metric", "measured", "respiration", {
    factors: ["sleep", "illness", "temperature", "measurement_context"],
    actions: ["consistent_measurement"],
    methods: ["observed_range"],
    limits: ["measured"],
    personalRange: true,
  }),
  spo2: definition("biometrics.spo2", "measured", "spo2", {
    factors: ["sleep", "temperature", "measurement_context"],
    actions: ["consistent_measurement"],
    methods: ["observed_range"],
    limits: ["measured"],
    personalRange: true,
  }),
  sleep_duration: definition("biometrics.sleep_duration", "measured", "sleep_duration", {
    factors: ["sleep_timing", "measurement_context"],
    actions: ["sleep_duration"],
    methods: ["sleep_session_estimate"],
    limits: ["sleep_estimate"],
  }),
  weight: definition("biometrics.weight", "measured", "weight", {
    factors: ["measurement_context"],
    methods: ["recorded_value"],
    limits: ["recorded"],
  }),
  body_fat: definition("biometrics.body_fat", "provider_proprietary", "body_fat", {
    factors: ["measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  vo2max: definition("biometrics.vo2max", "provider_proprietary", "vo2max", {
    factors: ["recent_training", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  steps: definition("biometrics.steps", "measured", "steps", {
    factors: ["measurement_context"],
    methods: ["recorded_value"],
    limits: ["recorded"],
  }),
  floors: definition("biometrics.floors", "measured", "floors", {
    factors: ["measurement_context"],
    methods: ["recorded_value"],
    limits: ["recorded"],
  }),
  hydration: definition("biometrics.hydration", "measured", "hydration", {
    factors: ["measurement_context"],
    methods: ["recorded_value"],
    limits: ["recorded"],
  }),
  provider_sleep_score: definition("metricView.provider_sleep_score", "provider_proprietary", "provider_sleep_score", {
    factors: ["sleep", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  sleep_deep: definition("biometrics.sleep_deep_metric", "provider_proprietary", "sleep_deep", {
    factors: ["sleep", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  sleep_rem: definition("biometrics.sleep_rem_metric", "provider_proprietary", "sleep_rem", {
    factors: ["sleep", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  sleep_light: definition("biometrics.sleep_light_metric", "provider_proprietary", "sleep_light", {
    factors: ["sleep", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  restlessness: definition("biometrics.restlessness_metric", "provider_proprietary", "restlessness", {
    factors: ["sleep", "measurement_context"],
    methods: ["provider_estimate"],
    limits: ["provider_estimate"],
  }),
  acute_load: definition("biometrics.acute_load_metric", "apex_derived", "acute_load", {
    factors: ["recent_training", "load_method"],
    methods: ["load_aggregation"],
    limits: ["load_aggregate"],
  }),
  chronic_load: definition("biometrics.chronic_load_metric", "apex_derived", "chronic_load", {
    factors: ["recent_training", "load_method"],
    methods: ["load_aggregation"],
    limits: ["load_aggregate"],
  }),
  acwr: definition("biometrics.acwr_metric", "apex_derived", "acwr", {
    factors: ["recent_training", "load_method"],
    methods: ["acwr_ratio"],
    limits: ["load_aggregate", "acwr_not_target"],
    contributorMetrics: ["acute_load", "chronic_load"],
  }),
  recovery: definition("biometrics.recovery_metric", "apex_derived", "recovery", {
    factors: ["sleep", "recent_training", "stress", "illness", "measurement_context"],
    methods: ["recovery_blend"],
    limits: ["composite_inputs_unavailable", "estimate_not_clinical"],
  }),
  readiness: definition("biometrics.readiness_metric", "apex_derived", "readiness", {
    factors: ["sleep", "recent_training", "stress", "illness", "measurement_context"],
    methods: ["readiness_blend"],
    limits: ["composite_inputs_unavailable", "estimate_not_clinical"],
  }),
  strain: definition("biometrics.strain_metric", "apex_derived", "strain", {
    factors: ["recent_training", "load_method"],
    methods: ["strain_peak"],
    limits: ["load_aggregate", "estimate_not_clinical"],
  }),
  sleep_score: definition("overview.sleep_score", "apex_derived", "sleep_score", {
    factors: ["sleep", "measurement_context"],
    methods: ["sleep_architecture"],
    limits: ["composite_inputs_unavailable", "estimate_not_clinical"],
  }),
  hrv_deviation: definition("biometrics.hrv", "apex_derived", "hrv_deviation", {
    factors: ["sleep", "recent_training", "stress", "illness", "temperature", "hydration", "measurement_context"],
    methods: ["hrv_deviation"],
    limits: ["measured_baseline_deviation", "estimate_not_clinical"],
  }),
};

export const educationText = (key: string, values?: EducationText["values"]): EducationText => ({ key, ...(values ? { values } : {}) });
