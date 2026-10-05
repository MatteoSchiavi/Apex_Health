import { expect, test, type Page } from "@playwright/test";
import { installApi } from "./fixtures";

type MetricPayload = {
  metric: string;
  label: string;
  unit: string;
  start_date: string;
  end_date: string;
  points: { date: string; value: number | null }[];
  stats: Record<string, number | null>;
  reference_range?: {
    state: string;
    empirical_range: [number, number] | null;
    sample_count: number;
    required_samples: number;
    median: number | null;
    origin: string;
    as_of: string;
  } | null;
};

const start = "2026-09-20";
const end = "2026-10-04";

function metric(
  key: string,
  value: number,
  unit: string,
  reference_range?: MetricPayload["reference_range"],
): MetricPayload {
  return {
    metric: key,
    label: key,
    unit,
    start_date: start,
    end_date: end,
    points: [
      { date: "2026-10-03", value: value - 2 },
      { date: end, value },
    ],
    stats: { count: 2, min: value - 2, max: value, mean: value - 1 },
    ...(reference_range === undefined ? {} : { reference_range }),
  };
}

async function mockMetric(page: Page, key: string, payload: MetricPayload) {
  // Register after installApi so this exact endpoint overrides only its mock.
  await page.route(
    (url) => new URL(url).pathname === `/metrics/${key}`,
    (route) => route.fulfill({ status: 200, json: payload }),
  );
}

test("biometrics opens on the body signals tab by default", async ({ page }) => {
  await installApi(page);
  await page.goto("/app/biometrics");

  await expect(page).toHaveURL(/\/app\/biometrics$/);
  await expect(
    page.getByRole("tab", { name: "Body signals", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});

test("HRV interpretation labels an in-range result and shows its measured band", async ({
  page,
}) => {
  await installApi(page);
  await mockMetric(
    page,
    "hrv_ms",
    metric("hrv_ms", 60, "ms", {
      state: "available",
      empirical_range: [45, 65],
      sample_count: 20,
      required_samples: 14,
      median: 55,
      origin: "observations",
      as_of: end,
    }),
  );
  await page.goto("/app/biometrics/hrv_ms");

  await expect(
    page.getByText("Within your usual range", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", {
      name: "Within your usual range · 45.0–65.0 ms",
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/45\.0–65\.0 ms · 20 comparable days/),
  ).toBeVisible();
});

test("HRV interpretation calls out a value above the measured band", async ({
  page,
}) => {
  await installApi(page);
  await mockMetric(
    page,
    "hrv_ms",
    metric("hrv_ms", 72, "ms", {
      state: "available",
      empirical_range: [45, 65],
      sample_count: 20,
      required_samples: 14,
      median: 55,
      origin: "observations",
      as_of: end,
    }),
  );
  await page.goto("/app/biometrics/hrv_ms");

  await expect(
    page.getByText("Above your usual range", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Above your usual range · 45.0–65.0 ms" }),
  ).toBeVisible();
});

test("HRV range shows the warming sample count before enough days are recorded", async ({
  page,
}) => {
  await installApi(page);
  await mockMetric(
    page,
    "hrv_ms",
    metric("hrv_ms", 60, "ms", {
      state: "warming",
      empirical_range: null,
      sample_count: 8,
      required_samples: 14,
      median: null,
      origin: "observations",
      as_of: end,
    }),
  );
  await page.goto("/app/biometrics/hrv_ms");

  await expect(page.getByText("Personal range: 8 / 14 recorded days")).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Within your usual range|Above your usual range/ }),
  ).toHaveCount(0);
});

test("sleep duration uses clock formatting in the hero and measurements table", async ({
  page,
}) => {
  await installApi(page);
  await mockMetric(page, "sleep_duration", metric("sleep_duration", 7.5, "h"));
  await page.goto("/app/biometrics/sleep_duration");

  await expect(page.locator(".hero-number")).toHaveText("7:30 h");
  await page.getByText("View all measurements", { exact: true }).click();
  await expect(page.locator("tbody tr").first()).toContainText("7:30 h");
});
