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
  readiness: { value: 64, delta_7d: 3 },
  recovery: { value: 67, delta_7d: 4 },
  strain: { value: 35, delta_7d: -12 },
  sleep_score: { value: 64, delta_7d: 3 },
  sleep_hours: 7.48,
  hrv_ms: 42,
  hrv_baseline_ms: 45,
  hrv_norm_30d: 48,
  resting_hr: 60,
  resting_hr_delta_7d: 2,
  spo2_avg: 96.8,
  spo2_delta_7d: 0.1,
  respiration_avg: 14.2,
  steps: 35,
  weight_kg: 74.2,
  vo2max: null,
  acute_load: 180,
  chronic_load: 220,
  acwr: 0.82,
  training_load_7d: 180,
  activities: [
    {
      id: 24505012960,
      start_time: "2026-09-26T10:59:22",
      local_date: "2026-09-26",
      discipline: "cycling",
      title: "Travo eMountain Biking",
      duration_s: 13523,
      distance_m: 66050,
      elevation_gain_m: 2333,
      avg_hr: 113,
      max_hr: 162,
      avg_power: null,
      np_power: null,
      avg_speed_mps: 4.88,
      calories: 986,
      training_load: null,
      data_completeness: "complete",
      sources: ["Garmin"],
    },
  ],
  sleep: {
    start_time: "2026-09-29T21:53:00Z",
    end_time: "2026-09-30T06:03:00Z",
    total_sleep_s: 26940,
    sleep_score: 64,
    stages: { deep_s: 2880, light_s: 17400, rem_s: 6660, awake_s: 2460 },
    respiration_avg: null,
    spo2_avg: null,
    restlessness: null,
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

// Real activities fetched from Garmin Connect (account: [REDACTED])
// 30 activities spanning Jul–Sep 2026, including mountain biking, sailing,
// open water swimming, hiking, and boating on Lake Como / La Maddalena.
export const activities: ActivityCard[] = [
  { id: 24505012960, start_time: "2026-09-26T10:59:22", local_date: "2026-09-26", discipline: "cycling", title: "Travo eMountain Biking", duration_s: 13523, distance_m: 66050, elevation_gain_m: 2333, avg_hr: 113, max_hr: 162, avg_power: null, np_power: null, avg_speed_mps: 4.88, calories: 986, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24433776396, start_time: "2026-09-20T12:53:36", local_date: "2026-09-20", discipline: "rowing", title: "Gravedona ed Uniti Barca", duration_s: 13929, distance_m: 29118, elevation_gain_m: 50, avg_hr: 97, max_hr: 124, avg_power: null, np_power: null, avg_speed_mps: 2.09, calories: null, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24422820122, start_time: "2026-09-19T13:01:46", local_date: "2026-09-19", discipline: "rowing", title: "Gravedona ed Uniti Barca", duration_s: 20222, distance_m: 39950, elevation_gain_m: 80, avg_hr: 93, max_hr: 131, avg_power: null, np_power: null, avg_speed_mps: 1.98, calories: null, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24347545480, start_time: "2026-09-13T12:52:21", local_date: "2026-09-13", discipline: "rowing", title: "Gravedona ed Uniti Barca", duration_s: 11159, distance_m: 24399, elevation_gain_m: 43, avg_hr: 103, max_hr: 133, avg_power: null, np_power: null, avg_speed_mps: 2.19, calories: null, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24335442417, start_time: "2026-09-12T13:25:51", local_date: "2026-09-12", discipline: "rowing", title: "Gravedona ed Uniti Barca", duration_s: 11436, distance_m: 22222, elevation_gain_m: 151, avg_hr: 111, max_hr: 137, avg_power: null, np_power: null, avg_speed_mps: 1.94, calories: null, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24215710935, start_time: "2026-09-02T16:52:47", local_date: "2026-09-02", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 14584, distance_m: 41483, elevation_gain_m: null, avg_hr: 74, max_hr: 151, avg_power: null, np_power: null, avg_speed_mps: 2.84, calories: 424, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24205585888, start_time: "2026-09-02T07:20:05", local_date: "2026-09-02", discipline: "swimming", title: "La Maddalena Nuoto in acque libere", duration_s: 892, distance_m: 376, elevation_gain_m: null, avg_hr: 146, max_hr: 181, avg_power: null, np_power: null, avg_speed_mps: 0.42, calories: 153, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24149802595, start_time: "2026-08-28T13:53:20", local_date: "2026-08-28", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 4872, distance_m: 11838, elevation_gain_m: null, avg_hr: 125, max_hr: 166, avg_power: null, np_power: null, avg_speed_mps: 2.43, calories: 495, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24146299897, start_time: "2026-08-28T10:38:44", local_date: "2026-08-28", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 4689, distance_m: 7907, elevation_gain_m: null, avg_hr: 92, max_hr: 141, avg_power: null, np_power: null, avg_speed_mps: 1.69, calories: 239, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24138520501, start_time: "2026-08-27T14:59:54", local_date: "2026-08-27", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 4528, distance_m: 10971, elevation_gain_m: null, avg_hr: 124, max_hr: 167, avg_power: null, np_power: null, avg_speed_mps: 2.42, calories: 422, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24134684319, start_time: "2026-08-27T10:43:06", local_date: "2026-08-27", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 6770, distance_m: 9397, elevation_gain_m: null, avg_hr: 91, max_hr: 143, avg_power: null, np_power: null, avg_speed_mps: 1.39, calories: 332, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24125434774, start_time: "2026-08-26T14:31:57", local_date: "2026-08-26", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 9933, distance_m: 22084, elevation_gain_m: null, avg_hr: 95, max_hr: 146, avg_power: null, np_power: null, avg_speed_mps: 2.22, calories: 531, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24121568727, start_time: "2026-08-26T10:14:05", local_date: "2026-08-26", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 6854, distance_m: 12740, elevation_gain_m: null, avg_hr: 90, max_hr: 131, avg_power: null, np_power: null, avg_speed_mps: 1.86, calories: 325, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24112479007, start_time: "2026-08-25T15:32:56", local_date: "2026-08-25", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 2835, distance_m: 7267, elevation_gain_m: null, avg_hr: 125, max_hr: 173, avg_power: null, np_power: null, avg_speed_mps: 2.56, calories: 298, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24109698388, start_time: "2026-08-25T10:44:26", local_date: "2026-08-25", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 3727, distance_m: 5783, elevation_gain_m: null, avg_hr: 119, max_hr: 159, avg_power: null, np_power: null, avg_speed_mps: 1.55, calories: 352, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24098561005, start_time: "2026-08-24T15:04:28", local_date: "2026-08-24", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 6595, distance_m: 17367, elevation_gain_m: null, avg_hr: 104, max_hr: 157, avg_power: null, np_power: null, avg_speed_mps: 2.63, calories: 430, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24095376062, start_time: "2026-08-24T10:11:25", local_date: "2026-08-24", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 8180, distance_m: 20493, elevation_gain_m: null, avg_hr: 101, max_hr: 143, avg_power: null, np_power: null, avg_speed_mps: 2.51, calories: 502, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24088283831, start_time: "2026-08-23T15:15:18", local_date: "2026-08-23", discipline: "rowing", title: "Navigazione a vela", duration_s: 10190, distance_m: 24293, elevation_gain_m: null, avg_hr: 115, max_hr: 164, avg_power: null, np_power: null, avg_speed_mps: 2.38, calories: 787, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24083899248, start_time: "2026-08-23T10:43:03", local_date: "2026-08-23", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 8319, distance_m: 18782, elevation_gain_m: null, avg_hr: 94, max_hr: 136, avg_power: null, np_power: null, avg_speed_mps: 2.26, calories: 444, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24075764175, start_time: "2026-08-22T17:41:51", local_date: "2026-08-22", discipline: "rowing", title: "La Maddalena Navigazione a vela", duration_s: 845, distance_m: 1866, elevation_gain_m: null, avg_hr: 91, max_hr: 128, avg_power: null, np_power: null, avg_speed_mps: 2.21, calories: 46, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24037042138, start_time: "2026-08-19T10:47:59", local_date: "2026-08-19", discipline: "hiking", title: "Peio Escursionismo", duration_s: 13208, distance_m: 19017, elevation_gain_m: 1312, avg_hr: 147, max_hr: 195, avg_power: null, np_power: null, avg_speed_mps: 1.44, calories: 1711, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24023504056, start_time: "2026-08-18T14:04:14", local_date: "2026-08-18", discipline: "cycling", title: "Commezzadura Mountain bike", duration_s: 7423, distance_m: 31129, elevation_gain_m: 2825, avg_hr: 112, max_hr: 172, avg_power: null, np_power: null, avg_speed_mps: 4.19, calories: 581, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 24010349394, start_time: "2026-08-17T08:56:28", local_date: "2026-08-17", discipline: "hiking", title: "Commezzadura Escursionismo", duration_s: 16008, distance_m: 20222, elevation_gain_m: 1329, avg_hr: 153, max_hr: 199, avg_power: null, np_power: null, avg_speed_mps: 1.26, calories: 2271, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23998395298, start_time: "2026-08-16T11:44:57", local_date: "2026-08-16", discipline: "hiking", title: "Pellizzano Escursionismo", duration_s: 5997, distance_m: 6408, elevation_gain_m: 345, avg_hr: 126, max_hr: 177, avg_power: null, np_power: null, avg_speed_mps: 1.07, calories: 629, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23995891204, start_time: "2026-08-16T10:59:14", local_date: "2026-08-16", discipline: "cycling", title: "Mezzana Escursionismo", duration_s: 1720, distance_m: 3363, elevation_gain_m: 274, avg_hr: 173, max_hr: 205, avg_power: null, np_power: null, avg_speed_mps: 1.96, calories: 350, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23975993736, start_time: "2026-08-14T08:59:32", local_date: "2026-08-14", discipline: "hiking", title: "Mezzana Escursionismo", duration_s: 15899, distance_m: 20063, elevation_gain_m: 1517, avg_hr: 156, max_hr: 195, avg_power: null, np_power: null, avg_speed_mps: 1.26, calories: 2451, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23874722355, start_time: "2026-08-06T16:23:02", local_date: "2026-08-06", discipline: "cycling", title: "Mahawt Quad", duration_s: 2021, distance_m: 17654, elevation_gain_m: 46, avg_hr: 65, max_hr: 97, avg_power: null, np_power: null, avg_speed_mps: 8.73, calories: 64, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23874721694, start_time: "2026-08-06T12:28:03", local_date: "2026-08-06", discipline: "cycling", title: "Mahawt Quad", duration_s: 1827, distance_m: 16930, elevation_gain_m: 102, avg_hr: 60, max_hr: 74, avg_power: null, np_power: null, avg_speed_mps: 9.27, calories: 33, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23845543059, start_time: "2026-08-04T08:58:58", local_date: "2026-08-04", discipline: "hiking", title: "Al Hamra Escursionismo", duration_s: 8759, distance_m: 8008, elevation_gain_m: 318, avg_hr: 108, max_hr: 168, avg_power: null, np_power: null, avg_speed_mps: 0.91, calories: 648, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
  { id: 23750560959, start_time: "2026-07-27T13:58:01", local_date: "2026-07-27", discipline: "cycling", title: "Ciclismo indoor", duration_s: 7245, distance_m: null, elevation_gain_m: null, avg_hr: 150, max_hr: 164, avg_power: null, np_power: null, avg_speed_mps: null, calories: 1085, training_load: null, data_completeness: "complete", sources: ["Garmin"] },
];

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

// Real sleep sessions fetched from Garmin Connect (account: [REDACTED])
// 13 nights spanning Sep 17–30, 2026. Sleep scores computed from deep+rem ratio
// and total duration (Garmin's own sleep score was not available in the API response).
export const sleepSessions: SleepSession[] = [
  { local_date: "2026-09-30", start_time: "2026-09-29T21:53:00Z", end_time: "2026-09-30T06:03:00Z", total_sleep_s: 26940, deep_s: 2880, light_s: 17400, rem_s: 6660, awake_s: 2460, sleep_score: 64, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-29", start_time: "2026-09-28T21:52:00Z", end_time: "2026-09-29T04:57:00Z", total_sleep_s: 22260, deep_s: 6900, light_s: 12240, rem_s: 3120, awake_s: 3240, sleep_score: 61, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-28", start_time: "2026-09-27T20:19:00Z", end_time: "2026-09-28T04:53:00Z", total_sleep_s: 29400, deep_s: 6720, light_s: 13560, rem_s: 9120, awake_s: 1440, sleep_score: 76, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-27", start_time: "2026-09-26T23:00:00Z", end_time: "2026-09-27T05:16:00Z", total_sleep_s: 22500, deep_s: 7260, light_s: 11700, rem_s: 3540, awake_s: 60, sleep_score: 63, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-26", start_time: "2026-09-25T21:43:00Z", end_time: "2026-09-26T05:51:00Z", total_sleep_s: 28440, deep_s: 3120, light_s: 17940, rem_s: 7380, awake_s: 840, sleep_score: 67, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-25", start_time: "2026-09-25T00:58:00Z", end_time: "2026-09-25T04:01:00Z", total_sleep_s: 10920, deep_s: 2820, light_s: 6600, rem_s: 1500, awake_s: 60, sleep_score: 38, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-24", start_time: "2026-09-23T22:25:00Z", end_time: "2026-09-24T05:11:00Z", total_sleep_s: 24240, deep_s: 5100, light_s: 15300, rem_s: 3840, awake_s: 120, sleep_score: 60, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-23", start_time: "2026-09-22T22:32:00Z", end_time: "2026-09-23T05:10:00Z", total_sleep_s: 23580, deep_s: 5340, light_s: 13320, rem_s: 4920, awake_s: 300, sleep_score: 62, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-22", start_time: "2026-09-21T22:18:00Z", end_time: "2026-09-22T05:00:00Z", total_sleep_s: 24120, deep_s: 7860, light_s: 9540, rem_s: 6720, awake_s: 0, sleep_score: 72, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-21", start_time: "2026-09-20T21:25:00Z", end_time: "2026-09-21T05:02:00Z", total_sleep_s: 26160, deep_s: 5760, light_s: 14160, rem_s: 6240, awake_s: 1260, sleep_score: 68, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-20", start_time: "2026-09-19T21:47:00Z", end_time: "2026-09-20T06:03:00Z", total_sleep_s: 29760, deep_s: 6780, light_s: 14760, rem_s: 8220, awake_s: 0, sleep_score: 75, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-18", start_time: "2026-09-17T22:04:00Z", end_time: "2026-09-18T05:31:00Z", total_sleep_s: 26580, deep_s: 4620, light_s: 17760, rem_s: 4200, awake_s: 240, sleep_score: 62, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
  { local_date: "2026-09-17", start_time: "2026-09-16T21:45:00Z", end_time: "2026-09-17T05:01:00Z", total_sleep_s: 25020, deep_s: 6420, light_s: 14040, rem_s: 4560, awake_s: 0, sleep_score: 65, respiration_avg: null, spo2_avg: null, restlessness: null, sources: ["Garmin"] },
];

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
