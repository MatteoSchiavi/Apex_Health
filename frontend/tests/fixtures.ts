import type { Page } from "@playwright/test";
// Synthetic records exist only in browser tests. Production always uses the API.
export const today = new Date().toISOString().slice(0, 10);
export const keys = [
  "readiness",
  "recovery",
  "strain",
  "sleep_score",
  "provider_sleep_score",
  "acwr",
  "acute_load",
  "chronic_load",
  "hrv_deviation",
  "hrv_ms",
  "systemic_stress",
  "load_spike",
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
  provider_sleep_score: "/100",
  acwr: "ratio",
  acute_load: "TSS/d",
  chronic_load: "TSS/d",
  hrv_deviation: "%",
  hrv_ms: "ms",
  systemic_stress: "/100",
  load_spike: "/100",
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
  ai_access_tier: "full",
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
    aiConsent?: boolean;
    empty?: boolean;
    fail?: string;
    theme?: "light" | "dark";
    locale?: "en" | "it";
    units?: "metric" | "imperial";
    role?: "owner" | "friend";
    sex?: "male" | "female" | "other" | null;
  } = {},
) {
  let me = {
    ...account,
    ...(options.role ? { role: options.role } : {}),
    ...Object.fromEntries(
      Object.entries(options).filter(([k]) =>
        ["theme", "locale", "units", "sex"].includes(k),
      ),
    ),
  };
  let athleteProfile = { training_focus: [] as string[], context: {} as Record<string, unknown>, revision: 0 };
  let aiConsent = options.aiConsent ?? true;
  const aiState = () => ({ effective_access: aiConsent ? "full" : "disabled", policy_version: "athlete-ai-consent-v1", provider_identity: "synthetic-browser-fixture", consent: { active: aiConsent, accepted_at: aiConsent ? today+"T00:00:00Z" : null, withdrawn_at: null }, budget: { used_tokens: 0, limit_tokens: 160000, exhausted: false, categories: { onboarding_extraction: { used_tokens: 0, limit_tokens: 40000 }, standard_chat: { used_tokens: 0, limit_tokens: 80000 }, strategic_coaching: { used_tokens: 0, limit_tokens: 100000 }, periodic_reports: { used_tokens: 0, limit_tokens: 80000 } } } });
  let syncPolls = 0;
  let labDrafts = options.empty
    ? []
    : [
        {
          id: 41,
          kind: "context_patch",
          status: "draft",
          before: {
            exists: true,
            doc_kind: "goals",
            content: "Finish the sailing season",
          },
          after: {
            exists: true,
            doc_kind: "goals",
            content: "Finish the sailing season\n\nPrepare for the regatta",
          },
          payload_hash: "a".repeat(64),
          snapshot_revision: "b".repeat(64),
          evidence_ids: ["observation:1:1"],
          reason: "Preserve the priority event goal",
          expires_at: new Date(Date.now() + 86400000).toISOString(),
          receipt: null as null | {
            state: string;
            external_delivery: string;
            undo_available: boolean;
          },
        },
      ];
  const labMetrics = [
    "hrv_overnight_rmssd",
    "resting_hr",
    "sleep_duration",
    "sleep_score",
  ].map((metric, i) => ({
    metric,
    unit: ["ms", "bpm", "h", "/100"][i],
    availability: options.empty ? "not_measured" : "available",
    sample_days_7d: options.empty ? 0 : 7,
    coverage_pct: options.empty ? 0 : 100,
    latest: options.empty
      ? null
      : {
          id: `observation:${i + 1}:1`,
          metric,
          value: [62, 52, 7.5, 84][i],
          unit: ["ms", "bpm", "h", "/100"][i],
          origin: "garmin",
          measured_at: today + "T06:00:00Z",
          local_date: today,
          fetched_at: today + "T07:00:00Z",
          revision: 1,
          availability: "available",
          acquisition: "unofficial_adapter",
          timezone: "Europe/Rome",
          quality_flags: [],
        },
  }));
  const labDecision = {
    id: 12,
    date: today,
    action: options.empty ? "collect_more_data" : "train_normally",
    reasons: [
      options.empty
        ? "Current measurements are missing."
        : "No conservative adjustment rule fired.",
    ],
    evidence: labMetrics.flatMap((m) => (m.latest ? [m.latest] : [])),
    data_completeness: {
      coverage_pct: options.empty ? 0 : 100,
      missing: options.empty ? ["hrv_overnight_rmssd"] : [],
    },
    confidence: options.empty ? "limited" : "supported_by_coverage",
    alternatives: [
      {
        action: "reduce_volume",
        reason: "Keep the planned focus with less volume.",
      },
    ],
    counterfactual:
      "A symptom note or new measurement can change the decision.",
    next_step: "Review a small session change.",
    formula_version: "daily-decision-v1",
    limitations: ["Planning rules are not a diagnosis."],
    outcome: null as null | { state: string },
  };
  let favoriteMetrics: string[] = [];
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/*", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname;
    if (
      !/^\/(me|auth|athlete|healthkit|schedule|legal\/config|dashboard|activities|sleep|metrics|gym|events|coach|settings|challenges|rankings|labs|lab|gear|imports|api\/admin|api\/feedback)(\/|$)/.test(
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
      const body = req.headers()["content-type"]?.includes("application/json")
        ? (req.postDataJSON() ?? {})
        : {};
      writes.push({ path, body });
      if (path === "/athlete/profile") { athleteProfile = req.method()==="DELETE" ? { training_focus: [], context: {}, revision: athleteProfile.revision+1 } : { training_focus: body.training_focus as string[], context: body.context as Record<string, unknown>, revision: athleteProfile.revision+1 }; data = athleteProfile; }
      else if (path === "/athlete/ai/consent") { aiConsent = Boolean(body.active); data = aiState(); }
      else if (path.startsWith("/athlete/")) data = { ...body, id: 1, revision: 1 };
      else if (path === "/lab/entries" && (body.entry as { kind?: string })?.kind === "metric_favorites") {
        favoriteMetrics = (body.entry as { metrics: string[] }).metrics; data = { id: 1 };
      } else if (path.match(/^\/lab\/changes\/41\/(approve|undo|reject)$/)) {
        const action = path.split("/").at(-1);
        labDrafts = labDrafts.map((d) => ({
          ...d,
          status:
            action === "approve"
              ? "applied_locally"
              : action === "undo"
                ? "undone"
                : "rejected",
          receipt:
            action === "reject"
              ? null
              : {
                  state: action === "approve" ? "applied_locally" : "undone",
                  external_delivery: "not_requested",
                  undo_available: action === "approve",
                },
        }));
        data = labDrafts[0];
      } else if (path === "/lab/decision/12/outcome") {
        labDecision.outcome = { state: body.state };
        data = labDecision;
      } else if (path === "/lab/replan") data = { state: "no_change" };
      else if (path === "/lab/analytics")
        data = {
          handle: "analysis:21",
          recipe: body.recipe,
          formula_version: "median-mad-v1",
          data: {
            state: "available",
            sample_count: 24,
            median: 62,
            mad: 3,
            unit: "ms",
            missing_days: 4,
            empirical_range: [57, 67],
            evidence_ids: ["observation:1:1"],
          },
        };
      else if (path === "/me") {
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
      else if (path === "/api/feedback") {
        await new Promise((resolve) => setTimeout(resolve, 150));
        data = { id: 91, created_at: today + "T12:00:00Z", notification_status: "pending" };
      }
      else data = { ok: true };
    } else if (path === "/healthkit/devices") data = [];
    else if (path === "/schedule/calendar") data = { sessions: [] };
    else if (path === "/legal/config") data = {};
    else if (path === "/athlete/profile") data = athleteProfile;
    else if (path === "/athlete/ai") data = aiState();
    else if (path === "/athlete/life-events" || path === "/lab/plan-drafts") data = [];
    else if (path === "/athlete/disciplines") data = ["running", "road_cycling", "strength", "sailing", "skiing", "enduro", "hiit"].map(name => ({ name, category: "endurance" }));
    else if (path === "/athlete/day") data = { date: url.searchParams.get("date") ?? today, timezone: "UTC", training_focus: athleteProfile.training_focus, sessions: [], legacy_gym_sessions: [], state: options.empty ? "no_plan" : "activity_recorded", activities: options.empty ? [] : [{ ...activity, planned_session_id: null, association: "independent", candidate_session_ids: [], checkin: null, comparison: null }], totals: {} };
    else if (/^\/activities\/\d+\/endurance$/.test(path)) data = { sport: "cycling", metrics: [] };
    else if (path === "/api/admin/users" || path === "/api/admin/sessions" || path === "/api/admin/invites" || path === "/api/admin/feedback") {
      const offset = Number(url.searchParams.get("offset") ?? 0), limit = Number(url.searchParams.get("limit") ?? 50);
      const total = 25;
      const allRows = path.endsWith("/users") ? Array.from({ length: total }, (_, i) => ({ id: i + 2, name: `Friend ${i + 1}`, email: `friend${i + 1}@example.com`, role: "friend", ai_access_tier: "full", share_segments: true, active_sessions: 2, disabled: false, last_login_at: today + "T08:00:00Z", created_at: today + "T00:00:00Z" }))
        : path.endsWith("/sessions") ? Array.from({ length: total }, (_, i) => ({ id: i + 1, user_id: i + 2, created_at: today + "T00:00:00Z", expires_at: today + "T23:00:00Z", absolute_expires_at: today + "T23:00:00Z", active: true, remember_me: false }))
        : path.endsWith("/invites") ? Array.from({ length: total }, (_, i) => ({ id: i + 1, used_by: i % 2 ? i : null, expired: false, expires_at: today + "T23:00:00Z" }))
        : Array.from({ length: total }, (_, i) => ({ id: i + 1, user_id: i + 2, category: "idea", message: `Feedback ${i + 1}`, page_url: "/app", created_at: today + "T00:00:00Z", notification_status: i % 3 ? "delivered" : "retrying" }));
      data = { items: allRows.slice(offset, offset + limit), total, limit, offset };
    } else if (path === "/api/admin/system") data = { scope: "container", cpu: { utilization_percent: 13.4, load_1m: 0.4, logical_cpus: 4 }, memory: { scope: "container cgroup", total_bytes: 1000, used_bytes: 500 }, disk: { scope: "container filesystem", total_bytes: 1000, used_bytes: 500 }, postgres: { connections: 4, active_connections: 1, max_connections: 100 }, celery: { available: true, workers: [{ name: "worker1", status: "online" }] } };
    else if (path === "/api/admin/logs") data = { items: [{ timestamp: today + "T00:00:00Z", level: "INFO", source: "test", event: "event" }] };
    else if (path === "/api/admin/notifications") data = { configured: true, pending: 2, failed: 1 };
    else if (path === "/lab/coverage")
      data = {
        timezone: "Europe/Rome",
        local_date: today,
        metrics: labMetrics,
        integrations: [],
      };
    else if (path === "/lab/decision") data = labDecision;
    else if (path === "/lab/changes") data = labDrafts;
    else if (path === "/lab/constraints")
      data = {
        date: today,
        events: [],
        sessions: options.empty
          ? []
          : [
              {
                id: 1,
                date: today,
                session_type: "easy ride",
                description: "Keep the ride conversational.",
                duration_min: 45,
              },
            ],
      };
    else if (path === "/lab/notifications")
      data = {
        quiet_hours_active: false,
        preferences: {
          quiet_start_hour: 22,
          quiet_end_hour: 7,
          daily_cap: 5,
          muted_classes: [],
        },
        items: options.empty
          ? []
          : [
              {
                id: 4,
                category: "data_quality",
                severity: "watch",
                state: "created",
                payload: {
                  title: "Evidence needs attention",
                  why: "A measurement arrived late.",
                  action: "Review data coverage",
                  href: "/app/data-health",
                },
                expires_at: today + "T23:59:59Z",
                snoozed_until: null,
              },
            ],
      };
    else if (path === "/lab/observations")
      data = options.empty
        ? []
        : Array.from({ length: 24 }, (_, i) => ({
            ...labMetrics[0].latest,
            local_date: new Date(
              Date.parse(today + "T12:00:00Z") - i * 86400000,
            )
              .toISOString()
              .slice(0, 10),
            measured_at:
              new Date(Date.parse(today + "T12:00:00Z") - i * 86400000)
                .toISOString()
                .slice(0, 10) + "T06:00:00Z",
            value: 62 + Math.sin(i) * 3,
          }));
    else if (path.startsWith("/lab/evidence/"))
      data = { ...labMetrics[0].latest, current: true, raw_ingest_id: 22 };
    else if (path === "/lab/entries" && url.searchParams.get("kind") === "metric_favorites") data = [{ payload: { metrics: favoriteMetrics } }];
    else if (
      [
        "/lab/entries",
        "/lab/jobs",
        "/lab/documents",
        "/lab/reports",
        "/lab/analyses",
        "/lab/audit",
        "/lab/decisions",
        "/gear",
      ].includes(path)
    )
      data = [];
    else if (path === "/me") data = me;
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
    else if (path === "/dashboard/activity-calendar") {
      const anchor = new Date(today + "T12:00:00Z");
      const weekday = (anchor.getUTCDay() + 6) % 7;
      const first = new Date(anchor.getTime() - (357 + weekday) * 86400000);
      data = { weekly_streak: 3, week_active_days: 1, days: Array.from({ length: 364 }, (_, i) => ({ date: new Date(first.getTime() + i * 86400000).toISOString().slice(0, 10), count: i === 357 + weekday ? 1 : 0, duration_s: i === 357 + weekday ? 3600 : 0, intensity: i === 357 + weekday ? 1 : 0, future: i > 357 + weekday })) };
    }
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
            spo2_avg: null,
            respiration_avg: null,
            vo2max: null,
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
                    hrv_ms: 62 + Math.sin(i) * 3,
                    provider_sleep_score: 82 + Math.sin(i) * 3,
                    sleep_duration: 7.5 + Math.sin(i) * 0.5,
                    sleep_deep: 1.4,
                    sleep_rem: 2,
                    sleep_light: 4.1,
                    restlessness: 4,
                    systemic_stress: 12,
                    load_spike: 15,
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
        ...(key === "hrv_ms"
          ? {
              reference_range: {
                state: "available",
                empirical_range: [58, 66],
                sample_count: 20,
                required_samples: 14,
                median: 62,
                origin: "garmin",
                as_of: end,
              },
            }
          : {}),
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
