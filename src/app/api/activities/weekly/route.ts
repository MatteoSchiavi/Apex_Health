/**
 * GET /api/activities/weekly
 *
 * Per-week aggregate volume for the weekly-volume chart on the Activities list
 * (plan §3 Row 2). One `WeeklyVolume` object per ISO week (Monday-starting),
 * bucketed by `localDate`, with per-discipline breakdown so the chart can stack.
 *
 * Query params:
 *   weeks=12            default 12, validated 2..52
 *   days=30             optional exact calendar range, overrides week count
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
import { weeklyQuery, queryValues, calendarDate, addCalendarDays, mondayForDate, activityWhere } from "@/lib/apex/activityQueries";
import type { WeeklyVolume } from "@/lib/apex/types";

export async function GET(req: NextRequest) {
  const parsed = weeklyQuery.safeParse(queryValues(new URL(req.url).searchParams));
  if (!parsed.success) return NextResponse.json({ ok: false, error: "Invalid weekly filters" }, { status: 400 });
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json(
        { ok: false, error: "No user. Run POST /api/garmin/sync first." },
        { status: 404 }
      );
    }

    const { weeks, days, disciplines, sources } = parsed.data;
    const today = calendarDate(new Date(), user.timezone);
    const until = addCalendarDays(today, 1);
    const from = days === undefined ? addCalendarDays(mondayForDate(today), -(weeks - 1) * 7) : addCalendarDays(until, -days);
    const firstWeekStr = mondayForDate(from);
    const bucketCount = Math.round((Date.parse(mondayForDate(today)) - Date.parse(firstWeekStr)) / 604800000) + 1;
    const where = activityWhere(user.id, from, until, disciplines, sources);
    const activities = await db.activity.groupBy({
      by: ["localDate", "discipline"], where,
      _count: { _all: true }, _sum: { durationS: true, trainingLoad: true, distanceM: true },
    });

    // Initialize all weeks (zero-filled).
    const buckets: WeeklyVolume[] = [];
    const index = new Map<string, number>();
    for (let i = 0; i < bucketCount; i++) {
      const key = addCalendarDays(firstWeekStr, i * 7);
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
      const key = mondayForDate(a.localDate);
      const i = index.get(key);
      if (i === undefined) continue; // outside window
      const b = buckets[i];
      b.sessions += a._count._all;
      b.total_hours += (a._sum.durationS || 0) / 3600;
      b.total_load += a._sum.trainingLoad ?? 0;
      b.total_distance_m += a._sum.distanceM ?? 0;
      if (!b.by_discipline[a.discipline]) {
        b.by_discipline[a.discipline] = { hours: 0, load: 0, distance_m: 0, sessions: 0 };
      }
      const d2 = b.by_discipline[a.discipline];
      d2.hours += (a._sum.durationS || 0) / 3600;
      d2.load += a._sum.trainingLoad ?? 0;
      d2.distance_m += a._sum.distanceM ?? 0;
      d2.sessions += a._count._all;
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
  } catch {
    return NextResponse.json({ ok: false, error: "Could not load weekly volume" }, { status: 500 });
  }
}
