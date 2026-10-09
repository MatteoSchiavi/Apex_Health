export type Focus = "gym" | "running" | "cycling";
export interface SportContext {
  level?: string; weekly_frequency?: number; weekly_distance_km?: number; weekly_duration_min?: number;
  longest_distance_km?: number; preferred_days?: number[]; long_session_day?: number;
  goal?: string; event?: { title: string; date?: string; distance_km?: number; priority: number };
  equipment?: string[]; constraints?: string; power_available?: boolean;
}
export interface ZoneConfiguration { effective_from: string; bands: { name: string; lower: number; upper: number }[] }
export interface AthleteContext {
  hr_zones?: ZoneConfiguration; power_zones?: ZoneConfiguration;
  focuses?: Partial<Record<Focus, SportContext>>; main_goal?: string; weekly_time_budget_min?: number;
  preferred_rest_day?: number; availability?: { day: number; start: string; end: string }[];
  sleep_work_schedule?: string; schedule_constraints?: string; gym_experience_years?: number; gym_split?: string;
  preferred_exercises?: string; rpe_preference?: boolean; self_declared_restrictions?: string; athlete_notes?: string;
  existing_plan?: string; recent_consistency?: string; event_history?: string; devices?: string; coaching_style?: string;
  ftp?: { watts: number; measured_on: string; confirmed: true }; onboarding_step?: number;
}
export interface AthleteProfile { training_focus: Focus[]; context: AthleteContext; revision: number }
export interface AiState {
  effective_access: "disabled" | "basic" | "full"; policy_version: string; provider_identity: string;
  consent: { active: boolean; accepted_at: string | null; withdrawn_at: string | null } | null;
  budget: { used_tokens: number; limit_tokens: number; exhausted: boolean; categories: Record<string, { used_tokens: number; limit_tokens: number }> };
}
export interface Checkin {
  id: number; activity_id: number | null; planned_session_id: number | null; status: string;
  rpe: number | null; pain: boolean | null; felt_unwell: boolean | null; note: string; revision: number;
}
export interface DaySession {
  id: number; plan_id: number; plan_revision: number; plan_title: string | null; discipline: string | null;
  start_time: string | null; session_type: string | null; duration_min: number | null; distance_m: number | null;
  description: string | null; protected: boolean; plan_protected: boolean; workout_protected: boolean; status: string; activity_id: number | null; checkin: Checkin | null;
}
export interface DayActivity {
  id: number; discipline: string | null; start_time: string; duration_s: number; distance_m: number | null;
  planned_session_id: number | null; association: string; candidate_session_ids: number[]; checkin: Checkin | null;
  comparison: { target_duration_min: number | null; recorded_duration_min: number; duration_delta_min: number | null } | null;
}
export interface AthleteDay {
  date: string; timezone: string; training_focus: Focus[]; sessions: DaySession[]; activities: DayActivity[];
  legacy_gym_sessions: { gym_day_plan_id: number; title: string; status: string }[]; state: string;
  totals: Record<string, { value: number | null; unit: string; available_sessions: number; total_sessions: number }>;
}
