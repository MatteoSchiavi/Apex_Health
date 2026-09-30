/**
 * GET /api/sleep
 *
 * Returns sleep sessions from the Prisma database.
 * Query params: ?days=14 (default)
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json({ ok: false, error: "No user. Run POST /api/garmin/sync first." }, { status: 404 });
    }

    const { searchParams } = new URL(req.url);
    const days = parseInt(searchParams.get("days") || "14");

    const sleepSessions = await db.sleepSession.findMany({
      where: { userId: user.id },
      orderBy: { localDate: "desc" },
      take: days,
    });

    return NextResponse.json({
      ok: true,
      items: sleepSessions.map(s => ({
        local_date: s.localDate,
        start_time: s.startTime,
        end_time: s.endTime,
        total_sleep_s: s.totalSleepS,
        deep_s: s.deepS,
        light_s: s.lightS,
        rem_s: s.remS,
        awake_s: s.awakeS,
        sleep_score: s.sleepScore,
        respiration_avg: s.respirationAvg,
        spo2_avg: s.spo2Avg,
        restlessness: s.restlessness,
        sources: s.sources.split(","),
      })),
      count: sleepSessions.length,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
