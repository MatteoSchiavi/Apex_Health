import { useUi } from "../app/stores/ui";
export const METRIC_LABELS: Record<string, string> = {
  resting_hr: "biometrics.resting_hr",
  hrv_deviation: "biometrics.hrv",
  spo2: "biometrics.spo2",
  respiration: "biometrics.respiration_metric",
  readiness: "biometrics.readiness_metric",
  recovery: "biometrics.recovery_metric",
  strain: "biometrics.strain_metric",
  sleep_score: "overview.sleep_score",
  acwr: "biometrics.acwr_metric",
  acute_load: "biometrics.acute_load_metric",
  chronic_load: "biometrics.chronic_load_metric",
  illness_risk: "biometrics.illness_risk",
  injury_risk: "biometrics.injury_risk",
  weight: "biometrics.weight",
  body_fat: "biometrics.body_fat",
  vo2max: "biometrics.vo2max",
  steps: "biometrics.steps",
  floors: "biometrics.floors",
  hydration: "biometrics.hydration",
  sleep_duration: "biometrics.sleep_duration",
  sleep_deep: "biometrics.sleep_deep_metric",
  sleep_rem: "biometrics.sleep_rem_metric",
  sleep_light: "biometrics.sleep_light_metric",
  restlessness: "biometrics.restlessness_metric",
};
export type Assessment = {
  tone: "neutral" | "positive" | "warning" | "alert";
  key: string;
};
// Only scored metrics and a measured deviation have interpretable thresholds.
// Absolute body values and arbitrary means are not health reference ranges.
export const LEGACY_HEURISTICS = [
  "readiness",
  "recovery",
  "strain",
  "sleep_score",
  "illness_risk",
  "injury_risk",
];
export function assess(key: string, value: number | null): Assessment {
  if (value === null) return { tone: "neutral", key: "design.no_data" };
  if (LEGACY_HEURISTICS.includes(key))
    return { tone: "neutral", key: "lab.heuristic" };
  if (key === "hrv_deviation")
    return value < -20
      ? { tone: "warning", key: "design.below_baseline" }
      : { tone: "neutral", key: "design.vs_baseline" };
  return { tone: "neutral", key: "design.recorded" };
}
export function useUnits() {
  const imperial = useUi((s) => s.me?.units === "imperial");
  return {
    distance: (m: number | null | undefined) =>
      m == null ? null : m / (imperial ? 1609.344 : 1000),
    distanceUnit: imperial ? "mi" : "km",
    elevation: (m: number | null | undefined) =>
      m == null ? null : m * (imperial ? 3.28084 : 1),
    elevationUnit: imperial ? "ft" : "m",
    weight: (kg: number | null | undefined) =>
      kg == null ? null : kg * (imperial ? 2.2046226 : 1),
    weightUnit: imperial ? "lb" : "kg",
    speed: (kmh: number | null) =>
      kmh == null ? null : kmh / (imperial ? 1.609344 : 1),
    speedUnit: imperial ? "mph" : "km/h",
    metric: (key: string, value: number | null) =>
      key === "weight" && value != null && imperial
        ? value * 2.2046226
        : key === "hydration" && value != null && imperial
          ? value / 29.57353
          : value,
    metricUnit: (key: string, unit: string) =>
      imperial && key === "weight"
        ? "lb"
        : imperial && key === "hydration"
          ? "fl oz"
          : unit,
  };
}
export function localDay(timezone?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  return ["year", "month", "day"]
    .map((type) => parts.find((p) => p.type === type)?.value)
    .join("-");
}
export function shiftDay(day: string, amount: number) {
  const date = new Date(day + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}
