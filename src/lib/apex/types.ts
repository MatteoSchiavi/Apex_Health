/**
 * Apex Health — domain types (mirrors the real backend API shapes).
 * Frontend is responsible for presentation only; these types represent
 * the actual API contracts the backend exposes.
 */

export interface ScoreBlock {
  value: number | null;
  delta_7d: number | null;
}

export type Locale = "en" | "it";
export type Theme = "dark" | "light";
export type Units = "metric" | "imperial";

export interface Me {
  user_id: number;
  email: string;
  name: string;
  dob: string | null;
  sex: string | null;
  height_cm: number | null;
  timezone: string;
  locale: Locale;
  theme: Theme;
  units: Units;
  role: string;
  ai_access_tier: string;
  main_integration_id: number | null;
}

export type Discipline =
  | "cycling"
  | "running"
  | "swimming"
  | "strength"
  | "sailing"
  | "boating"
  | "hiking"
  | "walking";

export interface ActivityCard {
  id: number;
  start_time: string;
  local_date: string;
  discipline: Discipline;
  title: string;
  duration_s: number;
  distance_m: number | null;
  elevation_gain_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power: number | null;
  np_power: number | null;
  avg_speed_mps: number | null;
  calories: number | null;
  training_load: number | null;
  data_completeness: "complete" | "partial" | "missing";
  sources: string[];
}

export interface ActivityLap {
  lap_index: number;
  start_time: string | null;
  duration_s: number | null;
  distance_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power: number | null;
  calories: number | null;
}

export interface ActivityStream {
  activity_id: number;
  t: number[];
  columns: Record<string, (number | null)[]>;
}

export interface ActivityDetail extends ActivityCard {
  has_streams: boolean;
  stream_types: string[];
  laps: ActivityLap[];
  route: { lat: number; lng: number; ele: number | null }[] | null;
  weather: { temp_c: number; wind_kph: number; humidity_pct: number; conditions: string } | null;
  gear: { id: number; name: string; type: string }[];
  source_metrics: Record<string, string>;
}

export interface Overview {
  date: string;
  anchor_is_today: boolean;
  readiness: ScoreBlock;
  recovery: ScoreBlock;
  strain: ScoreBlock;
  sleep_score: ScoreBlock;
  sleep_hours: number | null;
  hrv_ms: number | null;
  hrv_baseline_ms: number | null;
  hrv_norm_30d: number | null;
  resting_hr: number | null;
  resting_hr_delta_7d: number | null;
  spo2_avg: number | null;
  spo2_delta_7d: number | null;
  respiration_avg: number | null;
  steps: number | null;
  weight_kg: number | null;
  vo2max: number | null;
  acute_load: number | null;
  chronic_load: number | null;
  acwr: number | null;
  training_load_7d: number | null;
  activities: ActivityCard[];
  sleep: {
    start_time: string;
    end_time: string;
    total_sleep_s: number | null;
    sleep_score: number | null;
    stages: {
      deep_s: number | null;
      light_s: number | null;
      rem_s: number | null;
      awake_s: number | null;
    };
    respiration_avg: number | null;
    spo2_avg: number | null;
    restlessness: number | null;
  } | null;
  integration_status: { provider: string; status: string }[];
  alerts: { type: string; severity: "info" | "warning" | "alert"; message: string }[];
}

export interface SleepSession {
  local_date: string;
  start_time: string;
  end_time: string;
  total_sleep_s: number | null;
  deep_s: number | null;
  light_s: number | null;
  rem_s: number | null;
  awake_s: number | null;
  sleep_score: number | null;
  respiration_avg: number | null;
  spo2_avg: number | null;
  restlessness: number | null;
  sources: string[];
}

export interface SleepStages {
  date: string;
  segments: { t_start: string; t_end: string; stage: "deep" | "light" | "rem" | "awake" }[];
  source: string | null;
}

export interface SleepDay {
  date: string;
  session: SleepSession | null;
  biometrics: Record<string, number | null>;
  hrv_readings: { timestamp: string; hrv_ms: number; rolling_baseline_ms: number | null }[];
  stages: SleepStages | null;
}

export interface MetricCatalogItem {
  key: string;
  label: string;
  unit: string;
  group: "cardio" | "recovery" | "sleep" | "body" | "performance" | "lab";
  source: string;
  description: string;
}

export interface MetricTrend {
  metric: string;
  label: string;
  unit: string;
  group: string;
  start_date: string;
  end_date: string;
  points: { date: string; value: number | null }[];
  stats: { mean: number | null; min: number | null; max: number | null; last: number | null; baseline: number | null; delta_7d: number | null; delta_28d: number | null };
}

export interface ChatSession {
  id: number;
  title: string | null;
  started_at: string;
  last_activity_at: string;
  message_count: number;
  preview: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  referenced_data: Record<string, unknown> | null;
  created_at: string;
  kind: "data" | "recommendation" | "disclaimer";
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface DeviceOut {
  integration_id: number;
  provider: string;
  status: "active" | "paused" | "error";
  last_synced_at: string | null;
  is_main: boolean;
  connected_at: string;
}

export interface TrainingPlanItem {
  id: number;
  date: string;
  type: "session" | "rest" | "race";
  title: string;
  discipline: Discipline | "rest";
  duration_min: number | null;
  intensity: "easy" | "moderate" | "hard" | "threshold" | "recovery" | null;
  status: "planned" | "confirmed" | "done" | "skipped";
  note: string | null;
}

export interface GymExercise {
  id: number;
  name: string;
  muscle_group: string;
  sets: number;
  reps: string;
  weight_kg: number | null;
  rest_s: number;
  notes: string | null;
}

export interface GymSession {
  id: number;
  date: string;
  title: string;
  status: "planned" | "active" | "done";
  exercises: GymExercise[];
}

export interface Challenge {
  id: number;
  title: string;
  metric: string;
  unit: string;
  my_value: number;
  leader_value: number;
  my_rank: number;
  total_participants: number;
  ends_at: string;
}

export interface LabMarker {
  key: string;
  label: string;
  unit: string;
  value: number | null;
  ref_low: number | null;
  ref_high: number | null;
  status: "normal" | "low" | "high" | "borderline" | "unknown";
  date: string;
}

export type ViewKey =
  | "welcome"
  | "login"
  | "join"
  | "overview"
  | "activities"
  | "activity-detail"
  | "sleep"
  | "sleep-night"
  | "biometrics"
  | "metric"
  | "training"
  | "coach"
  | "social"
  | "settings";
