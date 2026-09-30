/**
 * GET /api/activities
 *
 * Returns activities from the Prisma database.
 * Query params: ?days=30 (default), ?discipline=cycling
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
    const days = parseInt(searchParams.get("days") || "90");
    const discipline = searchParams.get("discipline");

    // Calculate cutoff date
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffStr = cutoff.toISOString().slice(0, 10);

    const where: any = { userId: user.id, localDate: { gte: cutoffStr } };
    if (discipline) where.discipline = discipline;

    const activities = await db.activity.findMany({
      where,
      orderBy: { startTime: "desc" },
    });

    return NextResponse.json({
      ok: true,
      activities: activities.map(a => ({
        id: a.id,
        start_time: a.startTime,
        local_date: a.localDate,
        discipline: a.discipline,
        title: a.title,
        duration_s: a.durationS,
        distance_m: a.distanceM,
        elevation_gain_m: a.elevationGainM,
        avg_hr: a.avgHr,
        max_hr: a.maxHr,
        avg_power: a.avgPower,
        np_power: a.npPower,
        avg_speed_mps: a.avgSpeedMps,
        calories: a.calories,
        training_load: a.trainingLoad,
        data_completeness: a.dataCompleteness,
        sources: a.sources.split(","),
      })),
      count: activities.length,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
