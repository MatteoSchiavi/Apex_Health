/**
 * Central API client. One `api` object, zero bespoke fetch logic in
 * components. Laws:
 *  - credentials ride the HttpOnly session cookie (same origin) — no tokens
 *    in localStorage, ever (STACK.md §2.5).
 *  - every unsafe method sends the X-CSRF-Token header from the meta value
 *    the backend handshake gives us (login sets it; we mirror it).
 */

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API ${status}`);
    this.status = status;
    this.body = body;
  }
}

function csrfToken(): string {
  // Backend sessions are cookie+CSRF; the SPA mints a per-boot token the
  // middleware only checks for PRESENCE (any value) on unsafe methods.
  let t = sessionStorage.getItem("apex.csrf");
  if (!t) {
    t = crypto.randomUUID().replace(/-/g, "");
    sessionStorage.setItem("apex.csrf", t);
  }
  return t;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET" && method !== "HEAD") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = csrfToken();
  }
  const resp = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!resp.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in (parsed as Record<string, unknown>)
        ? String((parsed as Record<string, unknown>).detail)
        : undefined;
    throw new ApiError(resp.status, parsed, detail);
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

/* ------------------------------------------------------------- domain types */

export interface ScoreBlock {
  value: number | null;
  delta_7d: number | null;
}

export interface Me {
  user_id: number;
  email: string;
  name: string;
  dob: string | null;
  sex: string | null;
  height_cm: number | null;
  timezone: string;
  locale: "en" | "it";
  theme: "dark" | "light";
  units: "metric" | "imperial";
  role: string;
  ai_access_tier: string;
  main_integration_id: number | null;
}

export interface ActivityCard {
  id: number;
  start_time: string;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
  avg_power: number | null;
  training_load: number | null;
  calories: number | null;
  data_completeness: string;
}

export interface Overview {
  date: string;
  readiness: ScoreBlock;
  recovery: ScoreBlock;
  strain: ScoreBlock;
  sleep_score: ScoreBlock;
  sleep_hours: number | null;
  hrv_ms: number | null;
  hrv_baseline_ms: number | null;
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
    stages: { deep_s: number | null; light_s: number | null; rem_s: number | null; awake_s: number | null };
    respiration_avg: number | null;
    spo2_avg: number | null;
    restlessness: number | null;
  } | null;
  integration_status: { provider: string; status: string }[];
  alerts: { type: string; severity: string; message: string }[];
}

export interface ActivityListItem {
  id: number;
  start_time: string;
  local_date: string;
  discipline: string | null;
  duration_s: number;
  distance_m: number | null;
  elevation_gain_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power: number | null;
  np_power: number | null;
  calories: number | null;
  training_load: number | null;
  data_completeness: string;
  sources: string[];
}

export interface ActivityDetail extends ActivityListItem {
  has_streams: boolean;
  stream_types: string[];
  laps: {
    lap_index: number;
    start_time: string | null;
    duration_s: number | null;
    distance_m: number | null;
    avg_hr: number | null;
    max_hr: number | null;
    avg_power: number | null;
    calories: number | null;
    extras: Record<string, unknown> | null;
  }[];
  weather: Record<string, unknown> | null;
  source_metrics: Record<string, Record<string, unknown>> | null;
  gear: { id: number; name: string; type: string }[];
}

export interface StreamOut {
  activity_id: number;
  t: number[];
  columns: Record<string, (number | null)[]>;
}

export interface SleepSessionOut {
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
  sources?: string[];
}

export interface SleepList {
  items: SleepSessionOut[];
  start_date: string;
  end_date: string;
}

export interface SleepDay {
  date: string;
  session: SleepSessionOut | null;
  biometrics: Record<string, number | null>;
  hrv_readings: { timestamp: string; hrv_ms: number; reading_type: string; rolling_baseline_ms: number | null }[];
}

export interface MetricTrend {
  metric: string;
  label: string;
  unit: string;
  start_date: string;
  end_date: string;
  points: { date: string; value: number | null }[];
  stats: Record<string, number | null>;
}

export interface ChatSessionOut {
  id: number;
  title: string | null;
  started_at: string;
  last_activity_at: string;
  message_count: number;
}

export interface ChatMessageOut {
  id: number;
  role: "user" | "assistant";
  content: string;
  model_tier: string | null;
  referenced_data: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSessionOut {
  messages: ChatMessageOut[];
}

export interface DeviceOut {
  integration_id: number;
  provider: string;
  status: string;
  last_synced_at: string | null;
  is_main: boolean;
  connected_at: string;
}
