import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

const alphaUsage = {
  window_days: 28,
  weekly_active_alpha_users: 6,
  ai_users: 4,
  proposals: 5,
  acceptance_rate: 0.4,
  edit_rate: 0.2,
  rejection_rate: 0.2,
  decision_influence_rate: null,
  decision_feedback_responses: 0,
  provider_failure_counts: { garmin: 3, strava: 1 },
  events: { overview_viewed: 10, metric_explanation_opened: 4 },
  formula:
    "Decision influence is based on user feedback. It measures reported influence, not physiological benefit.",
};

test("owner admin shows compact alpha usage and handles missing rates", async ({
  page,
}) => {
  await installApi(page);
  await page.route("**/api/admin/alpha*", (route) =>
    route.fulfill({ json: alphaUsage }),
  );
  await page.goto("/admin");

  await expect(page.getByRole("heading", { name: "Alpha usage" })).toBeVisible();
  await expect(page.getByText("Last 28 days")).toBeVisible();
  await expect(page.getByText("Weekly active alpha users")).toBeVisible();
  await expect(page.getByText("Reported decision influence")).toBeVisible();
  await expect(page.getByText("—", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("garmin", { exact: true })).toBeVisible();
  await expect(page.getByText("3", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("not physiological benefit", { exact: false }),
  ).toBeVisible();
});

test("alpha usage labels are localized in Italian", async ({ page }) => {
  await installApi(page, { locale: "it" });
  await page.route("**/api/admin/alpha*", (route) =>
    route.fulfill({ json: alphaUsage }),
  );
  await page.goto("/admin");

  await expect(page.getByRole("heading", { name: "Uso alpha" })).toBeVisible();
  await expect(page.getByText("Ultimi 28 giorni")).toBeVisible();
  await expect(page.getByText("Influenza riferita", { exact: true })).toBeVisible();
  await expect(page.getByText("non misura un beneficio fisiologico", { exact: false })).toBeVisible();
});
