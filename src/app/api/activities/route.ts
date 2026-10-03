import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { activityCard } from "@/lib/apex/activityRecord";
import { activityQuery, queryValues, calendarDate, addCalendarDays, activityWhere } from "@/lib/apex/activityQueries";

/** Bounded pagination; totals compare two equal local-calendar windows. */
export async function GET(req: NextRequest) {
  const parsed = activityQuery.safeParse(queryValues(new URL(req.url).searchParams));
  if (!parsed.success) return NextResponse.json({ ok: false, error: "Invalid activity filters", issues: parsed.error.flatten() }, { status: 400 });
  try {
    const user = await db.user.findFirst({ where: { email: process.env.GARMIN_EMAIL || "" } });
    if (!user) return NextResponse.json({ ok: false, error: "Account not found" }, { status: 404 });
    const { days, offset, limit, disciplines, sources, week } = parsed.data;
    const until = addCalendarDays(calendarDate(new Date(), user.timezone), 1);
    const from = addCalendarDays(until, -days);
    const previous = addCalendarDays(from, -days);
    const currentWhere = activityWhere(user.id, from, until, disciplines, sources);
    const pageFrom = week && week > from ? week : from;
    const weekUntil = week ? addCalendarDays(week, 7) : until;
    const pageUntil = weekUntil < until ? weekUntil : until;
    const pageWhere = activityWhere(user.id, pageFrom, pageUntil, disciplines, sources);
    const previousWhere = activityWhere(user.id, previous, from, disciplines, sources);
    const aggregate = { _count: { _all: true }, _sum: { durationS: true, distanceM: true, trainingLoad: true } } as const;
    // A single read transaction keeps page and totals consistent during sync writes.
    const [page, current, prev, total] = await db.$transaction([
      db.activity.findMany({ where: pageWhere, orderBy: [{ startTime: "desc" }, { id: "desc" }], skip: offset, take: limit }),
      db.activity.aggregate({ where: currentWhere, ...aggregate }),
      db.activity.aggregate({ where: previousWhere, ...aggregate }),
      db.activity.count({ where: pageWhere }),
    ]);
    return NextResponse.json({ ok: true, activities: page.map(activityCard), count: page.length,
      total, offset, limit, summary: {
        sessions: current._count._all, total_time_s: current._sum.durationS ?? 0,
        total_distance_m: current._sum.distanceM ?? 0, total_load: current._sum.trainingLoad ?? 0,
        prev_sessions: prev._count._all, prev_total_time_s: prev._sum.durationS ?? 0,
        prev_total_distance_m: prev._sum.distanceM ?? 0, prev_total_load: prev._sum.trainingLoad ?? 0,
      } });
  } catch {
    return NextResponse.json({ ok: false, error: "Could not load activities" }, { status: 500 });
  }
}
