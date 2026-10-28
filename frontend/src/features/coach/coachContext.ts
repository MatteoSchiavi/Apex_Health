/** Only record identifiers cross the daily workflow boundary. */
export type CoachContext = {
  userId: number;
  date: string;
  plannedSessionId?: number;
};

function positiveId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function validatedCoachContext(state: unknown, userId: number): CoachContext | null {
  if (!state || typeof state !== "object") return null;
  const value = (state as { coachContext?: unknown }).coachContext;
  if (!value || typeof value !== "object") return null;
  const context = value as Record<string, unknown>;
  if (!positiveId(context.userId) || context.userId !== userId ||
    typeof context.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(context.date) || context.date.startsWith("0000")) return null;
  const date = new Date(context.date + "T12:00:00Z");
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== context.date) return null;
  if (context.plannedSessionId !== undefined && !positiveId(context.plannedSessionId)) return null;
  return {
    userId: context.userId,
    date: context.date,
    ...(context.plannedSessionId !== undefined ? { plannedSessionId: context.plannedSessionId } : {}),
  };
}
