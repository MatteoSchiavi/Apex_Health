export interface Observation {
  id: string;
  metric: string;
  value: number | null;
  unit: string | null;
  origin: string;
  measured_at: string;
  local_date: string;
  fetched_at: string;
  revision: number;
  availability: string;
  acquisition: string;
  timezone: string;
  quality_flags: string[];
}
export interface Coverage {
  timezone: string;
  local_date: string;
  metrics: {
    metric: string;
    unit: string | null;
    availability: string;
    sample_days_7d: number;
    coverage_pct: number;
    latest: Observation | null;
  }[];
  integrations: {
    provider: string;
    status: string;
    last_successful_fetch: string | null;
    consecutive_failures: number;
  }[];
}
export interface Decision {
  id: number;
  date: string;
  action: string;
  reasons: string[];
  evidence: Observation[];
  data_completeness: { coverage_pct: number; missing: string[] };
  confidence: string;
  alternatives: { action: string; reason: string; duration_factor?: number }[];
  counterfactual: string;
  next_step: string;
  formula_version: string;
  limitations: string[];
  state?: string;
  headline?: string;
  key_changes?: { metric: string; current: number | null; baseline: number | null; delta: number | null; origin: string | null }[];
  contributors?: string[];
  data_coverage?: { coverage_pct: number; missing: string[] };
  recommended_action?: { action: string; reason: string; duration_factor?: number; planned_session_id?: number };
  outcome: { state: string; notes?: string; influenced_plan?: "yes" | "partly" | "no"; useful?: boolean; completion?: "completed" | "partial" | "skipped"; rpe?: number; soreness?: number; pain?: boolean; felt_unwell?: boolean; activity_id?: number; draft_id?: number; planned_session_id?: number; recorded_at?: string } | null;
}
export interface Draft {
  adaptation?: { objective_status: string; data_gaps: string[]; evidence_ids: string[] } | null;
  id: number;
  kind: string;
  status: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  payload_hash: string;
  snapshot_revision: string;
  evidence_ids: string[];
  reason: string;
  expires_at: string;
  receipt: {
    state: string;
    external_delivery: string;
    undo_available: boolean;
  } | null;
}
export interface Entry {
  id: number;
  kind: string;
  date: string;
  payload: Record<string, unknown>;
  revision: number;
}
export interface Analysis {
  handle: string;
  recipe: string;
  formula_version: string;
  data: Record<string, unknown>;
}
export interface Job {
  id: number;
  kind: string;
  state: string;
  parameters: Record<string, string>;
  progress: Record<string, unknown>;
  cancel_requested: boolean;
}
export interface Doc {
  id: number;
  filename: string;
  content_hash: string;
  status: string;
  revision: number;
  excerpt: string | null;
}
export interface Event {
  profile_focus?: string | null; date_only?: boolean;
  id: number;
  title: string;
  kind: string;
  starts_at: string;
  ends_at: string | null;
  priority: number;
  taper_days: number;
  notes: string | null;
}
export interface Constraints {
  date: string;
  events: {
    id: number;
    title: string;
    date: string;
    days_away: number;
    priority: number;
    taper_days: number;
  }[];
  sessions: {
    id: number;
    date: string;
    session_type: string;
    description: string | null;
    duration_min: number | null;
  }[];
}
export const coreMetrics = [
  "hrv_overnight_rmssd",
  "resting_hr",
  "sleep_duration",
  "sleep_score",
];
