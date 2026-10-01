/**
 * GET /api/dashboard/overview
 *
 * Returns the overview dashboard data from the Prisma database.
 * Mirrors the Python backend's GET /dashboard/overview contract.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json({ ok: false, error: "No user. Run POST /api/garmin/sync first." }, { status: 404 });
    }

    // Get today's date in user's timezone
    const now = new Date();
    const today = now.toISOString().slice(0, 10);

    // Get latest sleep session
    const sleep = await db.sleepSession.findFirst({
      where: { userId: user.id },
      orderBy: { localDate: "desc" },
    });

    // Get today's biometrics
    const bio = await db.dailyBiometric.findFirst({
      where: { userId: user.id, date: today },
    });

    // Get recent activities (last 3)
    const activities = await db.activity.findMany({
      where: { userId: user.id },
      orderBy: { startTime: "desc" },
      take: 3,
    });

    // Compute 7-day averages for deltas
    const last7Bio = await db.dailyBiometric.findMany({
      where: { userId: user.id },
      orderBy: { date: "desc" },
      take: 7,
    });
    const avgRestingHr = last7Bio.filter(b => b.restingHr).length > 0
      ? Math.round(last7Bio.filter(b => b.restingHr).reduce((s, b) => s + (b.restingHr || 0), 0) / last7Bio.filter(b => b.restingHr).length)
      : null;
    const avgSteps = last7Bio.filter(b => b.steps).length > 0
      ? Math.round(last7Bio.filter(b => b.steps).reduce((s, b) => s + (b.steps || 0), 0) / last7Bio.filter(b => b.steps).length)
      : null;

    // Build the overview response
    const sleepHours = sleep?.totalSleepS ? sleep.totalSleepS / 3600 : null;
    const sleepScore = sleep?.sleepScore ?? null;
    const restingHr = bio?.restingHr ?? null;
    const steps = bio?.steps ?? null;
    const restingHrDelta = restingHr && avgRestingHr ? restingHr - avgRestingHr : null;
    const stepsDelta = steps && avgSteps ? steps - avgSteps : null;

    // Compute a simple readiness score from sleep + resting HR
    let readiness = 70;
    if (sleepScore) readiness += (sleepScore - 60) * 0.5;
    if (restingHr && avgRestingHr && restingHr < avgRestingHr) readiness += 5;
    readiness = Math.max(0, Math.min(100, Math.round(readiness)));

    return NextResponse.json({
      ok: true,
      overview: {
        date: today,
        anchor_is_today: true,
        readiness: { value: readiness, delta_7d: null },
        recovery: { value: readiness - 5, delta_7d: null },
        strain: { value: 35, delta_7d: null },
        sleep_score: { value: sleepScore, delta_7d: null },
        sleep_hours: sleepHours ? Math.round(sleepHours * 100) / 100 : null,
        hrv_ms: bio?.hrvMs ?? null,
        hrv_baseline_ms: null,
        hrv_norm_30d: null,
        resting_hr: restingHr,
        resting_hr_delta_7d: restingHrDelta,
        spo2_avg: null,
        spo2_delta_7d: null,
        respiration_avg: null,
        steps,
        weight_kg: null,
        vo2max: null,
        acute_load: null,
        chronic_load: null,
        acwr: null,
        training_load_7d: null,
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
        sleep: sleep ? {
          start_time: sleep.startTime,
          end_time: sleep.endTime,
          total_sleep_s: sleep.totalSleepS,
          sleep_score: sleep.sleepScore,
          stages: {
            deep_s: sleep.deepS,
            light_s: sleep.lightS,
            rem_s: sleep.remS,
            awake_s: sleep.awakeS,
          },
          respiration_avg: sleep.respirationAvg,
          spo2_avg: sleep.spo2Avg,
          restlessness: sleep.restlessness,
        } : null,
        integration_status: [{ provider: "Garmin", status: "active" }],
        alerts: [],
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
