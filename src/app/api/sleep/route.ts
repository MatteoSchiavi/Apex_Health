/**
 * GET /api/sleep
 *
 * Two modes:
 *   1. LIST (default)        → /api/sleep?days=14
 *      Returns the user's sleep sessions (most recent first), each enriched
 *      with the matching DailyBiometric's resting_hr + hrv_ms and a
 *      server-computed hrv_deviation_ms (vs the 30-day HRV mean). Also
 *      returns a `baseline` block (30-day sleep_score quantiles, 30-day
 *      HRV mean/sd, 30-day vital stats) so the client can render the list
 *      + table without a second round-trip.
 *
 *   2. NIGHT DETAIL          → /api/sleep?date=YYYY-MM-DD
 *      Returns the single night's session + biometric + hrv_readings
 *      (within the start_time → end_time window) + a `baseline` block
 *      (same as LIST) for the score badge, RangeBar bands, stage averages,
 *      and the HRV deviation trend. This is what SleepNightPage consumes.
 *
 * Plan §4 backend: this route extends the original list-only handler.
 * /api/sleep/summary?days=N (separate file) computes the list-page summary
 * (avg duration, avg score, regularity SDs, sleep debt).
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  circularMean,
  circularSD,
  mean,
  quantile,
  stdev,
  sleepWindowS,
  minutesOfDayUTC,
} from "@/lib/apex/sleepHelpers";

const DEFAULT_TARGET_H = 8;

interface SessionOut {
  local_date: string;
  start_time: string;
  end_time: string;
  total_sleep_s: number | null;
  deep_s: number | null;
  light_s: number | null;
  rem_s: number | null;
  awake_s: number | null;
  sleep_score: number | null;
  respiration_avg: number | null;
  spo2_avg: number | null;
  restlessness: number | null;
  sources: string[];
  // Plan §4 enrichment:
  resting_hr: number | null;
  hrv_ms: number | null;
  hrv_deviation_ms: number | null; // hrv_ms − 30d mean
  hrv_deviation_sd: number | null; // (hrv_ms − 30d mean) / 30d sd (signed)
}

interface VitalStats {
  mean: number | null;
  sd: number | null;
  low: number | null; // mean − 1 SD
  high: number | null; // mean + 1 SD
  count: number;
}

interface BaselineBlock {
  window_days: number;
  target_s: number;
  sleep_scores: {
    p33: number | null;
    p66: number | null;
    mean: number | null;
    sd: number | null;
    count: number;
  };
  // Keys match the client-side StageKey union (deep / light / rem / awake)
  // so the client can index `baseline.stages.deep` etc. without translation.
  stages: {
    deep: { mean_s: number | null; mean_pct: number | null };
    light: { mean_s: number | null; mean_pct: number | null };
    rem: { mean_s: number | null; mean_pct: number | null };
    awake: { mean_s: number | null; mean_pct: number | null };
  };
  vitals: {
    resting_hr: VitalStats;
    hrv_ms: VitalStats;
    spo2_avg: VitalStats;
    respiration_avg: VitalStats;
  };
}

interface HrvReadingOut {
  timestamp: string;
  hrv_ms: number;
  rolling_baseline_ms: number | null;
}

interface BiometricsOut {
  date: string;
  resting_hr: number | null;
  hrv_ms: number | null;
  spo2_avg: number | null;
  respiration_avg: number | null;
  skin_temp_c: number | null;
}

interface NightDetailOut {
  session: SessionOut | null;
  biometrics: BiometricsOut | null;
  hrv_readings: HrvReadingOut[];
  baseline: BaselineBlock;
}

function computeVitalStats(values: number[]): VitalStats {
  const m = mean(values);
  const s = stdev(values);
  return {
    mean: m,
    sd: s,
    low: m !== null && s !== null ? m - s : null,
    high: m !== null && s !== null ? m + s : null,
    count: values.filter((v) => Number.isFinite(v)).length,
  };
}

function toSessionOut(
  s: {
    localDate: string;
    startTime: string;
    endTime: string;
    totalSleepS: number | null;
    deepS: number | null;
    lightS: number | null;
    remS: number | null;
    awakeS: number | null;
    sleepScore: number | null;
    respirationAvg: number | null;
    spo2Avg: number | null;
    restlessness: number | null;
    sources: string;
  },
  bio: {
    restingHr: number | null;
    hrvMs: number | null;
  } | null,
  hrvMean: number | null,
  hrvSd: number | null,
): SessionOut {
  const hrvMs = bio?.hrvMs ?? null;
  const hrvDev =
    hrvMs !== null && hrvMean !== null ? hrvMs - hrvMean : null;
  const hrvDevSd =
    hrvDev !== null && hrvSd !== null && hrvSd > 0 ? hrvDev / hrvSd : null;
  return {
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
    sources: s.sources.split(",").map((x) => x.trim()).filter(Boolean),
    resting_hr: bio?.restingHr ?? null,
    hrv_ms: hrvMs,
    hrv_deviation_ms: hrvDev,
    hrv_deviation_sd: hrvDevSd,
  };
}

/** Compute the 30-day baseline block from a slice of SleepSessions + their
 *  matching DailyBiometrics. Reused by both LIST and NIGHT modes. */
