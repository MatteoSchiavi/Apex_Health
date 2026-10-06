import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { installApi, overview as sampleOverview, today } from "./fixtures";

test("overview restores daily metrics and formats sleep as hours and minutes", async ({
  page,
}) => {
  await installApi(page);
  await page.route("**/dashboard/overview*", (route) =>
    route.fulfill({
      json: {
        ...sampleOverview,
        body_fat_pct: 15.2,
        floors: 6,
        hydration_ml: 2100,
        sleep: {
          ...sampleOverview.sleep,
          total_sleep_s: 30_600,
        },
      },
    }),
  );
  await page.goto("/app");

  await expect(page.getByText("8:30 h", { exact: true })).toBeVisible();
  await expect(page.getByText("Body Fat", { exact: true })).toBeVisible();
  await expect(page.locator('a[href="/app/biometrics/body_fat"]')).toContainText("15.2");
  await expect(page.getByText("Floors", { exact: true })).toBeVisible();
  await expect(page.getByText("Hydration", { exact: true })).toBeVisible();
  await expect(page.locator('a[href="/app/biometrics/hydration"]')).toContainText("2,100");
});

test("overview quick access links lead to the primary destinations", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");

  const quickAccess = page.getByRole("navigation", { name: "Quick access" });
  for (const destination of [
    "/app/calendar",
    "/app/training",
    "/app/biometrics?tab=labs",
    "/app/coach",
    "/app/settings?tab=devices",
  ]) {
    await expect(
      quickAccess.locator(`a[href="${destination}"]`),
    ).toBeVisible();
  }
});

test("overview range selector refreshes signal requests and distinguishes ranges from direction", async ({
  page,
}) => {
  await installApi(page);
  await page.route((url) => url.pathname === "/metrics/vo2max", async (route) => {
    const previous = new Date(today + "T12:00:00Z"); previous.setUTCDate(previous.getUTCDate() - 1);
    await route.fulfill({ json: { metric: "vo2max", unit: "ml/kg/min", start_date: previous.toISOString().slice(0, 10), end_date: today, stats: { latest: 52 }, points: [{ date: previous.toISOString().slice(0, 10), value: 51 }, { date: today, value: 52 }] } });
  });
  const requests: URL[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/metrics/")) requests.push(url);
  });
  await page.goto("/app");

  await expect
    .poll(() => requests.some((url) => url.searchParams.get("days") === "7"))
    .toBe(true);
  const signals = page.getByRole("region", { name: "Recorded signals" });
  await expect(
    signals.getByRole("img", { name: /Within your usual range/ }).first(),
  ).toBeVisible();

  const vo2 = signals.locator("div.panel").filter({ hasText: /VO₂ max/i });
  await expect(vo2.getByText("Increasing", { exact: true })).toBeVisible();
  await expect(vo2.getByRole("img", { name: /Recorded readings/ })).toBeVisible();
  await expect(vo2.getByRole("img", { name: /usual range/ })).toHaveCount(0);

  await page.getByRole("button", { name: "4 weeks" }).click();
  await expect(page.getByRole("button", { name: "4 weeks" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect
    .poll(() =>
      ["hrv_ms", "resting_hr", "sleep_duration", "spo2", "respiration", "vo2max"].every(
        (metric) =>
          requests.some(
            (url) =>
              url.pathname === `/metrics/${metric}` &&
              url.searchParams.get("days") === "28" &&
              url.searchParams.get("end") === today,
          ),
      ),
    )
    .toBe(true);

  if (process.env.APEX_UI_SCREENSHOTS === "1") {
    mkdirSync("/workspace/apex-cloud", { recursive: true });
    await page.screenshot({
      path: "/workspace/apex-cloud/overview-refinement.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: "/workspace/apex-cloud/overview-refinement-mobile.png",
      fullPage: true,
    });
  }
});
