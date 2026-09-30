/**
 * Apex Health — deterministic mock data layer.
 *
 * These values represent the kind of data the backend would return from the
 * documented endpoints. They are stable across renders so the UI looks
 * consistent; they're rich enough to exercise every chart, table, and detail
 * surface in the application.
 *
 * Real backend endpoints this layer mirrors:
 *   GET /me, GET /dashboard/overview, GET /activities, GET /activities/:id,
 *   GET /activities/:id/streams, GET /sleep, GET /sleep/:date,
 *   GET /sleep/:date/stages, GET /metrics, GET /metrics/:key,
 *   GET /coach/chats, GET /coach/chats/:id, GET /settings/devices,
 *   GET /training/schedule, GET /gym/sessions, GET /challenges
 */

import type {
  ActivityCard,
  ActivityDetail,
  ActivityStream,
  Challenge,
  ChatSession,
  ChatSessionDetail,
  DeviceOut,
  GymSession,
  LabMarker,
  Me,
  MetricCatalogItem,
  MetricTrend,
  Overview,
  SleepDay,
  SleepSession,
  SleepStages,
  TrainingPlanItem,
} from "./types";

/* --------------------------------------------------------- deterministic RNG */

function mulberry32(seed: number) {
  let s = seed >>> 0;
  return () => {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function dateOffset(daysAgo: number, hour = 7, min = 0): string {
  const d = new Date();
  d.setHours(hour, min, 0, 0);
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString();
}

function localDate(daysAgo: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function clamp(x: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, x));
}

function round(x: number, dp = 0) {
  const f = Math.pow(10, dp);
  return Math.round(x * f) / f;
}

/* --------------------------------------------------------------- me */

export const me: Me = {
  user_id: 1,
  email: "matteo.schiavi@apexhealth.app",
  name: "Matteo Schiavi",
  dob: "1989-05-12",
  sex: "male",
  height_cm: 183,
  timezone: "Europe/Rome",
  locale: "en",
  theme: "dark",
  units: "metric",
  role: "owner",
  ai_access_tier: "pro",
  main_integration_id: 1,
};

/* --------------------------------------------------------------- devices */

export const devices: DeviceOut[] = [
  {
    integration_id: 1,
    provider: "Garmin",
    status: "active",
    last_synced_at: dateOffset(0, 8, 12),
    is_main: true,
    connected_at: dateOffset(120, 9, 0),
  },
  {
    integration_id: 2,
    provider: "Whoop",
    status: "active",
    last_synced_at: dateOffset(0, 7, 48),
    is_main: false,
    connected_at: dateOffset(80, 9, 0),
  },
  {
    integration_id: 3,
    provider: "Strava",
    status: "active",
    last_synced_at: dateOffset(0, 6, 30),
    is_main: false,
    connected_at: dateOffset(200, 9, 0),
  },
  {
    integration_id: 4,
    provider: "Oura",
    status: "paused",
    last_synced_at: dateOffset(4, 22, 0),
    is_main: false,
    connected_at: dateOffset(60, 9, 0),
  },
];

/* --------------------------------------------------------------- overview */

export const overview: Overview = {
  date: localDate(0),
  anchor_is_today: true,
  readiness: { value: 84, delta_7d: 7 },
  recovery: { value: 78, delta_7d: 4 },
  strain: { value: 62, delta_7d: -3 },
  sleep_score: { value: 88, delta_7d: 5 },
  sleep_hours: 7.71,
  hrv_ms: 64,
  hrv_baseline_ms: 59,
  hrv_norm_30d: 62,
  resting_hr: 48,
  resting_hr_delta_7d: -2,
  spo2_avg: 97.4,
  spo2_delta_7d: 0.2,
  respiration_avg: 13.6,
  steps: 8420,
  weight_kg: 74.2,
  vo2max: 58.4,
  acute_load: 312,
  chronic_load: 286,
  acwr: 1.09,
  training_load_7d: 312,
  activities: [
    {
      id: 2410,
      start_time: dateOffset(0, 6, 32),
      local_date: localDate(0),
      discipline: "cycling",
      title: "Threshold Intervals · Monte Berico",
      duration_s: 4820,
      distance_m: 32480,
      elevation_gain_m: 412,
      avg_hr: 156,
      max_hr: 174,
      avg_power: 248,
      np_power: 261,
      avg_speed_mps: 6.74,
      calories: 742,
      training_load: 84,
      data_completeness: "complete",
      sources: ["Garmin", "Strava"],
    },
    {
      id: 2409,
      start_time: dateOffset(1, 18, 15),
      local_date: localDate(1),
      discipline: "strength",
      title: "Lower Body Strength · Squat Focus",
      duration_s: 3120,
      distance_m: null,
      elevation_gain_m: null,
      avg_hr: 124,
      max_hr: 148,
      avg_power: null,
      np_power: null,
      avg_speed_mps: null,
      calories: 412,
      training_load: 58,
      data_completeness: "complete",
      sources: ["Garmin", "Manual"],
    },
    {
      id: 2408,
      start_time: dateOffset(2, 6, 18),
      local_date: localDate(2),
      discipline: "running",
      title: "Endurance Run · Adige River Path",
      duration_s: 3640,
      distance_m: 10800,
      elevation_gain_m: 64,
      avg_hr: 142,
      max_hr: 158,
      avg_power: null,
      np_power: null,
      avg_speed_mps: 2.97,
      calories: 604,
      training_load: 64,
      data_completeness: "complete",
      sources: ["Garmin", "Strava"],
    },
  ],
  sleep: {
    start_time: dateOffset(0, 22, 48),
    end_time: dateOffset(0, 6, 35),
    total_sleep_s: 27660,
    sleep_score: 88,
    stages: { deep_s: 5580, light_s: 15360, rem_s: 6720, awake_s: 540 },
    respiration_avg: 13.4,
    spo2_avg: 97.4,
    restlessness: 12,
  },
  integration_status: [
    { provider: "Garmin", status: "active" },
    { provider: "Whoop", status: "active" },
    { provider: "Strava", status: "active" },
  ],
  alerts: [
    {
      type: "hrv",
      severity: "info",
      message: "HRV trending above 28-day baseline — parasympathetic recovery strong.",
    },
    {
      type: "acwr",
      severity: "warning",
      message: "ACWR at 1.09 — within the optimal training window but approaching sweet-spot ceiling.",
    },
    {
      type: "resting_hr",
      severity: "info",
      message: "Resting HR 2 bpm below 7-day baseline — recovery indicator is positive.",
    },
  ],
};

/* --------------------------------------------------------------- activities list */

const activitySeeds: Array<Partial<ActivityCard> & { discipline: ActivityCard["discipline"]; title: string }> = [
  { discipline: "cycling", title: "Threshold Intervals · Monte Berico", avg_power: 248, np_power: 261, distance_m: 32480, duration_s: 4820, elevation_gain_m: 412 },
  { discipline: "strength", title: "Lower Body Strength · Squat Focus", avg_power: null, np_power: null, distance_m: null, duration_s: 3120, elevation_gain_m: null },
  { discipline: "running", title: "Endurance Run · Adige River Path", avg_power: null, np_power: null, distance_m: 10800, duration_s: 3640, elevation_gain_m: 64 },
  { discipline: "cycling", title: "Endurance Ride · Lake Garda Loop", avg_power: 198, np_power: 205, distance_m: 68400, duration_s: 7320, elevation_gain_m: 720 },
  { discipline: "running", title: "VO2max Intervals · 4×4", avg_power: null, np_power: null, distance_m: 8200, duration_s: 2640, elevation_gain_m: 30 },
  { discipline: "cycling", title: "Recovery Spin · Valpolicella", avg_power: 142, np_power: 144, distance_m: 28600, duration_s: 4560, elevation_gain_m: 180 },
  { discipline: "swimming", title: "Pool Swim · 4km Set", avg_power: null, np_power: null, distance_m: 4000, duration_s: 5880, elevation_gain_m: null },
  { discipline: "running", title: "Long Run · Lessinia Hills", avg_power: null, np_power: null, distance_m: 21400, duration_s: 7240, elevation_gain_m: 480 },
  { discipline: "strength", title: "Upper Body · Push Focus", avg_power: null, np_power: null, distance_m: null, duration_s: 2940, elevation_gain_m: null },
  { discipline: "cycling", title: "Climb Repeats · Monte Baldo", avg_power: 268, np_power: 281, distance_m: 41200, duration_s: 6180, elevation_gain_m: 980 },
  { discipline: "running", title: "Tempo Run · City Centre", avg_power: null, np_power: null, distance_m: 9600, duration_s: 3120, elevation_gain_m: 22 },
  { discipline: "cycling", title: "Race Simulation · Crit Round", avg_power: 286, np_power: 312, distance_m: 38400, duration_s: 3900, elevation_gain_m: 120 },
  { discipline: "hiking", title: "Hike · Monte Lessini", avg_power: null, np_power: null, distance_m: 14600, duration_s: 9240, elevation_gain_m: 640 },
  { discipline: "rowing", title: "Erg Row · 6×500m", avg_power: 218, np_power: null, distance_m: 3000, duration_s: 2340, elevation_gain_m: null },
  { discipline: "running", title: "Hill Repeats · San Pietro", avg_power: null, np_power: null, distance_m: 6800, duration_s: 2820, elevation_gain_m: 220 },
  { discipline: "cycling", title: "Sweet Spot · Piano di Fugazze", avg_power: 254, np_power: 258, distance_m: 54200, duration_s: 6720, elevation_gain_m: 880 },
  { discipline: "strength", title: "Posterior Chain · Deadlift", avg_power: null, np_power: null, distance_m: null, duration_s: 3360, elevation_gain_m: null },
  { discipline: "running", title: "Easy Recovery · 6km", avg_power: null, np_power: null, distance_m: 6000, duration_s: 2280, elevation_gain_m: 12 },
];

export function listActivities(days = 30): ActivityCard[] {
  const items: ActivityCard[] = [];
  for (let i = 0; i < days; i++) {
    const seed = mulberry32(i + 1);
    if (seed() < 0.42) continue; // rest days
    const template = activitySeeds[Math.floor(seed() * activitySeeds.length)];
    const id = 2400 - i * 7 - Math.floor(seed() * 5);
    const start_time = dateOffset(i, 6 + Math.floor(seed() * 4), Math.floor(seed() * 60));
    const local_date = localDate(i);
    const variance = 0.92 + seed() * 0.16;
    const distance_m = template.distance_m === null ? null : Math.round(template.distance_m * variance);
    const duration_s = Math.round(template.duration_s * (0.95 + seed() * 0.1));
    const avg_hr = template.avg_hr === null ? null : Math.round(template.avg_hr + (seed() - 0.5) * 8);
    const max_hr = avg_hr === null ? null : avg_hr + Math.round(8 + seed() * 18);
    const avg_power = template.avg_power === null ? null : Math.round((template.avg_power as number) * (0.96 + seed() * 0.08));
    const np_power = template.np_power === null ? null : Math.round((template.np_power as number) * (0.96 + seed() * 0.08));
    const avg_speed_mps =
      distance_m === null ? null : round(distance_m / duration_s, 2);
    const calories = Math.round((avg_hr ?? 130) * duration_s * 0.00018);
    const training_load = Math.round((duration_s / 60) * (avg_hr ? (avg_hr - 100) / 80 : 0.6) * (0.8 + seed() * 0.4));
    const completenessRoll = seed();
    const data_completeness: ActivityCard["data_completeness"] =
      completenessRoll > 0.88 ? "partial" : completenessRoll > 0.97 ? "missing" : "complete";
    items.push({
      id,
      start_time,
      local_date,
      discipline: template.discipline,
      title: template.title,
      duration_s,
      distance_m,
      elevation_gain_m: template.elevation_gain_m === null ? null : Math.round(template.elevation_gain_m * variance),
      avg_hr,
      max_hr,
      avg_power,
      np_power,
      avg_speed_mps,
      calories,
      training_load,
      data_completeness,
      sources: template.discipline === "strength" ? ["Manual", "Garmin"] : ["Garmin", "Strava"],
    });
  }
  return items;
}

export const activities: ActivityCard[] = listActivities(90);

/* --------------------------------------------------------------- activity detail */

function genRoute(): ActivityDetail["route"] {
  const route: { lat: number; lng: number; ele: number | null }[] = [];
  const baseLat = 45.4386;
  const baseLng = 11.0;
  for (let i = 0; i < 240; i++) {
    const t = i / 240;
    const seed = mulberry32(i * 7 + 13);
    const lat = baseLat + Math.sin(t * Math.PI * 3) * 0.04 + (seed() - 0.5) * 0.005;
    const lng = baseLng + t * 0.08 + Math.cos(t * Math.PI * 2) * 0.03 + (seed() - 0.5) * 0.005;
    const ele = 80 + Math.sin(t * Math.PI * 5) * 40 + t * 180 + (seed() - 0.5) * 8;
    route.push({ lat, lng, ele: round(ele, 1) });
  }
  return route;
}

function genStream(tCount: number, type: "hr" | "power" | "speed" | "alt" | "cadence"): (number | null)[] {
  const out: (number | null)[] = [];
  const seed = mulberry32(type.length * 31 + 7);
  let base = type === "hr" ? 150 : type === "power" ? 240 : type === "speed" ? 6.5 : type === "alt" ? 80 : 90;
  for (let i = 0; i < tCount; i++) {
    const phase = i / tCount;
    const drift = Math.sin(phase * Math.PI * 6) * (type === "hr" ? 18 : type === "power" ? 40 : type === "speed" ? 1.4 : type === "alt" ? 60 : 6);
    const noise = (seed() - 0.5) * (type === "hr" ? 6 : type === "power" ? 18 : 0.6);
    if (seed() < 0.012) out.push(null);
    else out.push(round(Math.max(0, base + drift + noise), type === "speed" || type === "alt" ? 1 : 0));
    if (i % 40 === 0) base += (seed() - 0.5) * 4;
  }
  return out;
}

export function getActivityDetail(id: number): ActivityDetail {
  const card = activities.find((a) => a.id === id) ?? activities[0];
  const tCount = 240;
  const t: number[] = Array.from({ length: tCount }, (_, i) => Math.round((card.duration_s * i) / (tCount - 1)));
  const route = card.discipline === "cycling" || card.discipline === "running" || card.discipline === "hiking" ? genRoute() : null;
  return {
    ...card,
    has_streams: true,
    stream_types: ["hr", "power", "speed", "alt", "cadence"],
    laps: Array.from({ length: 8 }, (_, i) => {
      const lapDur = Math.round(card.duration_s / 8);
      return {
        lap_index: i + 1,
        start_time: new Date(new Date(card.start_time).getTime() + lapDur * 1000 * i).toISOString(),
        duration_s: lapDur,
        distance_m: card.distance_m === null ? null : Math.round((card.distance_m / 8) * (0.94 + mulberry32(i + 1)() * 0.12)),
        avg_hr: card.avg_hr === null ? null : Math.round(card.avg_hr + (mulberry32(i + 1)() - 0.5) * 12),
        max_hr: card.max_hr === null ? null : card.max_hr - Math.round(mulberry32(i + 2)() * 6),
        avg_power: card.avg_power === null ? null : Math.round(card.avg_power + (mulberry32(i + 3)() - 0.5) * 22),
        calories: Math.round((card.calories ?? 0) / 8),
      };
    }),
    route,
    weather: {
      temp_c: 14,
      wind_kph: 9,
      humidity_pct: 62,
      conditions: "Partly cloudy",
    },
    gear: card.discipline === "cycling"
      ? [
          { id: 1, name: "Pinarello Dogma F", type: "bike" },
          { id: 2, name: "Shimano Ultegra Di2", type: "groupset" },
          { id: 3, name: "Garmin Edge 1040", type: "computer" },
          { id: 4, name: "Assioma Duo Pedals", type: "power_meter" },
        ]
      : card.discipline === "running"
        ? [
            { id: 5, name: "Nike ZoomX Vaporfly", type: "shoes" },
            { id: 6, name: "Garmin Forerunner 965", type: "watch" },
          ]
        : card.discipline === "strength"
          ? [
              { id: 7, name: "SBD Belt", type: "belt" },
              { id: 8, name: "Knee Sleeves", type: "sleeves" },
            ]
          : [],
    source_metrics: {
      heart_rate: "Garmin",
      power: "Assioma Duo",
      location: "Garmin Edge 1040",
      cadence: "Garmin",
      elevation: "Barometric (Garmin Edge)",
    },
  };
}

export function getActivityStreams(id: number): ActivityStream {
  const card = activities.find((a) => a.id === id) ?? activities[0];
  const tCount = 240;
  const t: number[] = Array.from({ length: tCount }, (_, i) => Math.round((card.duration_s * i) / (tCount - 1)));
  return {
    activity_id: id,
    t,
    columns: {
      hr: genStream(tCount, "hr"),
      power: card.avg_power === null ? new Array(tCount).fill(null) : genStream(tCount, "power"),
      speed: card.avg_speed_mps === null ? new Array(tCount).fill(null) : genStream(tCount, "speed"),
      alt: genStream(tCount, "alt"),
      cadence: genStream(tCount, "cadence"),
    },
  };
}

/* --------------------------------------------------------------- sleep */

export function listSleep(days = 30): SleepSession[] {
  const items: SleepSession[] = [];
  for (let i = 0; i < days; i++) {
    const seed = mulberry32(i + 11);
    const score = Math.round(72 + seed() * 22);
    const total = Math.round((6 * 3600 + seed() * 2 * 3600) / 60) * 60;
    const deep = Math.round(total * (0.16 + seed() * 0.08));
    const rem = Math.round(total * (0.20 + seed() * 0.06));
    const light = total - deep - rem - Math.round(total * 0.04);
    const awake = Math.round(total * (0.02 + seed() * 0.04));
    items.push({
      local_date: localDate(i),
      start_time: dateOffset(i + 1, 22 + Math.round(seed() * 2), Math.round(seed() * 60)),
      end_time: dateOffset(i, 6 + Math.round(seed() * 2), Math.round(seed() * 60)),
      total_sleep_s: total,
      deep_s: deep,
      light_s: light,
      rem_s: rem,
      awake_s: awake,
      sleep_score: score,
      respiration_avg: round(12.5 + seed() * 2, 1),
      spo2_avg: round(96.5 + seed() * 1.8, 1),
      restlessness: Math.round(8 + seed() * 14),
      sources: seed() > 0.3 ? ["Whoop", "Garmin"] : ["Whoop"],
    });
  }
  return items;
}

export const sleepSessions: SleepSession[] = listSleep(30);

export function getSleepDay(date: string): SleepDay {
  const session = sleepSessions.find((s) => s.local_date === date) ?? sleepSessions[0];
  const seed = mulberry32(date.split("-").reduce((acc, p) => acc + parseInt(p, 10), 0));
  // build a hypnogram — alternating segments across the night
  const segs: SleepStages["segments"] = [];
  const start = new Date(session.start_time).getTime();
  const end = new Date(session.end_time).getTime();
  const totalMs = end - start;
  const stageOrder: Array<SleepStages["segments"][number]["stage"]> = ["awake", "light", "deep", "light", "rem", "light", "deep", "light", "rem", "light", "rem", "light", "awake"];
  const segCount = stageOrder.length;
  for (let i = 0; i < segCount; i++) {
    const segStart = start + (totalMs * i) / segCount;
    const segEnd = start + (totalMs * (i + 1)) / segCount;
    segs.push({
      t_start: new Date(segStart).toISOString(),
      t_end: new Date(segEnd).toISOString(),
      stage: stageOrder[i],
    });
  }
  const hrv_readings = Array.from({ length: 24 }, (_, i) => {
    const ts = new Date(start + (totalMs * i) / 24).toISOString();
    return {
      timestamp: ts,
      hrv_ms: round(48 + seed() * 24 + Math.sin(i / 3) * 8, 1),
      reading_type: "overnight",
      rolling_baseline_ms: round(59 + seed() * 4, 1),
    };
  });
  return {
    date,
    session,
    biometrics: {
      resting_hr: 48 + Math.round(seed() * 4),
      hrv_ms: round(58 + seed() * 12, 0),
      spo2_avg: round(96.8 + seed() * 1.4, 1),
      respiration_avg: round(13 + seed() * 1.4, 1),
      skin_temp_c: round(32.4 + seed() * 0.6, 1),
    },
    hrv_readings,
    stages: { date, segments: segs, source: "Whoop" },
  };
}

/* --------------------------------------------------------------- metrics catalog */

export const metricCatalog: MetricCatalogItem[] = [
  { key: "hrv", label: "HRV (RMSSD)", unit: "ms", group: "recovery", source: "Whoop", description: "Heart Rate Variability — overnight autonomic recovery signal." },
  { key: "resting_hr", label: "Resting Heart Rate", unit: "bpm", group: "cardio", source: "Garmin", description: "Lowest 30-minute average overnight." },
  { key: "spo2", label: "SpO₂", unit: "%", group: "cardio", source: "Whoop", description: "Overnight blood oxygen saturation average." },
  { key: "respiration", label: "Respiration Rate", unit: "brpm", group: "cardio", source: "Whoop", description: "Overnight breathing rate." },
  { key: "skin_temp", label: "Skin Temperature Variance", unit: "°C", group: "body", source: "Whoop", description: "Deviation from baseline skin temperature." },
  { key: "weight", label: "Body Weight", unit: "kg", group: "body", source: "Garmin", description: "Morning body weight." },
  { key: "vo2max", label: "VO₂max (Est.)", unit: "ml/kg/min", group: "performance", source: "Garmin", description: "Estimated maximal oxygen uptake." },
  { key: "readiness", label: "Readiness Score", unit: "/100", group: "recovery", source: "Calculated", description: "Composite readiness from recovery + strain + sleep." },
  { key: "acwr", label: "ACWR", unit: "ratio", group: "performance", source: "Calculated", description: "Acute-to-chronic workload ratio (7d / 28d)." },
  { key: "sleep_score", label: "Sleep Score", unit: "/100", group: "sleep", source: "Whoop", description: "Composite sleep quality score." },
  { key: "sleep_efficiency", label: "Sleep Efficiency", unit: "%", group: "sleep", source: "Whoop", description: "Time asleep / time in bed." },
  { key: "deep_sleep", label: "Deep Sleep", unit: "h", group: "sleep", source: "Whoop", description: "Total deep sleep per night." },
  { key: "rem_sleep", label: "REM Sleep", unit: "h", group: "sleep", source: "Whoop", description: "Total REM sleep per night." },
  { key: "hrv_norm", label: "HRV 30d Norm", unit: "ms", group: "recovery", source: "Calculated", description: "30-day rolling normalized HRV." },
  { key: "total_sleep", label: "Total Sleep", unit: "h", group: "sleep", source: "Whoop", description: "Total sleep per night." },
];

export function getMetricTrend(key: string, days = 30): MetricTrend {
  const meta = metricCatalog.find((m) => m.key === key) ?? metricCatalog[0];
  const seed = mulberry32(key.length * 17 + days);
  const points: { date: string; value: number | null }[] = [];
  let v: number;
  switch (key) {
    case "hrv": v = 58; break;
    case "resting_hr": v = 50; break;
    case "spo2": v = 97; break;
    case "respiration": v = 13.4; break;
    case "skin_temp": v = 32.5; break;
    case "weight": v = 74.5; break;
    case "vo2max": v = 57.8; break;
    case "readiness": v = 78; break;
    case "acwr": v = 1.05; break;
    case "sleep_score": v = 82; break;
    case "sleep_efficiency": v = 92; break;
    case "deep_sleep": v = 1.5; break;
    case "rem_sleep": v = 1.8; break;
    case "hrv_norm": v = 60; break;
    case "total_sleep": v = 7.4; break;
    default: v = 50;
  }
  const range = key === "hrv" ? 14 : key === "resting_hr" ? 6 : key === "weight" ? 1.2 : key === "acwr" ? 0.3 : 8;
  for (let i = days - 1; i >= 0; i--) {
    const drift = Math.sin((days - i) / 7) * (range * 0.4);
    const noise = (seed() - 0.5) * (range * 0.3);
    const val = round(clamp(v + drift + noise, v - range, v + range), key === "weight" || key === "acwr" || key === "skin_temp" || key === "respiration" ? 2 : key === "spo2" || key === "sleep_efficiency" ? 1 : 0);
    points.push({ date: localDate(i), value: seed() > 0.96 ? null : val });
  }
  const values = points.map((p) => p.value).filter((x): x is number => x !== null);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const last = points.at(-1)?.value ?? null;
  const sevenAgo = points.at(-8)?.value ?? null;
  const twentyEightAgo = points.at(-29)?.value ?? points[0]?.value ?? null;
  return {
    metric: key,
    label: meta.label,
    unit: meta.unit,
    group: meta.group,
    start_date: points[0].date,
    end_date: points.at(-1)!.date,
    points,
    stats: {
      mean: round(mean, 2),
      min: round(min, 2),
      max: round(max, 2),
      last: last === null ? null : round(last, 2),
      baseline: round(mean, 2),
      delta_7d: sevenAgo === null || last === null ? null : round(last - sevenAgo, 2),
      delta_28d: twentyEightAgo === null || last === null ? null : round(last - twentyEightAgo, 2),
    },
  };
}

/* --------------------------------------------------------------- labs */

export const labMarkers: LabMarker[] = [
  { key: "hdl", label: "HDL Cholesterol", unit: "mg/dL", value: 58, ref_low: 40, ref_high: 60, status: "normal", date: localDate(14) },
  { key: "ldl", label: "LDL Cholesterol", unit: "mg/dL", value: 112, ref_low: 0, ref_high: 130, status: "normal", date: localDate(14) },
  { key: "triglycerides", label: "Triglycerides", unit: "mg/dL", value: 74, ref_low: 0, ref_high: 150, status: "normal", date: localDate(14) },
  { key: "glucose", label: "Fasting Glucose", unit: "mg/dL", value: 88, ref_low: 70, ref_high: 99, status: "normal", date: localDate(14) },
  { key: "hba1c", label: "HbA1c", unit: "%", value: 5.1, ref_low: 4.0, ref_high: 5.6, status: "normal", date: localDate(14) },
  { key: "ferritin", label: "Ferritin", unit: "ng/mL", value: 42, ref_low: 30, ref_high: 400, status: "normal", date: localDate(14) },
  { key: "vit_d", label: "Vitamin D", unit: "ng/mL", value: 28, ref_low: 30, ref_high: 100, status: "low", date: localDate(14) },
  { key: "crp", label: "hs-CRP", unit: "mg/L", value: 0.4, ref_low: 0, ref_high: 1.0, status: "normal", date: localDate(14) },
  { key: "tsh", label: "TSH", unit: "mIU/L", value: 1.8, ref_low: 0.4, ref_high: 4.0, status: "normal", date: localDate(14) },
  { key: "creatinine", label: "Creatinine", unit: "mg/dL", value: 1.02, ref_low: 0.7, ref_high: 1.3, status: "normal", date: localDate(14) },
];

/* --------------------------------------------------------------- training */

export function getTrainingSchedule(daysAhead = 14, daysBack = 7): TrainingPlanItem[] {
  const items: TrainingPlanItem[] = [];
  for (let i = -daysBack; i <= daysAhead; i++) {
    const seed = mulberry32(i + 31);
    const dow = new Date(localDate(i)).getDay();
    if (seed() < 0.18) {
      items.push({
        id: 1000 + i,
        date: localDate(i),
        type: "rest",
        title: "Recovery Day",
        discipline: "rest",
        duration_min: null,
        intensity: "recovery",
        status: i < 0 ? "done" : "planned",
        note: "Active recovery — light walk, mobility, sleep prioritised.",
      });
      continue;
    }
    const templates: Array<Partial<TrainingPlanItem> & { discipline: TrainingPlanItem["discipline"]; title: string }> = [
      { discipline: "cycling", title: "Endurance Ride · Zone 2", duration_min: 120, intensity: "easy" },
      { discipline: "cycling", title: "Threshold Intervals · 4×8min", duration_min: 90, intensity: "threshold" },
      { discipline: "running", title: "Long Run · Aerobic", duration_min: 75, intensity: "easy" },
      { discipline: "strength", title: "Lower Body · Squat Focus", duration_min: 60, intensity: "hard" },
      { discipline: "strength", title: "Upper Body · Push Pull", duration_min: 55, intensity: "hard" },
      { discipline: "cycling", title: "Sweet Spot · 3×20min", duration_min: 105, intensity: "moderate" },
      { discipline: "running", title: "VO2max · 5×3min", duration_min: 55, intensity: "hard" },
    ];
    const tmpl = templates[Math.floor(seed() * templates.length)];
    const isConfirmed = seed() > 0.55 && i >= 0;
    const status: TrainingPlanItem["status"] =
      i < 0 ? "done" : isConfirmed ? "confirmed" : "planned";
    items.push({
      id: 1000 + i,
      date: localDate(i),
      type: dow === 0 ? "race" : "session",
      title: tmpl.title,
      discipline: tmpl.discipline,
      duration_min: tmpl.duration_min ?? null,
      intensity: tmpl.intensity ?? null,
      status,
      note: isConfirmed ? "Confirmed by coach — overlaid on recurring template." : "Recurring weekly template.",
    });
  }
  return items;
}

/* --------------------------------------------------------------- gym sessions */

export const gymSessions: GymSession[] = [
  {
    id: 1,
    date: localDate(0),
    title: "Lower Body · Squat Focus",
    status: "planned",
    exercises: [
      { id: 1, name: "Back Squat", muscle_group: "Quads", sets: 4, reps: "5", weight_kg: 130, rest_s: 180, notes: "RPE 8, focus on depth" },
      { id: 2, name: "Romanian Deadlift", muscle_group: "Hamstrings", sets: 3, reps: "8", weight_kg: 100, rest_s: 120, notes: null },
      { id: 3, name: "Walking Lunges", muscle_group: "Quads / Glutes", sets: 3, reps: "12/leg", weight_kg: 24, rest_s: 90, notes: "Dumbbell" },
      { id: 4, name: "Leg Curl", muscle_group: "Hamstrings", sets: 3, reps: "10", weight_kg: 50, rest_s: 90, notes: null },
      { id: 5, name: "Calf Raise", muscle_group: "Calves", sets: 4, reps: "15", weight_kg: 80, rest_s: 60, notes: null },
    ],
  },
  {
    id: 2,
    date: localDate(1),
    title: "Upper Body · Push",
    status: "done",
    exercises: [
      { id: 1, name: "Bench Press", muscle_group: "Chest", sets: 4, reps: "5", weight_kg: 90, rest_s: 180, notes: "PR attempt next week" },
      { id: 2, name: "Overhead Press", muscle_group: "Shoulders", sets: 4, reps: "6", weight_kg: 55, rest_s: 120, notes: null },
      { id: 3, name: "Incline Dumbbell Press", muscle_group: "Chest", sets: 3, reps: "10", weight_kg: 32, rest_s: 90, notes: null },
      { id: 4, name: "Triceps Pushdown", muscle_group: "Triceps", sets: 3, reps: "12", weight_kg: 35, rest_s: 60, notes: null },
    ],
  },
];

/* --------------------------------------------------------------- coach chats */

export const chatSessions: ChatSession[] = [
  {
    id: 101,
    title: "Recovery after hard weekend",
    started_at: dateOffset(2, 9, 12),
    last_activity_at: dateOffset(2, 9, 24),
    message_count: 6,
    preview: "Your HRV is 7% above your 28-day baseline, which suggests parasympathetic recovery is strong.",
  },
  {
    id: 100,
    title: "VO2max plateau analysis",
    started_at: dateOffset(5, 21, 4),
    last_activity_at: dateOffset(4, 7, 18),
    message_count: 8,
    preview: "VO2max estimate has been stable at 58.4 for 4 weeks. Three factors are likely at play.",
  },
  {
    id: 99,
    title: "Sleep consistency review",
    started_at: dateOffset(9, 20, 0),
    last_activity_at: dateOffset(8, 8, 0),
    message_count: 4,
    preview: "Bedtime variance dropped from 47 to 18 minutes over the last 14 days.",
  },
];

export function getChatSession(id: number): ChatSessionDetail {
  const sess = chatSessions.find((s) => s.id === id) ?? chatSessions[0];
  return {
    ...sess,
    messages:
      id === 101
        ? [
            { id: 1, role: "user", content: "My recovery feels off after the weekend. What does the data say?", referenced_data: null, created_at: dateOffset(2, 9, 12), kind: "data" },
            { id: 2, role: "assistant", content: "Your HRV is 7% above your 28-day baseline (64 vs 59 ms mean), and resting HR dropped 2 bpm. Sleep efficiency is at 94% over the last 3 nights. These signals suggest parasympathetic recovery is strong — the subjective 'off' feeling is unlikely to be physiological under-recovery.", referenced_data: { hrv_ms: 64, hrv_baseline: 59, resting_hr: 48 }, created_at: dateOffset(2, 9, 14), kind: "data" },
            { id: 3, role: "user", content: "Should I train hard today?", referenced_data: null, created_at: dateOffset(2, 9, 18), kind: "data" },
            { id: 4, role: "assistant", content: "Your ACWR is 1.09 — inside the optimal training window but at the upper edge. Readiness 84/100 supports a quality session. Recommendation: a threshold-style bike interval session (4×8 min at FTP) is appropriate; avoid back-to-back high-load days.", referenced_data: { readiness: 84, acwr: 1.09 }, created_at: dateOffset(2, 9, 19), kind: "recommendation" },
            { id: 5, role: "assistant", content: "This is an interpretation of measured data, not medical advice. Stop and consult a clinician if you experience chest pain, unusual shortness of breath, or persistent fatigue.", referenced_data: null, created_at: dateOffset(2, 9, 19), kind: "disclaimer" },
            { id: 6, role: "user", content: "Got it, thank you.", referenced_data: null, created_at: dateOffset(2, 9, 24), kind: "data" },
          ]
        : id === 100
          ? [
              { id: 1, role: "user", content: "Why has my VO2max plateaued?", referenced_data: null, created_at: dateOffset(5, 21, 4), kind: "data" },
              { id: 2, role: "assistant", content: "VO2max estimate has been stable at 58.4 ml/kg/min for 4 weeks. Three factors are likely involved: (1) most of your recent rides are Zone 2 / endurance, which doesn't strongly drive VO2max adaptation; (2) the last true VO2max-style session was 12 days ago; (3) your weight is stable, so the estimate is mostly driven by HR response, not body-mass change.", referenced_data: { vo2max: 58.4, weight_kg: 74.2 }, created_at: dateOffset(5, 21, 10), kind: "data" },
              { id: 3, role: "assistant", content: "To break the plateau, include one dedicated VO2max session per week (e.g. 5×3 min at 106% FTP, 3 min recovery). Track the HR response — a faster HR recovery between intervals is the most reliable leading indicator of aerobic adaptation.", referenced_data: null, created_at: dateOffset(5, 21, 12), kind: "recommendation" },
              { id: 4, role: "assistant", content: "VO2max estimates from wrist-based optical sensors carry a typical ±3-5 ml/kg/min uncertainty. Treat the absolute number with skepticism; the trend direction is more meaningful than the level.", referenced_data: null, created_at: dateOffset(5, 21, 12), kind: "disclaimer" },
            ]
          : [
              { id: 1, role: "user", content: "How has my sleep consistency been?", referenced_data: null, created_at: dateOffset(9, 20, 0), kind: "data" },
              { id: 2, role: "assistant", content: "Bedtime variance dropped from 47 to 18 minutes over the last 14 days. Sleep score averages 85, up from 78 in the prior fortnight. Deep sleep is 1.5h average, REM 1.8h — both within healthy ranges.", referenced_data: { sleep_score_avg: 85, bedtime_variance_min: 18 }, created_at: dateOffset(9, 20, 4), kind: "data" },
              { id: 3, role: "assistant", content: "Maintain the current sleep window — the consistency, more than the absolute hours, is what is driving the score improvement.", referenced_data: null, created_at: dateOffset(9, 20, 6), kind: "recommendation" },
            ],
  };
}

/* --------------------------------------------------------------- challenges */

export const challenges: Challenge[] = [
  {
    id: 1,
    title: "October Distance — Cycling",
    metric: "Total Distance",
    unit: "km",
    my_value: 624,
    leader_value: 781,
    my_rank: 4,
    total_participants: 32,
    ends_at: dateOffset(-18, 23, 59),
  },
  {
    id: 2,
    title: "Vertical Climb Challenge",
    metric: "Total Elevation",
    unit: "m",
    my_value: 4820,
    leader_value: 6310,
    my_rank: 7,
    total_participants: 58,
    ends_at: dateOffset(-12, 23, 59),
  },
  {
    id: 3,
    title: "Recovery Score Streak",
    metric: "Days above 75",
    unit: "days",
    my_value: 14,
    leader_value: 22,
    my_rank: 11,
    total_participants: 124,
    ends_at: dateOffset(-5, 23, 59),
  },
];

/* --------------------------------------------------------------- helpers */

export function findActivity(id: number): ActivityCard | undefined {
  return activities.find((a) => a.id === id);
}
