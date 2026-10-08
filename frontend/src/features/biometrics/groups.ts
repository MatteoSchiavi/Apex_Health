export const METRIC_GROUPS = [
  { value: "health", label: "completion.health_metrics", groups: [
    { value: "signals", label: "design.body_signals", keys: ["resting_hr", "hrv_ms", "spo2", "respiration"] },
    { value: "sleep", label: "nav.sleep", keys: ["provider_sleep_score", "sleep_duration", "sleep_deep", "sleep_rem", "sleep_light", "restlessness"] },
    { value: "body", label: "design.body_activity", keys: ["weight", "body_fat", "steps", "floors", "hydration"] },
  ] },
  { value: "training", label: "completion.training_metrics", groups: [
    { value: "estimates", label: "design.recovery_sleep", keys: ["readiness", "recovery", "strain", "sleep_score", "hrv_deviation", "systemic_stress", "load_spike"] },
    { value: "load", label: "design.training_load", keys: ["acwr", "acute_load", "chronic_load"] },
    { value: "fitness", label: "completion.fitness", keys: ["vo2max"] },
  ] },
];

export const LEGACY_METRIC_TABS: Record<string, { tab: string; group: string }> = {
  signals: { tab: "health", group: "signals" }, body: { tab: "health", group: "body" },
  recovery: { tab: "health", group: "sleep" }, load: { tab: "training", group: "load" },
  estimates: { tab: "training", group: "estimates" },
};
