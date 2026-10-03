/**
 * One-shot seed script: populates the SQLite DB from the hardcoded demo data
 * in src/lib/apex/data.ts. Run with: bun run scripts/seed-db.ts
 *
 * Used when the DB has been reset (e.g. after a schema change dropped data)
 * and real Garmin credentials aren't available to re-sync.
 */
import { db } from "../src/lib/db";

async function main() {
  // Never mix fictional measurements into an existing real-account setup.
  if (process.env.APEX_DEMO_MODE !== "true") {
    console.log("Demo seeding skipped. Set APEX_DEMO_MODE=true only for a demo database.");
    return;
  }
  const email = process.env.GARMIN_EMAIL || "demo@apexhealth.app";
  let user = await db.user.findFirst({ where: { email } });
  if (!user) {
    user = await db.user.create({
      data: {
        email,
        name: "Apex Athlete",
        password: "demo",
        timezone: "Europe/Rome",
        locale: "en",
        theme: "dark",
        units: "metric",
        role: "owner",
        aiTier: "pro",
        sleepTargetH: 8.0,
      },
    });
    console.log("Seeded user:", user.id);
  }

  // Import the hardcoded demo data
  const { activities, sleepSessions } = await import("../src/lib/apex/data");

  // Seed activities (skip if already present)
  const existingActs = await db.activity.count({ where: { userId: user.id } });
  if (existingActs === 0 && activities.length > 0) {
    for (const a of activities) {
      await db.activity.create({
        data: {
          id: String(a.id),
          userId: user.id,
          startTime: a.start_time,
          localDate: a.local_date,
          discipline: a.discipline,
          title: a.title,
          durationS: a.duration_s,
          distanceM: a.distance_m ?? null,
          elevationGainM: a.elevation_gain_m ?? null,
          avgHr: a.avg_hr ?? null,
          maxHr: a.max_hr ?? null,
          avgPower: a.avg_power ?? null,
          npPower: a.np_power ?? null,
          avgSpeedMps: a.avg_speed_mps ?? null,
          calories: a.calories ?? null,
          trainingLoad: a.training_load ?? null,
          dataCompleteness: a.data_completeness,
          sources: a.sources.join(","),
        },
      });
    }
    console.log("Seeded", activities.length, "activities");
  } else {
    console.log("Activities already present:", existingActs);
  }

  // Seed sleep sessions
  const existingSleep = await db.sleepSession.count({ where: { userId: user.id } });
  if (existingSleep === 0 && sleepSessions.length > 0) {
    for (const s of sleepSessions) {
      await db.sleepSession.create({
        data: {
          userId: user.id,
          localDate: s.local_date,
          startTime: s.start_time,
          endTime: s.end_time,
          totalSleepS: s.total_sleep_s ?? null,
          deepS: s.deep_s ?? null,
          lightS: s.light_s ?? null,
          remS: s.rem_s ?? null,
          awakeS: s.awake_s ?? null,
          sleepScore: s.sleep_score ?? null,
          respirationAvg: s.respiration_avg ?? null,
          spo2Avg: s.spo2_avg ?? null,
          restlessness: s.restlessness ?? null,
          sources: s.sources.join(","),
        },
      });
    }
    console.log("Seeded", sleepSessions.length, "sleep sessions");
  } else {
    console.log("Sleep sessions already present:", existingSleep);
  }

  // Seed a few daily biometrics
  const existingBio = await db.dailyBiometric.count({ where: { userId: user.id } });
  if (existingBio === 0) {
    const today = new Date();
    for (let i = 0; i < 7; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      await db.dailyBiometric.create({
        data: {
          userId: user.id,
          date: dateStr,
          restingHr: 48 + Math.round(Math.random() * 4 - 2),
          hrvMs: 55 + Math.round(Math.random() * 10 - 5),
          spo2Avg: 96 + Math.random() * 1.5,
          respirationAvg: 13 + Math.random() * 2,
          steps: 6000 + Math.round(Math.random() * 4000),
          weightKg: 75 + Math.random() * 1.5,
        },
      });
    }
    console.log("Seeded 7 daily biometrics");
  }

  // Sample data is not a connected device. Connections are created explicitly.

  console.log("Seed complete.");
  const counts = {
    activities: await db.activity.count({ where: { userId: user.id } }),
    sleep: await db.sleepSession.count({ where: { userId: user.id } }),
    biometrics: await db.dailyBiometric.count({ where: { userId: user.id } }),
    gear: await db.gear.count({ where: { userId: user.id } }),
    integrations: await db.integration.count({ where: { userId: user.id } }),
  };
  console.log("Final counts:", counts);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await db.$disconnect();
  });
