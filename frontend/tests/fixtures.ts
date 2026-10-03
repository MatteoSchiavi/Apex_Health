import type { Page } from "@playwright/test";
// Synthetic records exist only in browser tests. Production always uses the API.
export const today = new Date().toISOString().slice(0, 10);
export const keys = [
  "readiness",
  "recovery",
  "strain",
  "sleep_score",
  "acwr",
  "acute_load",
  "chronic_load",
  "hrv_deviation",
  "illness_risk",
  "injury_risk",
  "resting_hr",
  "weight",
  "body_fat",
  "vo2max",
  "steps",
  "floors",
  "spo2",
  "hydration",
  "sleep_duration",
  "sleep_deep",
  "sleep_rem",
  "sleep_light",
  "respiration",
  "restlessness",
];
const units: Record<string, string> = {
  readiness: "/100",
  recovery: "/100",
  strain: "/100",
  sleep_score: "/100",
  acwr: "ratio",
  acute_load: "TSS/d",
  chronic_load: "TSS/d",
  hrv_deviation: "%",
  illness_risk: "/100",
  injury_risk: "/100",
  resting_hr: "bpm",
  weight: "kg",
  body_fat: "%",
  vo2max: "ml/kg/min",
  steps: "steps",
  floors: "floors",
  spo2: "%",
  hydration: "ml",
  sleep_duration: "h",
  sleep_deep: "h",
  sleep_rem: "h",
  sleep_light: "h",
  respiration: "br/min",
  restlessness: "%",
};
export const catalog = Object.fromEntries(
  keys.map((key) => [key, { unit: units[key], direction: "band" }]),
);
export const account = {
  user_id: 1,
  email: "athlete@example.com",
  name: "Alex Morgan",
  dob: null,
  sex: null,
  height_cm: null,
  timezone: "UTC",
  locale: "en",
  theme: "light",
  units: "metric",
  role: "owner",
  ai_access_tier: "medical",
  main_integration_id: 1,
};
export const activity = {
  id: 1,
  start_time: today + "T08:00:00Z",
  local_date: today,
  discipline: "road_cycling",
  duration_s: 5400,
  distance_m: 42195,
  elevation_gain_m: 480,
  avg_hr: 142,
  max_hr: 176,
  avg_power: 210,
  np_power: null,
  calories: 850,
  training_load: 82,
  data_completeness: "full",
  sources: ["garmin"],
  has_streams: true,
  stream_types: ["hr", "power"],
  laps: [
    {
      lap_index: 1,
      start_time: today + "T08:00:00Z",
      duration_s: 1200,
      distance_m: 10000,
      avg_hr: 142,
      max_hr: 168,
      avg_power: 220,
      calories: 190,
      extras: null,
    },
  ],
  weather: null,
  source_metrics: { garmin: { aerobic_effect: 3.4, anaerobic_effect: 1.2 } },
  gear: [{ id: 1, name: "Road bike", type: "bike" }],
};
export const night = {
  local_date: today,
  start_time: today + "T00:00:00Z",
  end_time: today + "T08:00:00Z",
  total_sleep_s: 27000,
  deep_s: 5100,
  light_s: 14700,
  rem_s: 7200,
  awake_s: 1800,
  sleep_score: 84,
  respiration_avg: 14.2,
  spo2_avg: 97.6,
  restlessness: 4,
  sources: ["garmin"],
};
export const overview = {
  date: today,
  anchor_is_today: true,
  readiness: { value: 82, delta_7d: 4 },
  recovery: { value: 78, delta_7d: 2 },
  strain: { value: 42, delta_7d: 5 },
  sleep_score: { value: 84, delta_7d: 3 },
  sleep_hours: 7.5,
  hrv_ms: 64,
  hrv_baseline_ms: 60,
  hrv_norm_30d: 62,
  resting_hr: 52,
  resting_hr_delta_7d: -2,
  spo2_avg: 97.6,
  spo2_delta_7d: 0.2,
  respiration_avg: 14.2,
  steps: 8640,
  weight_kg: 72.5,
  vo2max: 52.4,
  acute_load: 62,
  chronic_load: 58,
  acwr: 1.07,
  training_load_7d: 434,
  activities: [activity],
  sleep: {
    ...night,
    stages: {
      deep_s: night.deep_s,
      rem_s: night.rem_s,
      light_s: night.light_s,
      awake_s: night.awake_s,
    },
  },
  integration_status: [{ provider: "garmin", status: "active" }],
  alerts: [],
};
export async function installApi(
  page: Page,
  options: {
    empty?: boolean;
    fail?: string;
    theme?: "light" | "dark";
    locale?: "en" | "it";
    units?: "metric" | "imperial";
  } = {},
) {
  let me = {
    ...account,
    ...Object.fromEntries(
      Object.entries(options).filter(([k]) =>
        ["theme", "locale", "units"].includes(k),
      ),
    ),
  };
  let syncPolls = 0;
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/*", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname;
    if (
      !/^\/(me|auth|dashboard|activities|sleep|metrics|gym|events|coach|settings|challenges|rankings|labs)(\/|$)/.test(
        path,
      )
    )
      return route.continue();
    if (options.fail && path === options.fail)
      return route.fulfill({
        status: 503,
        json: { detail: "Service unavailable" },
      });
    let data: unknown;
    if (req.method() !== "GET") {
      const body = req.postDataJSON() ?? {};
      writes.push({ path, body });
      if (path === "/me") {
        me = { ...me, ...body };
        data = me;
      } else if (path === "/coach/chats")
        return route.fulfill({
          status: 502,
          json: {
            detail: "Coach is temporarily unavailable. Please try again.",
          },
        });
      else if (path === "/settings/integrations/garmin/sync")
        data = {
          enqueued: true,
          completed: false,
          job_id: "test-sync",
          status_url: "/settings/integrations/garmin/sync/test-sync",
        };
      else if (path === "/auth/login") data = { ok: true };
      else data = { ok: true };
    } else if (path === "/me") data = me;
    else if (path === "/settings/devices")
      data = options.empty
        ? []
        : [
            {
              integration_id: 1,
              provider: "garmin",
              status: "active",
              last_synced_at: today + "T06:00:00Z",
              is_main: true,
              connected_at: today + "T00:00:00Z",
            },
          ];
    else if (path === "/dashboard/overview")
      data = options.empty
        ? {
            ...overview,
            readiness: { value: null, delta_7d: null },
            recovery: { value: null, delta_7d: null },
            strain: { value: null, delta_7d: null },
            sleep_score: { value: null, delta_7d: null },
            sleep_hours: null,
            hrv_ms: null,
            resting_hr: null,
            steps: null,
            weight_kg: null,
            acute_load: null,
            activities: [],
            sleep: null,
          }
        : overview;
    else if (path === "/metrics") data = catalog;
    else if (path.startsWith("/metrics/")) {
      const key = path.split("/").at(-1)!;
      const end = url.searchParams.get("end") ?? today;
      const days = Number(url.searchParams.get("days") ?? 60);
      const values = Array.from({ length: Math.min(days, 14) }, (_, i) => {
        const date = new Date(end + "T12:00:00Z");
        date.setUTCDate(date.getUTCDate() - Math.min(days, 14) + 1 + i);
        return {
          date: date.toISOString().slice(0, 10),
          value:
            i === 5
              ? null
              : ((
                  {
                    weight: 72 + i / 20,
                    steps: 7200 + i * 70,
                    hydration: 2000 + i * 50,
                    resting_hr: 52 + Math.sin(i) * 2,
                    spo2: 97.6 + Math.sin(i) * 0.2,
                    respiration: 14.2 + Math.sin(i) * 0.4,
                    acwr: 1.07 + Math.sin(i) * 0.1,
                    body_fat: 15,
                    vo2max: 52.4,
                    floors: 6,
                    hrv_deviation: 6.7 + Math.sin(i) * 2,
                    sleep_duration: 7.5 + Math.sin(i) * 0.5,
                    sleep_deep: 1.4,
                    sleep_rem: 2,
                    sleep_light: 4.1,
                    restlessness: 4,
                    illness_risk: 12,
                    injury_risk: 15,
                    acute_load: 62 + Math.sin(i) * 10,
                    chronic_load: 58 + Math.sin(i) * 4,
                  } as Record<string, number>
                )[key] ?? 70 + Math.sin(i) * 10 + i),
        };
      });
      const valid = values.filter((p) => p.value != null).map((p) => p.value!);
      data = {
        metric: key,
        label: key,
        unit: catalog[key]?.unit ?? "/100",
        start_date: values[0].date,
        end_date: end,
        points: options.empty ? [] : values,
        stats: options.empty
          ? {}
          : {
              count: valid.length,
              min: Math.min(...valid),
              max: Math.max(...valid),
              mean: valid.reduce((a, b) => a + b, 0) / valid.length,
              latest: valid.at(-1),
              delta_30d: 2,
            },
      };
    } else if (path === "/activities") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      data = {
        items: options.empty
          ? []
          : offset
            ? [{ ...activity, id: 2, discipline: "running", distance_m: 5000 }]
            : [activity],
        total: options.empty ? 0 : 2,
        limit: 50,
        offset,
      };
    } else if (path === "/activities/1") data = activity;
    else if (path === "/activities/1/streams")
      data = {
        activity_id: 1,
        t: [0, 60, 120, 180, 240],
        columns: {
          hr: [100, 120, null, 140, 130],
          power: [100, 200, 250, 220, 210],
          speed: [6, 7, 8, 9, 7],
          lat: [],
          lon: [],
        },
      };
    else if (path === "/sleep")
      data = {
        items: options.empty ? [] : [night],
        start_date: today,
        end_date: today,
      };
    else if (path.endsWith("/stages"))
      data = { date: today, segments: null, source: "garmin" };
    else if (path.startsWith("/sleep/"))
      data = {
        date: today,
        session: options.empty ? null : night,
        biometrics: { resting_hr: 52 },
        hrv_readings: [
          {
            timestamp: today + "T02:00:00Z",
            hrv_ms: 62,
            rolling_baseline_ms: 60,
            reading_type: "overnight",
          },
          {
            timestamp: today + "T03:00:00Z",
            hrv_ms: 66,
            rolling_baseline_ms: 60,
            reading_type: "overnight",
          },
        ],
      };
    else if (path.startsWith("/gym/plan/"))
      data = { date: today, plan: null, template: null };
    else if (path === "/events") data = [];
    else if (path === "/coach/chats") data = [];
    else if (path.startsWith("/settings/integrations/garmin/sync/"))
      data =
        ++syncPolls < 2
          ? { state: "STARTED", completed: false }
          : { state: "SUCCESS", completed: true, result: { status: "ok" } };
    else if (
      ["/settings/invites", "/labs", "/challenges", "/rankings"].includes(path)
    )
      data = [];
    else return route.fulfill({ status: 404, json: { detail: "Not found" } });
    return route.fulfill({ status: 200, json: data });
  });
  return { writes };
}
