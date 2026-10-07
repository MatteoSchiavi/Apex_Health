import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

const syncHealth = {
  feeds: [
    {
      provider: "oura",
      feed: "sleep",
      state: "stale",
      last_attempt_at: "2026-10-07T10:00:00Z",
      last_success_at: "2026-10-07T10:00:00Z",
      latest_measurement_at: "2026-10-03T08:00:00Z",
      stale_after_hours: 48,
      error_class: null,
      retry_state: "idle",
      has_checkpoint: true,
      failed_attempts: 0,
      credentials_state: "configured",
    },
    {
      provider: "strava",
      feed: "account_sync",
      state: "available",
      last_attempt_at: null,
      last_success_at: "2026-10-07T09:00:00Z",
      latest_measurement_at: null,
      stale_after_hours: 48,
      error_class: null,
      retry_state: "idle",
      has_checkpoint: true,
      failed_attempts: 0,
      credentials_state: "configured",
    },
  ],
};

test("sync health distinguishes a recent fetch from stale measurements", async ({
  page,
}) => {
  await installApi(page);
  await page.route("**/lab/sync-health", (route) =>
    route.fulfill({ json: syncHealth }),
  );
  await page.goto("/app/data-health");

  await expect(page.getByText("Sync health", { exact: true })).toBeVisible();
  await expect(page.getByText("Stale", { exact: true })).toBeVisible();
  const sleepFeed = page.getByRole("region", { name: "oura sleep" });
  await expect(sleepFeed.getByText("Last attempt", { exact: true })).toBeVisible();
  await expect(sleepFeed.getByText("Latest measurement", { exact: true })).toBeVisible();
  await expect(sleepFeed.getByText("Stored", { exact: true })).toBeVisible();
  await expect(page.getByText("account sync", { exact: true })).toBeVisible();
});

test("sync health panel uses Italian labels", async ({ page }) => {
  await installApi(page, { locale: "it" });
  await page.route("**/lab/sync-health", (route) =>
    route.fulfill({ json: syncHealth }),
  );
  await page.goto("/app/data-health");

  await expect(page.getByText("Salute sincronizzazione", { exact: true })).toBeVisible();
  await expect(page.getByText("Obsoleto", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "oura sleep" }).getByText("Ultimo tentativo", { exact: true })).toBeVisible();
});
