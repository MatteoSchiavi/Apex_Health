import { NextRequest, NextResponse } from "next/server";
import { syncGarminData } from "@/lib/garmin/sync";
import { db } from "@/lib/db";

/**
 * POST /api/garmin/sync
 *
 * Triggers a Garmin Connect data sync. Fetches activities, sleep, daily stats,
 * and HRV from Garmin Connect and stores them in the Prisma database.
 *
 * If no user exists in the DB, creates one from the GARMIN_EMAIL env var.
 */

export async function POST(req: NextRequest) {
  try {
    // Ensure a user exists
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    let user = await db.user.findFirst({ where: { email } });
    if (!user) {
      user = await db.user.create({
        data: {
          email,
          name: "Matteo Schiavi",
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

    // Run the sync
    const report = await syncGarminData(user.id);

    return NextResponse.json({ ok: true, userId: user.id, report });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/**
 * GET /api/garmin/sync — returns the sync status
 */
export async function GET() {
  try {
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json({ ok: false, error: "No user found. Run POST /api/garmin/sync first." });
    }

    const activityCount = await db.activity.count({ where: { userId: user.id } });
    const sleepCount = await db.sleepSession.count({ where: { userId: user.id } });
    const biometricCount = await db.dailyBiometric.count({ where: { userId: user.id } });

    // Get the latest activity
    const latestActivity = await db.activity.findFirst({
      where: { userId: user.id },
      orderBy: { startTime: "desc" },
      take: 1,
    });

    return NextResponse.json({
      ok: true,
      user: { id: user.id, email: user.email, name: user.name },
      stats: { activities: activityCount, sleepSessions: sleepCount, dailyBiometrics: biometricCount },
      latestActivity: latestActivity ? { title: latestActivity.title, date: latestActivity.localDate } : null,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
