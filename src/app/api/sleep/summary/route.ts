/**
 * GET /api/sleep/summary?days=N
 *
 * Plan §4 Sleep list summary block. Computes the four "Row 1" stats
 * server-side so the client doesn't have to re-walk the session list:
 *   - avg_duration_s          average total_sleep_s across the window
 *   - avg_score               average sleep_score across the window
 *   - target_s                the user's sleep target (me.sleepTargetH × 3600,
 *                             default 8h)
 *   - regularity_bed_sd_min   circular SD of bedtime (minutes)
 *   - regularity_wake_sd_min  circular SD of wake time (minutes)
 *   - median_bedtime          circular mean bedtime, minutes-of-day
 *   - median_wake             circular mean wake,  minutes-of-day
 *   - sleep_debt_s            cumulative shortfall vs target over the last
 *                             7 nights (negative = surplus)
 *   - window_days             the requested window (echoed for the client)
 *   - count                   number of sessions in the window
 *
 * Regularity uses CIRCULAR standard deviation because bedtime can cross
 * midnight (a 23:30 bedtime and a 01:00 bedtime are 1.5h apart in sleep-land
 * but 1380 vs 60 minutes-of-day are 1320 minutes apart on a linear scale).
 * The median bedtime / wake is reported as the circular MEAN — for the
 * floating-bar timing chart this is the most defensible single
 * representative value.
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  circularMean,
  circularSD,
  mean,
  minutesOfDayUTC,
} from "@/lib/apex/sleepHelpers";

const DEFAULT_TARGET_H = 8;
const DEBT_WINDOW_NIGHTS = 7;

interface SleepSummaryOut {
  ok: boolean;
  window_days: number;
  count: number;
  avg_duration_s: number | null;
  avg_score: number | null;
  target_s: number;
  regularity_bed_sd_min: number | null;
  regularity_wake_sd_min: number | null;
  median_bedtime: number | null; // minutes-of-day
  median_wake: number | null; // minutes-of-day
  sleep_debt_s: number; // negative = surplus
}

export async function GET(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json(
        { ok: false, error: "No user. Run POST /api/garmin/sync first." },
        { status: 404 },
      );
    }

    const { searchParams } = new URL(req.url);
    const days = Math.max(1, Math.min(365, parseInt(searchParams.get("days") || "30")));
    const targetH = user.sleepTargetH ?? DEFAULT_TARGET_H;
    const targetS = Math.round(targetH * 3600);

    // Sessions in the selected window, oldest → newest (so the last 7 are
    // the most recent 7 nights for the debt calculation).
    const sessions = await db.sleepSession.findMany({
      where: { userId: user.id },
      orderBy: { localDate: "desc" },
      take: days,
    });

    const validDur = sessions
      .map((s) => s.totalSleepS)
      .filter((v): v is number => v !== null && Number.isFinite(v));
    const validScore = sessions
      .map((s) => s.sleepScore)
      .filter((v): v is number => v !== null && Number.isFinite(v));

    const bedMinutes = sessions
      .map((s) => minutesOfDayUTC(s.startTime))
      .filter((v) => Number.isFinite(v));
    const wakeMinutes = sessions
      .map((s) => minutesOfDayUTC(s.endTime))
      .filter((v) => Number.isFinite(v));

    // Sleep debt: cumulative shortfall vs target over the last 7 nights.
    // Positive value = you owe sleep (you under-slept). Negative = surplus.
    // Missing total_sleep_s nights contribute 0 sleep (full shortfall).
    const last7 = sessions.slice(0, DEBT_WINDOW_NIGHTS);
    let debtS = 0;
    for (const s of last7) {
      const slept = s.totalSleepS ?? 0;
      debtS += targetS - slept;
    }

    const out: SleepSummaryOut = {
      ok: true,
      window_days: days,
      count: sessions.length,
      avg_duration_s: validDur.length ? Math.round(mean(validDur)!) : null,
      avg_score: validScore.length ? Math.round(mean(validScore)!) : null,
      target_s: targetS,
      regularity_bed_sd_min: circularSD(bedMinutes),
      regularity_wake_sd_min: circularSD(wakeMinutes),
      median_bedtime: circularMean(bedMinutes),
      median_wake: circularMean(wakeMinutes),
      sleep_debt_s: debtS,
    };
    return NextResponse.json(out);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
