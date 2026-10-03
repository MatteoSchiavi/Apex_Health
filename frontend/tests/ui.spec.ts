import { test, expect } from "@playwright/test";
import { installApi, today, keys } from "./fixtures";
test("overview prioritizes readiness and never invents clinical status", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");
  await expect(
    page.getByRole("heading", { name: "Your daily overview" }),
  ).toBeVisible();
  await expect(page.locator(".hero-number")).toHaveText("82");
  await expect(page.getByText("All systems normal")).toHaveCount(0);
  await expect(page.getByText("No overreaching markers")).toHaveCount(0);
  await page.getByRole("button", { name: "Month", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Month", exact: true }),
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
  await page.goto("/app/biometrics");
  for (const [name, metricKeys] of [
    ["Body signals", ["resting_hr", "hrv_deviation", "spo2", "respiration"]],
    [
      "Recovery & sleep",
      [
        "readiness",
        "recovery",
        "sleep_score",
        "sleep_duration",
        "sleep_deep",
        "sleep_rem",
        "sleep_light",
        "restlessness",
      ],
    ],
    [
      "Load & risk scores",
      [
        "strain",
        "acwr",
        "acute_load",
        "chronic_load",
        "illness_risk",
        "injury_risk",
      ],
    ],
    [
      "Body & daily activity",
      ["weight", "body_fat", "vo2max", "steps", "floors", "hydration"],
    ],
  ] as const) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect
      .poll(() =>
        page
          .locator("a.metric-row")
          .evaluateAll((rows) => rows.map((row) => row.getAttribute("href"))),
      )
      .toEqual(metricKeys.map((key) => "/app/biometrics/" + key));
    await expect
      .poll(() => metricKeys.every((key) => visited.has(key)))
      .toBe(true);
  }
  expect([...visited].sort()).toEqual([...keys].sort());
  const tab = page.getByRole("tab", {
    name: "Body & daily activity",
    exact: true,
  });
  await tab.focus();
  await tab.press("ArrowLeft");
  await expect(
    page.getByRole("tab", { name: "Load & risk scores", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.goto("/app/biometrics/sleep_score");
  await expect(
    page.getByRole("heading", { name: "Sleep Score", exact: true }),
  ).toBeVisible();
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
    .getByRole("link", { name: /Overview/ })
    .click();
  await expect(page.locator("html")).toHaveClass("dark");
});
test("empty and unavailable states are explicit", async ({ page }) => {
  await installApi(page, { empty: true });
  await page.goto("/app");
  await expect(
    page.getByText("Your overview will appear", { exact: false }),
  ).toBeVisible();
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
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
          path,
        ).toBe(layout.width);
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
    dialog.getByRole("button", { name: "Settings", exact: true }),
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
