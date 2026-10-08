import { expect, test, type Page } from "@playwright/test";
import { activity, installApi } from "./fixtures";

const summary = {
  kind: "running", avg_speed_m_s: 10 / 3, max_speed_m_s: 14, avg_cadence: null,
  slope_count: null, zones: [], strength: [],
};
async function detail(page: Page, changes: Record<string, unknown>, options: Parameters<typeof installApi>[1] = {}) {
  await installApi(page, options);
  await page.route(url => url.pathname === "/activities/1", route => route.fulfill({ json: { ...activity, ...changes } }));
  await page.goto("/app/activities/1");
}

test("running uses pace in chosen distance units, including lap splits", async ({ page }) => {
  await detail(page, { discipline: "running", distance_m: 5000, duration_s: 1500, presentation: { ...summary, avg_cadence: 174 } });
  await expect(page.locator(".stat-pod").filter({ has: page.getByText("Pace", { exact: true }) })).toContainText("5:00");
  await expect(page.getByText("min/km", { exact: true })).toBeVisible();
  await expect(page.locator(".stat-pod").filter({ has: page.getByText("Cadence", { exact: true }) })).toContainText("174");
  await expect(page.getByText("spm", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Laps", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("2:00 min/km");
});

test("imperial running pace converts metres per second to minutes per mile", async ({ page }) => {
  await detail(page, { discipline: "running", presentation: summary }, { units: "imperial" });
  await expect(page.locator(".stat-pod").filter({ has: page.getByText("Pace", { exact: true }) })).toContainText("8:03");
  await expect(page.getByText("min/mi", { exact: true })).toBeVisible();
});

test("sailing uses nautical miles and knots and removes altitude from every detail section", async ({ page }) => {
  await installApi(page);
  await page.route(url => url.pathname === "/activities/1", route => route.fulfill({ json: {
    ...activity, discipline: "sailing", distance_m: 18520, duration_s: 3600,
    presentation: { ...summary, kind: "sailing", avg_speed_m_s: 18520 / 3600, max_speed_m_s: 10 },
    weather: { wind_speed_10m_max: 18.52 },
    source_metrics: { garmin: { altitude_m: 400, elevation_gain_m: 500, maxSpeed: 10 }, malformed: null, scalar: 4 },
    laps: [{ ...activity.laps[0], duration_s: 3600, distance_m: 18520 }],
  } }));
  await page.route(url => url.pathname === "/activities/1/streams", route => route.fulfill({ json: {
    activity_id: 1, t: [0, 60], columns: { hr: [120, 130], speed: [5, 10], altitude: [300, 400], lat: [], lon: [] },
  } }));
  await page.goto("/app/activities/1");
  await expect(page.getByText("nm", { exact: true })).toBeVisible();
  await expect(page.getByText("kn", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("tab", { name: "Elevation", exact: true })).toHaveCount(0);
  await expect(page.getByText("Elevation Gain", { exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: "Laps", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("10.00 nm");
  await expect(page.locator("tbody")).toContainText("10.0 kn");
  await page.getByRole("tab", { name: "Sources", exact: true }).click();
  await expect(page.getByText("altitude m", { exact: true })).toHaveCount(0);
  await expect(page.getByText("elevation gain m", { exact: true })).toHaveCount(0);
  await expect(page.getByText("19.4 kn", { exact: true })).toBeVisible();
});

test("strength groups filter completed exercises and preserve unknown volume", async ({ page }) => {
  await detail(page, { discipline: "strength", has_streams: false, presentation: { ...summary, kind: "strength", strength: [
    { exercise_id: 1, name: "Back squat", muscle_group: "legs", sets: 3, reps: 24, volume_kg: 1200, weighted_sets: 3,
      previous: { date: "2026-01-01", sets: 2, reps: 16, volume_kg: 640 }, delta_sets: 1, delta_reps: 8, delta_volume_kg: 560 },
    { exercise_id: 2, name: "Push up", muscle_group: "push", sets: 2, reps: 20, volume_kg: null, weighted_sets: 0,
      previous: null, delta_sets: null, delta_reps: null, delta_volume_kg: null },
  ] } });
  await expect(page.getByRole("heading", { name: "Back squat" })).toBeVisible();
  await expect(page.getByText("Weight recorded for 0 of 2 sets", { exact: true })).toBeVisible();
  await expect(page.getByText("— kg", { exact: true })).toBeVisible();
  await expect(page.getByText(/Change: \+1 Sets · \+8 Reps · \+560 kg/)).toBeVisible();
  const legs = page.locator('svg [role="button"][aria-label="Legs"]');
  await legs.focus();
  await page.keyboard.press("Enter");
  await expect(legs).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Push up" })).toHaveCount(0);
  await page.getByRole("button", { name: "All groups", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Push up" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Route", exact: true })).toHaveCount(0);
});

test("unrecorded strength and HIIT retain honest missing data and omit GPS maps", async ({ page }) => {
  await detail(page, { discipline: "strength", has_streams: false, avg_hr: 150, presentation: { ...summary, kind: "strength" } });
  await expect(page.getByText("No completed exercise sets were recorded for this session.")).toBeVisible();
  await expect(page.getByRole("group", { name: "Muscle groups", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Route", exact: true })).toHaveCount(0);
  await page.route(url => url.pathname === "/activities/1", route => route.fulfill({ json: { ...activity, discipline: "hiit", has_streams: false,
    presentation: { ...summary, kind: "hiit" } } }));
  await page.reload();
  await expect(page.getByText("Calories", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Route", exact: true })).toHaveCount(0);
  await expect(page.getByText("Cadence", { exact: true })).toHaveCount(0);
});

test("skiing displays actual max speed without turning arbitrary laps into runs", async ({ page }) => {
  await detail(page, { discipline: "skiing", presentation: { ...summary, kind: "skiing", max_speed_m_s: 25 } });
  await expect(page.getByText("Maximum speed", { exact: true })).toBeVisible();
  await expect(page.locator(".stat-pod").filter({ has: page.getByText("Maximum speed", { exact: true }) })).toContainText("90.0");
  const pod = page.locator(".stat-pod").filter({ has: page.getByText("Recorded runs", { exact: true }) });
  await expect(pod).toContainText("—");
});

test("cycling exposes only supplied zone boundaries without an assumed FTP", async ({ page }) => {
  await detail(page, { presentation: { ...summary, kind: "cycling", avg_cadence: 88, zones: [
    { metric: "power", name: "Recorded Z2", duration_s: 600, lower: null, upper: null },
  ] } });
  await expect(page.locator(".stat-pod").filter({ has: page.getByText("Cadence", { exact: true }) })).toContainText("88");
  await expect(page.getByText("Power · Recorded Z2", { exact: true })).toBeVisible();
  await expect(page.getByText(/FTP/)).toHaveCount(0);
});


test("imperial strength shows recorded set weights, session totals and comparable volume in pounds", async ({ page }) => {
  await detail(page, { discipline: "strength", has_streams: false, presentation: { ...summary, kind: "strength", strength: [
    { exercise_id: 1, name: "Back squat", muscle_group: "legs", sets: 2, reps: 13, volume_kg: 300, weighted_sets: 2,
      recorded_sets: [{ reps: 5, weight_kg: 20 }, { reps: 8, weight_kg: 25 }],
      previous: { date: "2026-01-01", sets: 1, reps: 5, volume_kg: 100, weighted_sets: 1 },
      delta_sets: 1, delta_reps: 8, delta_volume_kg: 200 },
    { exercise_id: 2, name: "Push up", muscle_group: "push", sets: 1, reps: 10, volume_kg: null, weighted_sets: 0,
      recorded_sets: [{ reps: 10, weight_kg: null }],
      previous: null, delta_sets: null, delta_reps: null, delta_volume_kg: null },
  ] } }, { units: "imperial" });
  const totals = page.getByRole("heading", { name: "Session totals", exact: true }).locator("..");
  await expect(totals.locator(".stat-pod").filter({ has: page.getByText("Sets", { exact: true }) })).toContainText("3");
  await expect(totals.locator(".stat-pod").filter({ has: page.getByText("Reps", { exact: true }) })).toContainText("23");
  await expect(totals.locator(".stat-pod").filter({ has: page.getByText("Volume", { exact: true }) })).toContainText("661");
  await expect(totals).toContainText("Weight recorded for 2 of 3 sets");
  const squat = page.getByRole("heading", { name: "Back squat", exact: true }).locator("..");
  await expect(squat).toContainText("661 lb");
  await expect(squat).toContainText("Previous session · 2026-01-01: 1 Sets · 5 Reps · 220 lb");
  await expect(squat).toContainText("Change: +1 Sets · +8 Reps · +441 lb");
  await squat.locator("summary").click();
  const rows = squat.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.first().locator("td").nth(1)).toHaveText("5");
  await expect(rows.first().locator("td").nth(2)).toHaveText("44.1 lb");
  await expect(rows.nth(1).locator("td").nth(1)).toHaveText("8");
  await expect(rows.nth(1).locator("td").nth(2)).toHaveText("55.1 lb");
  await page.locator('svg [role="button"][aria-label="Legs"] path[data-muscle="quads"]').first().click();
  await expect(page.getByRole("heading", { name: "Push up", exact: true })).toHaveCount(0);
  await expect(totals).toContainText("23");
  await page.getByRole("button", { name: "All groups", exact: true }).click();
  const push = page.getByRole("heading", { name: "Push up", exact: true }).locator("..");
  await push.locator("summary").click();
  await expect(push.locator("tbody tr td").nth(2)).toHaveText("— lb");
});