async function computeBaseline(
  userId: number,
  targetH: number,
): Promise<BaselineBlock> {
  const recentSessions = await db.sleepSession.findMany({
    where: { userId },
    orderBy: { localDate: "desc" },
    take: 30,
  });
  const recentDates = recentSessions.map((s) => s.localDate);
  const recentBios = recentDates.length
    ? await db.dailyBiometric.findMany({
        where: { userId, date: { in: recentDates } },
      })
    : [];

  const scores = recentSessions
    .map((s) => s.sleepScore)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const deep = recentSessions
    .map((s) => (s.deepS ?? 0))
    .filter((v) => Number.isFinite(v));
  const light = recentSessions
    .map((s) => (s.lightS ?? 0))
    .filter((v) => Number.isFinite(v));
  const rem = recentSessions
    .map((s) => (s.remS ?? 0))
    .filter((v) => Number.isFinite(v));
  const awake = recentSessions
    .map((s) => (s.awakeS ?? 0))
    .filter((v) => Number.isFinite(v));
  const totalAsleepArr = recentSessions.map((s) =>
    (s.deepS ?? 0) + (s.lightS ?? 0) + (s.remS ?? 0),
  );

  const stageMeanPct = (sums: number[]) => {
    if (!sums.length || !totalAsleepArr.length) return null;
    let sumSecs = 0;
    let sumAsleep = 0;
    for (let i = 0; i < sums.length; i++) {
      sumSecs += sums[i] ?? 0;
      sumAsleep += totalAsleepArr[i] ?? 0;
    }
    return sumAsleep > 0 ? (sumSecs / sumAsleep) * 100 : null;
  };

  const restingHrArr: number[] = [];
  const hrvMsArr: number[] = [];
  const spo2Arr: number[] = [];
  const respArr: number[] = [];
  for (const b of recentBios) {
    if (b.restingHr !== null) restingHrArr.push(b.restingHr);
    if (b.hrvMs !== null) hrvMsArr.push(b.hrvMs);
    if (b.spo2Avg !== null) spo2Arr.push(b.spo2Avg);
    if (b.respirationAvg !== null) respArr.push(b.respirationAvg);
  }

  return {
    window_days: 30,
    target_s: Math.round(targetH * 3600),
    sleep_scores: {
      p33: quantile(scores, 0.33),
      p66: quantile(scores, 0.66),
      mean: mean(scores),
      sd: stdev(scores),
      count: scores.length,
    },
    stages: {
      // Keys are the client-side StageKey union ("deep" | "light" | "rem"
      // | "awake") so the client can index with the same key it uses for
      // the composition bar / table.
      deep: { mean_s: mean(deep), mean_pct: stageMeanPct(deep) },
      light: { mean_s: mean(light), mean_pct: stageMeanPct(light) },
      rem: { mean_s: mean(rem), mean_pct: stageMeanPct(rem) },
      awake: { mean_s: mean(awake), mean_pct: null }, // awake isn't % of asleep
    },
    vitals: {
      resting_hr: computeVitalStats(restingHrArr),
      hrv_ms: computeVitalStats(hrvMsArr),
      spo2_avg: computeVitalStats(spo2Arr),
      respiration_avg: computeVitalStats(respArr),
    },
  };
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
    const targetH = user.sleepTargetH ?? DEFAULT_TARGET_H;

    // ─────────────────────────────────────────────────────── NIGHT DETAIL MODE
    const dateParam = searchParams.get("date");
    if (dateParam) {
      const session = await db.sleepSession.findFirst({
        where: { userId: user.id, localDate: dateParam },
      });
      const bio = await db.dailyBiometric.findFirst({
        where: { userId: user.id, date: dateParam },
      });
      const baseline = await computeBaseline(user.id, targetH);

      let hrvReadings: HrvReadingOut[] = [];
      if (session) {
        const start = session.startTime;
        const end = session.endTime;
        const rows = await db.hrvReading.findMany({
          where: {
            userId: user.id,
            timestamp: { gte: start, lte: end },
          },
          orderBy: { timestamp: "asc" },
        });
        hrvReadings = rows.map((r) => ({
          timestamp: r.timestamp,
          hrv_ms: r.hrvMs,
          rolling_baseline_ms: r.rollingBaselineMs,
        }));
      }

      const sessionOut: SessionOut | null = session
        ? toSessionOut(
            session,
            bio
              ? { restingHr: bio.restingHr, hrvMs: bio.hrvMs }
              : null,
            baseline.vitals.hrv_ms.mean,
            baseline.vitals.hrv_ms.sd,
          )
        : null;

      const biometricsOut: BiometricsOut | null = bio
        ? {
            date: bio.date,
            resting_hr: bio.restingHr,
            hrv_ms: bio.hrvMs,
            spo2_avg: bio.spo2Avg,
            respiration_avg: bio.respirationAvg,
            skin_temp_c: null, // schema doesn't surface skin temp yet
          }
        : null;

      const out: NightDetailOut = {
        session: sessionOut,
        biometrics: biometricsOut,
        hrv_readings: hrvReadings,
        baseline,
      };
      return NextResponse.json({ ok: true, ...out });
    }

    // ──────────────────────────────────────────────────────────── LIST MODE
    const days = parseInt(searchParams.get("days") || "14");
    const sessions = await db.sleepSession.findMany({
      where: { userId: user.id },
      orderBy: { localDate: "desc" },
      take: days,
    });
    const dates = sessions.map((s) => s.localDate);
    const bios = dates.length
      ? await db.dailyBiometric.findMany({
          where: { userId: user.id, date: { in: dates } },
        })
      : [];
    const bioByDate = new Map(bios.map((b) => [b.date, b]));

    const baseline = await computeBaseline(user.id, targetH);
    const hrvMean = baseline.vitals.hrv_ms.mean;
    const hrvSd = baseline.vitals.hrv_ms.sd;

    const items = sessions.map((s) =>
      toSessionOut(s, bioByDate.get(s.localDate) ?? null, hrvMean, hrvSd),
    );

    // List of all sleep dates (oldest → newest) — used by SleepNightPage
    // to compute prev/next night navigation. Same answer for any `days`
    // large enough to cover history; ship ALL of them so navigation works
    // for older nights.
    const allSessions = await db.sleepSession.findMany({
      where: { userId: user.id },
      orderBy: { localDate: "asc" },
      select: { localDate: true },
    });

    return NextResponse.json({
      ok: true,
      items,
      count: items.length,
      baseline,
      all_dates: allSessions.map((s) => s.localDate),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

// Re-export the helpers the summary route uses — kept here so they have
// a single source-of-truth. (Tree-shaken when not imported.)
export {
  circularMean,
  circularSD,
  mean,
  quantile,
  stdev,
  sleepWindowS,
  minutesOfDayUTC,
};
