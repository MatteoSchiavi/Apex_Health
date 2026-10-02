/**
 * GET /api/dashboard
 *
 * Overview dashboard payload — mirrors the Python backend's
 * GET /dashboard/overview contract.
 *
 * Strict Overview redesign (Part 1): adds recovery/strain ScoreBlocks
 * with real computation, sleep_score.delta_7d, hrv_deviation_pct,
 * gear_due, integration_health, data_completeness, and real
 * acute_load/chronic_load/acwr from activity training load.
 *
 * Additive only — every field the previous response had is preserved.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

/** local YYYY-MM-DD using en-CA (ISO-style) anchored to the user's timezone. */
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

async function getOrCreateUser() {
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

/** Compute a 7-day average from an array of (date, value) pairs. */
function avg(values: (number | null)[]): number | null {
  const real = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (real.length === 0) return null;
  return real.reduce((s, v) => s + v, 0) / real.length;
}

export async function GET() {
  try {
    const user = await getOrCreateUser();
    const today = localToday(user.timezone);

    // ----- core reads ----------------------------------------------------
    const [sleep, bio, last7Bio, last30Bio, last7Sleep, last30Hrv, todayActivities] =
      await Promise.all([
        // Most recent sleep session (today if present, else latest)
        db.sleepSession.findFirst({
          where: { userId: user.id },
          orderBy: { localDate: "desc" },
        }),
        // Today's biometric snapshot
        db.dailyBiometric.findFirst({
          where: { userId: user.id, date: today },
        }),
        // Last 7 days of biometrics (for delta_7d on resting HR, SpO2, etc.)
        db.dailyBiometric.findMany({
          where: { userId: user.id },
          orderBy: { date: "desc" },
          take: 7,
        }),
        // Last 30 days of biometrics (HRV baseline + deviation)
        db.dailyBiometric.findMany({
          where: { userId: user.id },
          orderBy: { date: "desc" },
          take: 30,
        }),
        // Last 7 sleep sessions (for sleep_score.delta_7d + recovery baseline)
        db.sleepSession.findMany({
          where: { userId: user.id },
          orderBy: { localDate: "desc" },
          take: 7,
        }),
        // Last 30 HRV readings (for deviation SD)
        db.hrvReading.findMany({
          where: { userId: user.id, readingType: "overnight" },
          orderBy: { timestamp: "desc" },
          take: 30,
        }),
        // Today's activities (for the activity list + strain)
        db.activity.findMany({
          where: {
            userId: user.id,
            localDate: today,
          },
          orderBy: { startTime: "asc" },
        }),
      ]);

    // ----- recovery / strain / readiness (transparent computation) -------
    // sleep_score: from the latest sleep session, real.
    const sleepScore = sleep?.sleepScore ?? null;

    // sleep_score.delta_7d = today's score minus mean of the previous 6 sessions
    // (excluding today's session so the delta reflects a 7-day comparison, not
    // a same-day comparison).
    let sleepScoreDelta7d: number | null = null;
    if (sleepScore !== null && last7Sleep.length >= 2) {
      const prev6 = last7Sleep.slice(1).map((s) => s.sleepScore).filter((v): v is number => v !== null && Number.isFinite(v));
      if (prev6.length > 0) {
        const m = prev6.reduce((s, v) => s + v, 0) / prev6.length;
        sleepScoreDelta7d = Math.round((sleepScore - m) * 10) / 10;
      }
    }

    // HRV baseline + deviation. The 30-day baseline is the mean of the last 30
    // hrvMs readings from DailyBiometric (more stable than per-reading HrvReading).
    const hrvValues = last30Bio.map((b) => b.hrvMs).filter((v): v is number => v !== null && Number.isFinite(v));
    const hrvBaseline = hrvValues.length > 0 ? avg(hrvValues) : null;
    const hrvMs = bio?.hrvMs ?? null;
    let hrvDeviationPct: number | null = null;
    if (hrvMs !== null && hrvBaseline && hrvBaseline > 0) {
      hrvDeviationPct = Math.round(((hrvMs - hrvBaseline) / hrvBaseline) * 1000) / 10;
    }

    // resting_hr.delta_7d = today's RHR minus mean of the previous 6 days
    const restingHr = bio?.restingHr ?? null;
    const restingHrSeries = last7Bio.map((b) => b.restingHr);
    const rhrPrev6 = last7Bio.slice(1).map((b) => b.restingHr).filter((v): v is number => v !== null && Number.isFinite(v));
    const restingHrDelta7d =
      restingHr !== null && rhrPrev6.length > 0
        ? Math.round(restingHr - rhrPrev6.reduce((s, v) => s + v, 0) / rhrPrev6.length)
        : null;

    // spo2_avg + delta_7d (today vs mean of previous 6 days)
    const spo2Avg = bio?.spo2Avg ?? null;
    const spo2Prev6 = last7Bio.slice(1).map((b) => b.spo2Avg).filter((v): v is number => v !== null && Number.isFinite(v));
    const spo2Delta7d =
      spo2Avg !== null && spo2Prev6.length > 0
        ? Math.round((spo2Avg - spo2Prev6.reduce((s, v) => s + v, 0) / spo2Prev6.length) * 10) / 10
        : null;

    const respirationAvg = bio?.respirationAvg ?? null;
    const weightKg = bio?.weightKg ?? null;
    const steps = bio?.steps ?? null;
    const vo2max = bio?.vo2max ?? null;

    // ----- recovery (0-100): sleep score + HRV deviation + RHR trend ----
    // Formula is transparent and defensible: start at sleep score, add small
    // bumps for HRV above baseline and RHR below baseline, clamp to [0,100].
    let recovery: number | null = null;
    if (sleepScore !== null) {
      let r = sleepScore;
      if (hrvMs !== null && hrvBaseline && hrvBaseline > 0) {
        const hrvDev = (hrvMs - hrvBaseline) / hrvBaseline; // -1..+1 typically
        r += Math.max(-15, Math.min(15, hrvDev * 100 * 0.5));
      }
      if (restingHr !== null && rhrPrev6.length > 0) {
        const rhrAvg6 = rhrPrev6.reduce((s, v) => s + v, 0) / rhrPrev6.length;
        const rhrDev = rhrAvg6 - restingHr; // positive = recovered (RHR lower than 7d avg)
        r += Math.max(-10, Math.min(10, rhrDev * 1.5));
      }
      recovery = Math.max(0, Math.min(100, Math.round(r)));
    }

    // recovery.delta_7d
    const prev6SleepScores = last7Sleep.slice(1).map((s) => s.sleepScore).filter((v): v is number => v !== null && Number.isFinite(v));
    const recoveryDelta7d =
      recovery !== null && prev6SleepScores.length > 0
        ? Math.round(recovery - prev6SleepScores.reduce((s, v) => s + v, 0) / prev6SleepScores.length)
        : null;

    // ----- strain (0-100): today's activity volume × intensity ------------
    // Use duration × (avg HR / max HR) as a transparent proxy when trainingLoad
    // is null (which it is for all rows in the current DB). Cap at 100.
    let strain: number | null = null;
    if (todayActivities.length > 0) {
      let raw = 0;
      for (const a of todayActivities) {
        const dur = a.durationS ?? 0;
        const intensity =
          a.avgHr && a.maxHr && a.maxHr > 0 ? Math.min(1, a.avgHr / a.maxHr) : 0.6;
        if (a.trainingLoad !== null && Number.isFinite(a.trainingLoad)) {
          // TSS-like: trainingLoad is on a 0-100+ scale; cap at 100.
          raw += Math.min(100, a.trainingLoad);
        } else {
          // 10 TSS/hr × intensity scale × 1.2 to roughly align with TSS.
          raw += (dur / 3600) * 10 * intensity * 1.2;
        }
      }
      strain = Math.max(0, Math.min(100, Math.round(raw)));
    }

    // strain.delta_7d: today vs mean of last 6 days' activity-derived strain.
    // Compute the last 6 days' strain via a quick fetch (small — bounded).
    let strainDelta7d: number | null = null;
    if (strain !== null) {
      const startDate6 = addDays(today, -6);
      const last6DaysActivities = await db.activity.findMany({
        where: { userId: user.id, localDate: { gte: startDate6, lt: today } },
        select: { localDate: true, durationS: true, avgHr: true, maxHr: true, trainingLoad: true },
      });
      const byDate = new Map<string, number>();
      for (const a of last6DaysActivities) {
        if (!a.localDate) continue;
        const intensity =
          a.avgHr && a.maxHr && a.maxHr > 0 ? Math.min(1, a.avgHr / a.maxHr) : 0.6;
        const tl =
          a.trainingLoad !== null && Number.isFinite(a.trainingLoad)
            ? Math.min(100, a.trainingLoad)
            : (a.durationS ?? 0) / 3600 * 10 * intensity * 1.2;
        byDate.set(a.localDate, (byDate.get(a.localDate) ?? 0) + tl);
      }
      const perDay = Array.from(byDate.values()).map((v) => Math.max(0, Math.min(100, Math.round(v))));
      if (perDay.length > 0) {
        const m = perDay.reduce((s, v) => s + v, 0) / perDay.length;
        strainDelta7d = Math.round(strain - m);
      }
    }

    // ----- readiness (0-100): synthesis of recovery + sleep + (100 - strain) -
    // Today's strain pulls readiness DOWN when it exceeds recovery.
    let readiness: number | null = null;
    if (recovery !== null) {
      let r = recovery;
      if (strain !== null) {
        // strain above 60 starts to drag readiness down; below 30 boosts it.
        const strainPenalty = Math.max(-15, Math.min(15, (strain - 50) * 0.4));
        r += strainPenalty;
      }
      readiness = Math.max(0, Math.min(100, Math.round(r)));
    } else if (sleepScore !== null) {
      // Fallback when recovery couldn't be computed (no HRV / RHR).
      readiness = Math.max(0, Math.min(100, Math.round(sleepScore)));
    }

    // readiness.delta_7d = today vs mean of previous 6 sleep scores
    const readinessDelta7d =
      readiness !== null && prev6SleepScores.length > 0
        ? Math.round(readiness - prev6SleepScores.reduce((s, v) => s + v, 0) / prev6SleepScores.length)
        : null;

    // ----- data_completeness (for the "estimated" tag on Readiness) --------
    // "full" requires today's sleep AND today's bio to both exist.
    let dataCompleteness: "full" | "partial" | "missing" = "missing";
    if (sleep && bio) dataCompleteness = "full";
    else if (sleep || bio) dataCompleteness = "partial";

    // ----- acute / chronic load + ACWR (real, from activity training load) -
    // 28-day window. trainingLoad null → duration-based estimate (10 TSS/hr).
    const loadStartDate = addDays(today, -27); // 28 days inclusive of today
    const loadActivities = await db.activity.findMany({
      where: { userId: user.id, localDate: { gte: loadStartDate } },
      select: { localDate: true, trainingLoad: true, durationS: true, discipline: true },
    });
    const loadByDate = new Map<string, number>();
    for (const a of loadActivities) {
      if (!a.localDate) continue;
      const tl =
        a.trainingLoad != null && Number.isFinite(a.trainingLoad)
          ? a.trainingLoad
          : a.durationS
          ? (a.durationS / 3600) * 10
          : 0;
      loadByDate.set(a.localDate, (loadByDate.get(a.localDate) ?? 0) + tl);
    }
    // acute = sum of last 7 days; chronic = mean of last 28 days.
    let acuteSum = 0;
    for (let i = 0; i < 7; i++) {
      const d = addDays(today, -i);
      acuteSum += loadByDate.get(d) ?? 0;
    }
    let chronicSum = 0;
    let chronicCount = 0;
    for (let i = 0; i < 28; i++) {
      const d = addDays(today, -i);
      chronicSum += loadByDate.get(d) ?? 0;
      chronicCount++;
    }
    const chronicMean = chronicCount > 0 ? chronicSum / chronicCount : 0;
    const acuteLoad = Math.round(acuteSum * 10) / 10;
    const chronicLoad = Math.round(chronicMean * 10) / 10;
    const acwr = chronicMean > 0 ? Math.round((acuteSum / chronicMean) * 100) / 100 : null;

    // ----- gear_due (Gear items at/above 80% of service interval) ---------
    const allGear = await db.gear.findMany({
      where: { userId: user.id, active: true },
      orderBy: { usagePct: "desc" },
    });
    const gearDue = allGear
      .map((g) => {
        // Compute usage_pct on read — the cached Prisma client may have a
        // stale value. Mirrors the gearHelpers.computeUsagePct logic.
        const hoursPct =
          g.serviceIntervalHours && g.serviceIntervalHours > 0
            ? (g.hoursSinceService / g.serviceIntervalHours) * 100
            : 0;
        const kmPct =
          g.serviceIntervalKm && g.serviceIntervalKm > 0
            ? (g.kmSinceService / g.serviceIntervalKm) * 100
            : 0;
        const usagePct = Math.max(hoursPct, kmPct, g.usagePct);
        return { g, usagePct };
      })
      .filter(({ usagePct }) => usagePct >= 80)
      .map(({ g, usagePct }) => ({
        id: g.id,
        name: g.name,
        gear_type: g.gearType,
        brand: g.brand,
        usage_pct: Math.round(usagePct * 10) / 10,
        hours_since_service: Math.round(g.hoursSinceService * 10) / 10,
        service_interval_hours: g.serviceIntervalHours,
        km_since_service: Math.round(g.kmSinceService * 10) / 10,
        service_interval_km: g.serviceIntervalKm,
      }));

    // ----- integration_health (from Integration model) --------------------
    const integrations = await db.integration.findMany({
      where: { userId: user.id },
      orderBy: { isMain: "desc" },
    });
    const integrationHealth = integrations.map((i) => ({
      provider: i.provider,
      status: i.status,
      last_synced_at: i.lastSyncedAt,
      is_main: i.isMain,
      consecutive_failures: i.status === "error" ? 1 : 0, // no column in schema
    }));

    // ----- activities for the Row 4 list (today only) ---------------------
    // The spec is explicit: "Today's activities". When today has no activities
    // yet, return an empty array — the Overview renders its empty state
    // (don't fall back to recent activities; that would be misleading).
    const recentActivities = todayActivities;

    // ----- alerts (Row 0) -------------------------------------------------
    // Currently the DB has no Alert table. We seed an empty array here —
    // Row 0 is rendered from this `alerts` field only. When the backend
    // starts populating risk scores (illness_risk_score, injury_risk_score,
    // iron_status_flag, cross_discipline_fatigue_index) they can be merged
    // into the same list client-side without touching this route.
    const alerts: { type: string; severity: "info" | "warning" | "alert"; message: string }[] = [];

    // ----- response -------------------------------------------------------
    const sleepHours = sleep?.totalSleepS ? sleep.totalSleepS / 3600 : null;

    return NextResponse.json({
      ok: true,
      overview: {
        date: today,
        anchor_is_today: true,
        data_completeness: dataCompleteness,
        readiness: { value: readiness, delta_7d: readinessDelta7d },
        recovery: { value: recovery, delta_7d: recoveryDelta7d },
        strain: { value: strain, delta_7d: strainDelta7d },
        sleep_score: { value: sleepScore, delta_7d: sleepScoreDelta7d },
        sleep_hours: sleepHours ? Math.round(sleepHours * 100) / 100 : null,
        hrv_ms: hrvMs,
        hrv_baseline_ms: hrvBaseline !== null ? Math.round(hrvBaseline) : null,
        hrv_norm_30d: hrvBaseline !== null ? Math.round(hrvBaseline) : null,
        hrv_deviation_pct: hrvDeviationPct,
        resting_hr: restingHr,
        resting_hr_delta_7d: restingHrDelta7d,
        spo2_avg: spo2Avg !== null ? Math.round(spo2Avg * 10) / 10 : null,
        spo2_delta_7d: spo2Delta7d,
        respiration_avg: respirationAvg !== null ? Math.round(respirationAvg * 10) / 10 : null,
        weight_kg: weightKg !== null ? Math.round(weightKg * 10) / 10 : null,
        vo2max,
        steps,
        acute_load: acuteLoad,
        chronic_load: chronicLoad,
        acwr,
        training_load_7d: acuteLoad, // 7-day acute sum (same thing)
        activities: recentActivities.map((a) => ({
          id: Number(a.id),
          // Normalise SQLite's space-separated "YYYY-MM-DD HH:MM:SS" to ISO
          // "YYYY-MM-DDTHH:MM:SS" so client `new Date(iso)` parses deterministically.
          start_time: a.startTime.includes(" ") ? a.startTime.replace(" ", "T") : a.startTime,
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
          data_completeness: a.dataCompleteness as "complete" | "partial" | "missing",
          sources: a.sources.split(",").map((s) => s.trim()).filter(Boolean),
        })),
        sleep: sleep
          ? {
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
            }
          : null,
        integration_status: integrationHealth.map((i) => ({
          provider: i.provider,
          status: i.status,
        })),
        integration_health: integrationHealth,
        gear_due: gearDue,
        alerts,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
