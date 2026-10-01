/**
 * Apex Health — Garmin Connect sync service (Node.js).
 *
 * Fetches real data from Garmin Connect using the garmin-connect npm package,
 * stores it in the Prisma database, and returns a summary of what was synced.
 *
 * Credentials are read at CALL TIME (not import time) from either:
 *   1. The Integration table (set via the Settings > Connect Garmin flow), or
 *   2. The GARMIN_EMAIL / GARMIN_PASSWORD env vars (fallback).
 */

import { GarminConnect } from "garmin-connect";
import { db } from "@/lib/db";

let garminClient: GarminConnect | null = null;
let cachedCredsHash: string | null = null;

/** Read Garmin credentials — prefers the Integration table, falls back to env. */
async function getGarminCredentials(userId: number): Promise<{ email: string; password: string } | null> {
  // 1. Check the Integration table for stored Garmin credentials
  const integration = await db.integration.findFirst({
    where: { userId, provider: "Garmin" },
  });
  if (integration?.garminEmail && integration?.garminPassword) {
    return { email: integration.garminEmail, password: integration.garminPassword };
  }
  // 2. Fall back to env vars
  const envEmail = process.env.GARMIN_EMAIL || "";
  const envPass = process.env.GARMIN_PASSWORD || "";
  if (envEmail && envPass) {
    return { email: envEmail, password: envPass };
  }
  return null;
}

async function getGarminClient(userId: number): Promise<GarminConnect> {
  const creds = await getGarminCredentials(userId);
  if (!creds || !creds.email || !creds.password) {
    throw new Error("No Garmin credentials connected. Use Settings > Connect Garmin to add them, or set GARMIN_EMAIL/GARMIN_PASSWORD in .env.");
  }
  // Re-login if credentials changed (compare a simple hash)
  const hash = `${creds.email}:${creds.password.slice(0, 2)}`;
  if (garminClient && cachedCredsHash === hash) return garminClient;
  const client = new GarminConnect({
    username: creds.email,
    password: creds.password,
  });
  await client.login();
  garminClient = client;
  cachedCredsHash = hash;
  return client;
}

export interface SyncReport {
  activities: number;
  sleepSessions: number;
  dailyStats: number;
  hrvReadings: number;
  errors: string[];
}

