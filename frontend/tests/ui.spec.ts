import { test, expect } from "@playwright/test";
import { installApi, overview, today, keys } from "./fixtures";
test("overview keeps recorded signals reachable and estimates distinct", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Today" }),
  ).toBeVisible();
  await expect(page.getByTestId("overview-history")).not.toHaveAttribute("open", "");
  await page.getByTestId("overview-history").locator("summary").click();
  await expect(page.getByRole("region", { name: "Recorded signals" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Daily readiness, recovery, strain and sleep" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Readiness.*82/ })).toBeVisible();
  await expect(page.getByText("All systems normal")).toHaveCount(0);
  await expect(page.getByText("No overreaching markers")).toHaveCount(0);
  await page.getByRole("button", { name: "4 weeks", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "4 weeks", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
test("all metrics remain reachable through keyboard tabs; sleep score has correct label", async ({
  page,
}) => {
  const visited = new Set<string>();
  page.on("request", (r) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith("/metrics/")) visited.add(path.slice(9));
  });
  await installApi(page);
  for (const [tab, group, expected] of [
    ["health", "signals", ["resting_hr", "hrv_ms", "spo2", "respiration"]],
    ["health", "sleep", ["provider_sleep_score", "sleep_duration", "sleep_deep", "sleep_rem", "sleep_light", "restlessness"]],
    ["health", "body", ["weight", "body_fat", "steps", "floors", "hydration"]],
    ["training", "estimates", ["readiness", "recovery", "strain", "sleep_score", "hrv_deviation", "systemic_stress", "load_spike"]],
    ["training", "load", ["acwr", "acute_load", "chronic_load"]],
    ["training", "fitness", ["vo2max"]],
  ] as const) {
    await page.goto(`/app/biometrics?tab=${tab}&group=${group}`);
    const category = page.getByRole("tab", { name: tab === "health" ? "Health metrics" : "Training & recovery" });
    await category.focus();
    await expect(category).toHaveAttribute("aria-selected", "true");
    await expect.poll(() => expected.every(key => visited.has(key))).toBe(true);
  }
  expect(keys.every(key => visited.has(key))).toBe(true);
});

test("activity pagination and imperial detail preserve missing normalized power", async ({
  page,
}) => {
  await installApi(page, { units: "imperial" });
  await page.goto("/app/activities");
  await expect(
    page.getByText("Totals and sport filters", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load more sessions" }).click();
  await expect(
    page.getByRole("tab", { name: "Running", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Running", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.goto("/app/activities/1");
  await expect(page.getByText("26.22")).toBeVisible();
  await expect(
    page
      .getByText("Normalized power", { exact: true })
      .locator("../..")
      .locator(".stat-value"),
  ).toContainText("—");
  await page.getByRole("tab", { name: "Speed", exact: true }).click();
  await expect(page.getByRole("img", { name: "Speed · mph" })).toBeVisible();
  await page.getByRole("tab", { name: "Laps", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("6.21 mi");
});
test("sleep without epochs shows totals and never fabricates a timeline", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app/sleep/" + today);
  await expect(
    page.getByText("No stage timeline was recorded", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("Stable", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Duration & composition")).toBeVisible();
});
test("queued sync waits for completion and clears persisted job", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app/settings?tab=devices");
  await page.getByRole("button", { name: "Sync now", exact: true }).click();
  await expect(page.getByText("Sync queued.", { exact: false })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Syncing…", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText("Sync complete.", { exact: false })).toBeVisible({
    timeout: 10000,
  });
  expect(
    await page.evaluate(() => localStorage.getItem("apex.sync.1")),
  ).toBeNull();
});

const garminAccount = {
  provider: "garmin", state: "awaiting_new_data", last_attempt_at: today + "T08:00:00Z",
  last_success_at: today + "T08:00:00Z", latest_measurement_at: "2025-01-01T08:00:00Z",
  has_successful_sync: true, data_freshness: "stale", stale_after_hours: 48,
  error_class: null, failed_attempts: 0, credentials_state: "configured", streams_failed: 0, unprocessed: 0,
};

for (const locale of ["en", "it"] as const) {
  test(`owned successful sync and old measurements remain distinct; partial job counts are truthful: ${locale}`, async ({ page }) => {
    await installApi(page, { locale });
    await page.setViewportSize({ width: 390, height: 844 });
    let partial = false, healthRequests = 0;
    await page.route("**/settings/devices", route => route.fulfill({ json: [{ integration_id: 1, provider: "garmin", status: "active", is_main: true, last_synced_at: null, connected_at: today + "T00:00:00Z" }] }));
    await page.route("**/lab/sync-health", route => {
      healthRequests++;
      return route.fulfill({ json: { feeds: [], accounts: [{ ...garminAccount, ...(partial ? { state: "partial", streams_failed: 1, unprocessed: 2 } : {}) }] } });
    });
    await page.route("**/settings/integrations/garmin/sync/test-sync", route => {
      partial = true;
      return route.fulfill({ json: { state: "SUCCESS", completed: true, result: { status: "ok", streams_failed: 1, unprocessed: 2 } } });
    });
    await page.goto("/app/settings?tab=devices");
    await expect(page.getByText(locale === "en" ? "Awaiting new data" : "In attesa di nuovi dati", { exact: true })).toBeVisible();
    await expect(page.getByText(locale === "en" ? "Older measurements" : "Misurazioni meno recenti", { exact: false })).toBeVisible();
    await expect(page.getByText(locale === "en" ? "Never synced" : "Mai sincronizzato", { exact: false })).toHaveCount(0);
    await page.getByRole("button", { name: locale === "en" ? "Sync now" : "Sincronizza ora", exact: true }).click();
    const message = page.getByRole("status").filter({ hasText: locale === "en" ? "Sync finished with incomplete data:" : "Sincronizzazione terminata con dati incompleti:" });
    await expect(message).toContainText(locale === "en" ? "1 feeds failed and 2 records await processing" : "1 flussi non riusciti e 2 record in attesa di elaborazione");
    await expect(page.getByText(locale === "en" ? "Sync complete." : "Sincronizzazione completata.", { exact: false })).toHaveCount(0);
    await expect.poll(() => healthRequests).toBeGreaterThan(1);
    await page.getByRole("tab", { name: locale === "en" ? "Data health" : "Qualità dei dati", exact: true }).click();
    const account = page.getByRole("region", { name: locale === "en" ? "Garmin synchronization" : "Sincronizzazione Garmin", exact: true });
    await expect(account.getByText(locale === "en" ? "Partially synchronized" : "Sincronizzazione parziale", { exact: true })).toBeVisible();
    await expect(account.getByText(locale === "en" ? "Last successful attempt" : "Ultimo tentativo riuscito", { exact: true })).toBeVisible();
    await expect(account.getByText(locale === "en" ? "Latest measurement" : "Ultima misurazione", { exact: true })).toBeVisible();
    await expect(account.getByText(locale === "en" ? "1 feeds failed · 2 records awaiting processing." : "1 flussi non riusciti · 2 record in attesa di elaborazione.", { exact: false })).toBeVisible();
    await expect(account.getByText(locale === "en" ? "Measurement age does not mean" : "La sua età non significa", { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("overlapping sync is informational, follows account completion and refreshes the athlete day", async ({ page }) => {
  await installApi(page);
  let skipped = false, healthRequests = 0, dayRequests = 0;
  await page.route(/\/athlete\/day\?/, route => { dayRequests++; return route.fallback(); });
  await page.route("**/lab/sync-health", route => {
    healthRequests++;
    return route.fulfill({ json: { feeds: [], accounts: [{ ...garminAccount, state: skipped && healthRequests === 2 ? "syncing" : "awaiting_new_data" }] } });
  });
  await page.route("**/settings/integrations/garmin/sync/test-sync", route => {
    skipped = true;
    return route.fulfill({ json: { state: "SUCCESS", completed: true, result: { status: "skipped", reason: "already_running" } } });
  });
  await page.goto("/app");
  await expect.poll(() => dayRequests).toBe(1);
  await page.locator('a[href="/app/settings"]').first().click();
  await page.getByRole("tab", { name: "Devices & Services", exact: true }).click();
  await page.getByRole("button", { name: "Sync now", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Another synchronization is already running." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Syncing…", exact: true })).toBeDisabled();
  expect(await page.evaluate(() => localStorage.getItem("apex.sync.1"))).toBeNull();
  await expect(page.getByText("Sync complete.", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Sync did not complete.", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sync now", exact: true })).toBeEnabled({ timeout: 10000 });
  await expect(page.getByText("Another synchronization is already running.", { exact: false })).toHaveCount(0);
  await page.locator('a[href="/app"]').first().click();
  await expect.poll(() => dayRequests).toBeGreaterThan(1);
});

test("legacy feed checkpoints prevent never-synced claims without inventing a success timestamp", async ({ page }) => {
  await installApi(page);
  await page.route("**/settings/devices", route => route.fulfill({ json: [{ integration_id: 1, provider: "garmin", status: "active", is_main: true, last_synced_at: null }] }));
  await page.route("**/lab/sync-health", route => route.fulfill({ json: { feeds: [{ provider: "garmin", feed: "activities", has_checkpoint: true, last_success_at: null, latest_measurement_at: null }] } }));
  await page.goto("/app/settings?tab=devices");
  await expect(page.getByText("Imported data is available. The successful sync time is not recorded.", { exact: true })).toBeVisible();
  await expect(page.getByText("Never synced", { exact: false })).toHaveCount(0);
  await expect(page.getByText("No synchronization has been recorded yet.", { exact: true })).toHaveCount(0);
});

test("sync health keeps loading, empty and sanitized error states distinct", async ({ page }) => {
  await installApi(page);
  let finish: () => void = () => {};
  await page.route("**/lab/sync-health", async route => {
    await new Promise<void>(resolve => { finish = resolve; });
    return route.fulfill({ json: { feeds: [], accounts: [] } });
  });
  await page.goto("/app/data-health");
  const panel = page.locator(".panel").filter({ has: page.getByText("Sync health", { exact: true }) });
  await expect(panel.getByRole("status")).toContainText("Loading");
  await expect(panel.getByText("No provider syncs are configured.", { exact: true })).toHaveCount(0);
  finish();
  await expect(panel.getByText("No provider syncs are configured.", { exact: true })).toBeVisible();
  await page.route("**/lab/sync-health", route => route.fulfill({ status: 503, json: { detail: "PRIVATE_CONNECTOR_DIAGNOSTIC" } }));
  await page.reload();
  await expect(panel.getByRole("alert")).toContainText("Synchronization status is unavailable.");
  await expect(panel.getByText("No provider syncs are configured.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("PRIVATE_CONNECTOR_DIAGNOSTIC", { exact: false })).toHaveCount(0);
});
test("coach provider failure is visible and preserves the account-scoped draft", async ({
  page,
}) => {
  const { writes } = await installApi(page);
  await page.goto("/app/coach");
  await page
    .getByRole("textbox", { name: "Ask about your data, training, recovery…" })
    .fill("What should I do today?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Coach is temporarily unavailable",
  );
  await expect(
    page.getByRole("textbox", {
      name: "Ask about your data, training, recovery…",
    }),
  ).toHaveValue("What should I do today?");
  expect(writes.find((w) => w.path === "/coach/chats")!.body).toEqual({
    text: "What should I do today?",
  });
  expect(
    await page.evaluate(() => localStorage.getItem("apex.chat.1.draft")),
  ).toBe("What should I do today?");
});
test("profile can clear optional fields and preferences persist across navigation", async ({
  page,
}) => {
  const { writes } = await installApi(page);
  await page.goto("/app/settings");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  expect(writes.find((w) => w.path === "/me")!.body).toMatchObject({
    dob: null,
    sex: null,
    height_cm: null,
  });
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveClass("dark");
  await page
    .locator("aside nav")
    .getByRole("link", { name: "Today", exact:true })
    .click();
  await expect(page.locator("html")).toHaveClass("dark");
});
test("empty and unavailable states are explicit", async ({ page }) => {
  await installApi(page, { empty: true });
  // The shared empty fixture retains chronic load; exercise a genuinely empty health snapshot here.
  await page.route("**/dashboard/overview*", route => route.fulfill({ json: {
    ...overview,
    readiness: { value: null, delta_7d: null }, recovery: { value: null, delta_7d: null },
    strain: { value: null, delta_7d: null }, sleep_score: { value: null, delta_7d: null },
    sleep_hours: null, hrv_ms: null, resting_hr: null, spo2_avg: null, respiration_avg: null,
    vo2max: null, steps: null, weight_kg: null, acute_load: null, chronic_load: null, acwr: null,
    training_load_7d: null, activities: [], sleep: null,
  } }));
  await page.addInitScript(() => localStorage.setItem("apex.setup-checklist.dismissed", "1"));
  await page.goto("/app");
  await expect(page.getByTestId("overview-setup")).toHaveCount(0);
  const healthEmpty = page.getByTestId("overview-health-empty");
  await expect(healthEmpty).toContainText("Connect a data source for ongoing health updates.");
  const scores = page.getByRole("region", { name: "Daily readiness, recovery, strain and sleep" });
  await expect(scores.getByTestId("score-value")).toHaveText(["—", "—", "—", "—"]);
  await expect(scores.getByText("No score for this day", { exact: true })).toHaveCount(4);
  await healthEmpty.getByRole("link", { name: "Connect a data source", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/settings\?tab=devices$/);
  await page.goto("/app/activities");
  await expect(
    page.getByText("No activities in this period yet."),
  ).toBeVisible();
  await page.goto("/app/biometrics?tab=labs");
  await expect(page.getByText("No lab panels recorded yet.")).toBeVisible();
});
test("backend outage keeps the session screen with a retry action", async ({
  page,
}) => {
  await installApi(page, { fail: "/me" });
  await page.goto("/app");
  await expect(
    page.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/app");
});
for (const layout of [
  { width: 390, locale: "it" as const, theme: "dark" as const },
  { width: 390, locale: "en" as const, theme: "light" as const },
  { width: 1440, locale: "en" as const, theme: "dark" as const },
  { width: 1440, locale: "it" as const, theme: "light" as const },
])
  test(
    "all routes fit " +
      layout.width +
      "px / " +
      layout.locale +
      " / " +
      layout.theme,
    async ({ page }) => {
      // This case loads thirteen separate routes; its budget covers the entire
      // traversal, not a thirty-second deadline for one screen.
      test.setTimeout(60_000);
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await installApi(page, { locale: layout.locale, theme: layout.theme });
      await page.setViewportSize({ width: layout.width, height: 844 });
      for (const path of [
        "/app",
        "/app/biometrics",
        "/app/biometrics/weight",
        "/app/activities",
        "/app/activities/1",
        "/app/sleep",
        "/app/sleep/" + today,
        "/app/training",
        "/app/coach",
        "/app/social",
        "/app/settings?tab=devices",
        "/login",
        "/join",
      ]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("html"), path).toHaveJSProperty("scrollWidth", layout.width);
        const tiny = await page.evaluate(() =>
          Array.from(document.querySelectorAll("main label,main button,main p"))
            .filter(
              (el) =>
                el.getBoundingClientRect().height > 0 &&
                parseFloat(getComputedStyle(el).fontSize) < 12,
            )
            .map((el) => el.textContent),
        );
        expect(tiny, path).toEqual([]);
      }
      expect(errors).toEqual([]);
    },
  );
test("search dialog traps focus and returns focus to the trigger", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");
  const trigger = page.getByRole("button", { name: "Go to a page…" });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox").press("Shift+Tab");
  await expect(
    dialog.getByRole("button").last(),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

for (const theme of ["light", "dark"] as const) {
  test(
    "critical screens meet automated accessibility checks in " + theme,
    async ({ page }) => {
      const { default: AxeBuilder } = await import("@axe-core/playwright");
      await installApi(page, { theme });
      for (const path of [
        "/app",
        "/app/biometrics",
        "/app/settings",
        "/app/coach",
        "/login",
        "/join",
      ]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        expect(
          result.violations.map((v) => ({
            id: v.id,
            nodes: v.nodes.map((n) => n.target),
          })),
          path,
        ).toEqual([]);
      }
    },
  );
}
