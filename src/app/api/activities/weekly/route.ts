/**
 * GET /api/activities/weekly
 *
 * Per-week aggregate volume for the weekly-volume chart on the Activities list
 * (plan §3 Row 2). One `WeeklyVolume` object per ISO week (Monday-starting),
 * bucketed by `localDate`, with per-discipline breakdown so the chart can stack.
 *
 * Query params:
 *   weeks=12            default 12, clamped 2..52
 *   discipline=cycling   repeatable, mirrors /api/activities
 *   source=Garmin        repeatable, mirrors /api/activities
 *
 * Response:
 *   { ok, weekly: WeeklyVolume[] }
 *
 * Empty weeks (no sessions) are still returned, with zero totals and an empty
 * `by_discipline` map — the chart needs them to show consistency gaps.
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { WeeklyVolume } from "@/lib/apex/types";

/** ISO week starts Monday. Returns local-time Date for the Monday of that week. */
function isoWeekStart(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dow = d.getDay(); // 0 = Sun .. 6 = Sat
  const delta = dow === 0 ? -6 : 1 - dow;
  d.setDate(d.getDate() + delta);
  return d;
}

function toLocalDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function buildWhere(userId: number, dateGte: string, disciplines: string[], sources: string[]) {
  const where: any = { userId, localDate: { gte: dateGte } };
  if (disciplines.length) where.discipline = { in: disciplines };
  if (sources.length) where.OR = sources.map((s) => ({ sources: { contains: s } }));
  return where;
}

export async function GET(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json(
        { ok: false, error: "No user. Run POST /api/garmin/sync first." },
        { status: 404 }
      );
    }

    const { searchParams } = new URL(req.url);
    const weeks = Math.max(2, Math.min(52, parseInt(searchParams.get("weeks") || "12")));
    const disciplines = searchParams.getAll("discipline").filter(Boolean);
    const sources = searchParams.getAll("source").filter(Boolean);

    // Window: from the Monday `weeks-1` weeks before this week's Monday, through today.
    const thisWeekStart = isoWeekStart(new Date());
    const firstWeekStart = new Date(thisWeekStart);
    firstWeekStart.setDate(firstWeekStart.getDate() - (weeks - 1) * 7);
    const firstWeekStr = toLocalDateStr(firstWeekStart);

    // Pull everything in the window.
    const where = buildWhere(user.id, firstWeekStr, disciplines, sources);
    const activities = await db.activity.findMany({
      where,
      orderBy: { startTime: "asc" },
    });

    // Initialize all weeks (zero-filled).
    const buckets: WeeklyVolume[] = [];
    const index = new Map<string, number>();
    for (let i = 0; i < weeks; i++) {
      const ws = new Date(firstWeekStart);
      ws.setDate(ws.getDate() + i * 7);
      const key = toLocalDateStr(ws);
      index.set(key, i);
      buckets.push({
        week_start: key,
        total_hours: 0,
        total_load: 0,
        total_distance_m: 0,
        sessions: 0,
        by_discipline: {},
      });
    }

    // Bucket activities.
    for (const a of activities) {
      // localDate is YYYY-MM-DD.
      const [y, m, d] = a.localDate.split("-").map(Number);
      if (!y || !m || !d) continue;
      const date = new Date(y, m - 1, d);
      const ws = isoWeekStart(date);
      const key = toLocalDateStr(ws);
      const i = index.get(key);
      if (i === undefined) continue; // outside window
      const b = buckets[i];
      b.sessions += 1;
      b.total_hours += (a.durationS || 0) / 3600;
      b.total_load += a.trainingLoad ?? 0;
      b.total_distance_m += a.distanceM ?? 0;
      if (!b.by_discipline[a.discipline]) {
        b.by_discipline[a.discipline] = { hours: 0, load: 0, distance_m: 0, sessions: 0 };
      }
      const d2 = b.by_discipline[a.discipline];
      d2.hours += (a.durationS || 0) / 3600;
      d2.load += a.trainingLoad ?? 0;
      d2.distance_m += a.distanceM ?? 0;
      d2.sessions += 1;
    }

    // Round hours to 1 decimal for cleaner display.
    for (const b of buckets) {
      b.total_hours = Math.round(b.total_hours * 10) / 10;
      b.total_load = Math.round(b.total_load * 10) / 10;
      b.total_distance_m = Math.round(b.total_distance_m);
      for (const k of Object.keys(b.by_discipline)) {
        const dd = b.by_discipline[k];
        dd.hours = Math.round(dd.hours * 10) / 10;
        dd.load = Math.round(dd.load * 10) / 10;
        dd.distance_m = Math.round(dd.distance_m);
      }
    }

    return NextResponse.json({ ok: true, weekly: buckets });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
