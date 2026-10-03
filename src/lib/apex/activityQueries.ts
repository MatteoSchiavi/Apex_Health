import { z } from "zod";
import type { Prisma } from "@prisma/client";

const integer = (fallback: number, min: number, max: number) =>
  z.string().regex(/^\d+$/).transform(Number).pipe(z.number().int().min(min).max(max)).prefault(String(fallback));
const filters = z.array(z.string().trim().min(1).max(64).refine((s) => !s.includes(","))).max(20);
const base = { disciplines: filters, sources: filters };
export const activityQuery = z.object({
  ...base, week: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((s) => {
    const d = new Date(`${s}T12:00:00Z`);
    return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === s && d.getUTCDay() === 1;
  }).optional(), days: integer(90, 1, 3660), offset: integer(0, 0, 1_000_000), limit: integer(60, 1, 100),
});
export const weeklyQuery = z.object({ ...base, weeks: integer(12, 2, 52), days: integer(90, 1, 366).optional() });

export function queryValues(params: URLSearchParams) {
  return {
    days: params.get("days") ?? undefined, offset: params.get("offset") ?? undefined,
    limit: params.get("limit") ?? undefined, weeks: params.get("weeks") ?? undefined,
    week: params.get("week") ?? undefined,
    disciplines: params.getAll("discipline"), sources: params.getAll("source"),
  };
}

/** Arithmetic on date labels keeps DST and the server timezone from shifting a day. */
export function calendarDate(now: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (key: string) => parts.find((p) => p.type === key)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
export function addCalendarDays(date: string, days: number) {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
export function mondayForDate(date: string) {
  const day = new Date(`${date}T12:00:00Z`).getUTCDay();
  return addCalendarDays(date, day === 0 ? -6 : 1 - day);
}
export function activityWhere(userId: number, from: string, until: string, disciplines: string[], sources: string[]): Prisma.ActivityWhereInput {
  return {
    userId, localDate: { gte: from, lt: until },
    ...(disciplines.length ? { discipline: { in: disciplines } } : {}),
    // Providers are whole comma-delimited tokens, never substrings of another provider.
    ...(sources.length ? { OR: sources.flatMap((s) => [
      { sources: s }, { sources: { startsWith: `${s},` } },
      { sources: { endsWith: `,${s}` } }, { sources: { contains: `,${s},` } },
    ]) } : {}),
  };
}
