/**
 * Frontend types for the Coach chat API (plan §1).
 *
 * These match the JSON shape returned by /api/coach/chats* and are intentionally
 * close to the existing mock `ChatMessage`/`ChatSession` types so the store stays
 * compatible. The backend's slim `referenced_data` (tool_calls + context_keys)
 * and the new `drafts` array live here too.
 */

import type { CoachDraft, CoachEvidence } from "./types";

export interface ChatSessionRow {
  id: number;
  title: string | null;
  started_at: string;
  last_activity_at: string;
  message_count: number;
  preview: string;
}

export interface ChatMessageRow {
  id: number;
  role: "user" | "assistant";
  content: string;
  referenced_data: CoachEvidence | Record<string, unknown> | null;
  drafts: CoachDraft[] | null;
  model_tier?: string | null;
  kind: "data" | "recommendation" | "disclaimer";
  created_at: string;
  /** Client-only status flag for optimistic user messages. */
  status?: "sending" | "sent" | "error";
}

export interface ChatSessionDetail extends ChatSessionRow {
  messages: ChatMessageRow[];
}

export interface ContextDocRow {
  kind: "profile" | "goals" | "injuries" | "equipment" | "preferences" | "season_plan";
  content: string;
  updated_at: string;
  char_count: number;
  char_cap: number;
}