export async function syncGarminData(userId: number): Promise<SyncReport> {
  const report: SyncReport = { activities: 0, sleepSessions: 0, dailyStats: 0, hrvReadings: 0, errors: [] };

  try {
    const client = await getGarminClient(userId);

    // 1. Sync activities (last 50)
    try {
      const activities = await client.getActivities(0, 50);
      for (const a of activities) {
        const activityType = a.activityType?.typeKey || "other";
        const discipline = mapDiscipline(activityType);
        const startLocal = a.startTimeLocal || "";
        const localDate = startLocal.slice(0, 10);

        await db.activity.upsert({
          where: { id: String(a.activityId) },
          update: {
            startTime: startLocal,
            localDate,
            discipline,
            title: a.activityName || "unnamed",
            durationS: Math.round(a.duration || 0),
            distanceM: a.distance > 0 ? a.distance : null,
            elevationGainM: a.elevationGain > 0 ? Math.round(a.elevationGain) : null,
            avgHr: a.averageHR ? Math.round(a.averageHR) : null,
            maxHr: a.maxHR ? Math.round(a.maxHR) : null,
            avgSpeedMps: a.averageSpeed ? Math.round(a.averageSpeed * 100) / 100 : null,
            calories: a.calories ? Math.round(a.calories) : null,
            sources: "Garmin",
          },
          create: {
            id: String(a.activityId),
            userId,
            startTime: startLocal,
            localDate,
            discipline,
            title: a.activityName || "unnamed",
            durationS: Math.round(a.duration || 0),
            distanceM: a.distance > 0 ? a.distance : null,
            elevationGainM: a.elevationGain > 0 ? Math.round(a.elevationGain) : null,
            avgHr: a.averageHR ? Math.round(a.averageHR) : null,
            maxHr: a.maxHR ? Math.round(a.maxHR) : null,
            avgSpeedMps: a.averageSpeed ? Math.round(a.averageSpeed * 100) / 100 : null,
            calories: a.calories ? Math.round(a.calories) : null,
            sources: "Garmin",
          },
        });
        report.activities++;
      }
    } catch (e) {
      report.errors.push(`Activities: ${e instanceof Error ? e.message : "unknown"}`);
    }

    // 2. Sync sleep data (last 14 days)
    try {
      const today = new Date();
      for (let i = 0; i < 14; i++) {
        const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
        const dateStr = d.toISOString().slice(0, 10);

        try {
          const sleepData = await client.getSleepData(d);
          const dto = sleepData?.dailySleepDTO;
          if (dto && dto.sleepTimeSeconds > 0) {
            const existing = await db.sleepSession.findFirst({
              where: { userId, localDate: dateStr },
            });

            const totalSleep = dto.sleepTimeSeconds || 0;
            const deep = dto.deepSleepSeconds || 0;
            const rem = dto.remSleepSeconds || 0;
            const light = dto.lightSleepSeconds || 0;
            const awake = dto.awakeSleepSeconds || 0;
            const quality = totalSleep > 0 ? (deep + rem) / totalSleep : 0;
            const durationScore = Math.min(1.0, totalSleep / 28800);
            const score = Math.round(quality * 50 + durationScore * 50);

            const startMs = dto.sleepStartTimestampGMT;
            const endMs = dto.sleepEndTimestampGMT;
            const startTime = startMs ? new Date(startMs).toISOString() : dateStr;
            const endTime = endMs ? new Date(endMs).toISOString() : dateStr;

            if (existing) {
              await db.sleepSession.update({
                where: { id: existing.id },
                data: { startTime, endTime, totalSleepS: totalSleep, deepS: deep, lightS: light, remS: rem, awakeS: awake, sleepScore: score, sources: "Garmin" },
              });
            } else {
              await db.sleepSession.create({
                data: { userId, localDate: dateStr, startTime, endTime, totalSleepS: totalSleep, deepS: deep, lightS: light, remS: rem, awakeS: awake, sleepScore: score, sources: "Garmin" },
              });
            }
            report.sleepSessions++;
          }
        } catch {
          // Individual day might not have sleep data — skip
        }
      }
    } catch (e) {
      report.errors.push(`Sleep: ${e instanceof Error ? e.message : "unknown"}`);
    }

    // 3. Sync daily stats (steps + HR) (last 7 days)
    try {
      const today = new Date();
      for (let i = 0; i < 7; i++) {
        const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
        const dateStr = d.toISOString().slice(0, 10);

        try {
          const steps = await client.getSteps(d);
          const hr = await client.getHeartRate(d);
          
          await db.dailyBiometric.upsert({
            where: { userId_date: { userId, date: dateStr } },
            update: { 
              steps: typeof steps === "number" ? steps : 0,
              restingHr: hr?.restingHeartRate ? Math.round(hr.restingHeartRate) : null,
            },
            create: { 
              userId, date: dateStr, 
              steps: typeof steps === "number" ? steps : 0,
              restingHr: hr?.restingHeartRate ? Math.round(hr.restingHeartRate) : null,
            },
          });
          report.dailyStats++;
        } catch { /* skip */ }
      }
    } catch (e) {
      report.errors.push(`Daily stats: ${e instanceof Error ? e.message : "unknown"}`);
    }

  } catch (e) {
    report.errors.push(`Login: ${e instanceof Error ? e.message : "unknown"}`);
  }

  return report;
}

function mapDiscipline(typeKey: string): string {
  const map: Record<string, string> = {
    cycling: "cycling", road_biking: "cycling", mountain_biking: "cycling",
    e_bike_mountain: "cycling", e_bike_road: "cycling", indoor_cycling: "cycling",
    running: "running", trail_running: "running", track_running: "running",
    swimming: "swimming", open_water_swimming: "swimming", lap_swimming: "swimming",
    strength_training: "strength", hiking: "hiking", walking: "walking",
    sailing_v2: "sailing", boating_v2: "boating", rowing: "rowing",
    fitness_equipment: "strength",
  };
  return map[typeKey] || "cycling";
}

export { getGarminClient };
