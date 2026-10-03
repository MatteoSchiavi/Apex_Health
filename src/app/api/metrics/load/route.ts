import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { trainingLoadSummary } from "@/lib/apex/healthMath";

/**
 * Training Load / ACWR API (plan §2 Load card)
 *
 * GET /api/metrics/load?days=56
 *
 * Returns, for the last `days` calendar days:
 *   - daily load (sum of activity trainingLoad per localDate; activities
 *     without trainingLoad contribute a duration-derived estimate so the
 *     chart doesn't have zero gaps for disciplines like hiking/sailing)
 *   - rolling 7-day acute load (sum of last 7 days, ending on that day)
 *   - rolling chronic load (28-day total / 4, in weekly units)
 *   - ACWR = acute / chronic
 *   - events on each day (so the UI can draw vertical lines + taper windows)
 */

async function getUser() {
  const email = process.env.GARMIN_EMAIL || "";
  let user = await db.user.findFirst({ where: { email } });
  if (!user) {
    user = await db.user.create({
      data: {
        email,
        name: "Apex Athlete",
        password: process.env.GARMIN_PASSWORD || "",
        timezone: "Europe/Rome",
        locale: "en",
        theme: "dark",
        units: "metric",
        role: "owner",
        aiTier: "pro",
      },
    });
  }
  return user;
}

/** local YYYY-MM-DD using en-CA (ISO-style) so the chart anchors to user's day. */
function localToday(timezone: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  } catch {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString().slice(0, 10);
  }
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export async function GET(req: NextRequest) {
  try {
    const user = await getUser();
    const { searchParams } = new URL(req.url);
    const days = Math.max(7, Math.min(120, parseInt(searchParams.get("days") || "56")));

    const today = localToday(user.timezone);
    const startDate = addDays(today, -(days - 1));
    // also fetch ~28 extra days back so the chronic rolling window is full from day 1
    const fetchStart = addDays(startDate, -28);

    const [activities, events] = await Promise.all([
      db.activity.findMany({
        where: { userId: user.id, localDate: { gte: fetchStart } },
        select: { localDate: true, trainingLoad: true, durationS: true, discipline: true },
      }),
      db.calendarEvent.findMany({
        where: { userId: user.id },
        select: { id: true, title: true, kind: true, date: true, priority: true, taperDays: true },
      }),
    ]);

    // Build a date → load map. Activities without a recorded trainingLoad get a
    // duration-based estimate: 1 TSS per 6 minutes (~10 TSS/hr). This matches
    // the "10 TSS per hour for steady endurance" rule of thumb.
    const loadByDate = new Map<string, number>();
    for (const a of activities) {
      if (!a.localDate) continue;
      const tl =
        a.trainingLoad != null
          ? a.trainingLoad
          : a.durationS
          ? Math.round((a.durationS / 3600) * 10 * 10) / 10
          : 0;
      loadByDate.set(a.localDate, (loadByDate.get(a.localDate) ?? 0) + tl);
    }

    // Build a daily load array covering [fetchStart, today]. Index 0 is the
    // oldest day (28 days before the chart start); index N-1 is today.
    const allDates: string[] = [];
    const allLoads: number[] = [];
    for (let i = 0; ; i++) {
      const d = addDays(fetchStart, i);
      allDates.push(d);
      allLoads.push(loadByDate.get(d) ?? 0);
      if (d === today) break;
    }

    // chart start index inside the all* arrays
    const startIdx = allDates.length - days;

    const series: {
      date: string;
      load: number;
      acute: number | null;
      chronic: number | null;
      acwr: number | null;
      events: { id: number; title: string; kind: string; priority: string; taperDays: number | null }[];
    }[] = [];

    for (let i = 0; i < days; i++) {
      const idx = startIdx + i;
      const d = allDates[idx];
      const todayLoad = allLoads[idx];

      // acute = sum of last 7 days ending today (including today)
      const acuteRaw = allLoads
        .slice(Math.max(0, idx - 6), idx + 1)
        .reduce((s, v) => s + v, 0);
      // chronic = 28-day total / 4, matching the 7-day numerator's units.
      const chronicSlice = allLoads.slice(Math.max(0, idx - 27), idx + 1);
      const chronicTotal = chronicSlice.reduce((s, v) => s + v, 0);
      const { acute, chronic, acwr } = trainingLoadSummary(acuteRaw, chronicTotal);

      const dayEvents = events
        .filter((e) => e.date === d)
        .map((e) => ({
          id: e.id,
          title: e.title,
          kind: e.kind,
          priority: e.priority,
          taperDays: e.taperDays,
        }));

      series.push({
        date: d,
        load: Math.round(todayLoad * 10) / 10,
        acute,
        chronic,
        acwr,
        events: dayEvents,
      });
    }

    // Taper windows: for each priority-1 event, mark the `taperDays` days
    // leading up to (and excluding) the event date. UI shades them.
    const taperWindows: { eventId: number; start: string; end: string }[] = [];
    for (const e of events) {
      if (e.priority !== "priority_1" && e.priority !== "high") continue;
      const t = e.taperDays ?? 5;
      const end = e.date;
      const start = addDays(end, -t);
      taperWindows.push({ eventId: e.id, start, end });
    }

    // Latest aggregates
    const last = series[series.length - 1];
    const summary = {
      acute_load: last?.acute ?? null,
      chronic_load: last?.chronic ?? null,
      acwr: last?.acwr ?? null,
      training_load_7d: last?.acute ?? null,
    };

    return NextResponse.json({
      ok: true,
      days,
      series,
      taperWindows,
      summary,
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
