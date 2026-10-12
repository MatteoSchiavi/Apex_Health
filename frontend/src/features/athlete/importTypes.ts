import type {WorkoutStep} from "./StructuredWorkoutSteps";
import type { AthleteContext, Focus } from "./types";
export interface WorkoutFieldsValue {
  steps?: WorkoutStep[];
  discipline: string; session_type: string | null; duration_min: number | null; distance_m: number | null;
  start_time: string | null; description: string; intensity_targets: Record<string, string>; protected: boolean;
}
export interface WeeklyWorkout extends WorkoutFieldsValue { id: string; day: number }
export interface DatedWorkout extends WorkoutFieldsValue { date: string | null }
export interface WeeklyStructure { title: string; rows: WeeklyWorkout[]; notes: string }
export interface PlanStructure { title: string; starts_on: string | null; ends_on: string | null; weekly_structure: string; sessions: DatedWorkout[]; ambiguities: string[]; protected: boolean }
export interface PlanDraft { id: number; document_id: number | null; document_revision: number | null; template_id?: number | null; template_revision?: number | null; version: number; structure: PlanStructure; payload_hash: string; status: string; confirmed_at: string | null }
export interface ImportProposal {
  profile: { training_focus: Focus[] | null; context: AthleteContext };
  weekly: WeeklyStructure | null; dated: PlanStructure | null;
  sources: { field: string; quote: string; certainty: "explicit" | "uncertain" | "contradictory" }[];
  issues: { field: string; question: string; required: boolean }[];
}
export interface AthleteImport {
  id: number; document_id: number; document_revision: number; version: number; proposal: ImportProposal;
  payload_hash: string; extraction_method: string; source_text: string; category_hints: string[];
  receipts: { profile?: { fields: string[]; profile_revision: number }; template?: { template_id: number; revision: number }; dated_plan?: { draft_id: number } };
}
export interface AthleteTemplate { id: number; revision: number; source_document_id: number; source_document_revision: number; import_draft_id: number; structure: WeeklyStructure }
export const emptyWorkout = (): WorkoutFieldsValue => ({ discipline: "", session_type: null, duration_min: null, distance_m: null, start_time: null, description: "", intensity_targets: {}, protected: false });
