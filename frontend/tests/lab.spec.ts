import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi } from "./fixtures";
test("today shows coverage and separates a decision from a score", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");
  await expect(
    page.getByText("Today's training decision", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("100% of required signals covered"),
  ).toBeVisible();
  await expect(page.getByText("Uncalibrated heuristic").first()).toBeVisible();
  await page.getByRole("button", { name: "Followed", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Followed", exact: true }),
  ).toBeDisabled();
});
test("approval sends the displayed hash and undo has a separate receipt", async ({
  page,
}) => {
  const { writes } = await installApi(page);
  await page.goto("/app/coach?tab=changes");
  await expect(
    page.getByText("Prepare for the regatta", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("Applied locally", { exact: true })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Approve this change", exact: true })
    .click();
  await expect(
    page.getByText("Applied locally", { exact: true }),
  ).toBeVisible();
  expect(
    writes.find((w) => w.path === "/lab/changes/41/approve")?.body,
  ).toEqual({ payload_hash: "a".repeat(64) });
  await expect(
    page.getByText("Device delivery not requested", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Undo local change", exact: true })
    .click();
  await expect(page.getByText("Undone", { exact: true })).toBeVisible();
});
test("stale approval displays a conflict and leaves draft reviewable", async ({
  page,
}) => {
  await installApi(page);
  await page.route("**/lab/changes/41/approve", (r) =>
    r.fulfill({
      status: 409,
      json: { detail: "Data changed; request a fresh preview" },
    }),
  );
  await page.goto("/app/coach?tab=changes");
  await page.getByRole("button", { name: "Approve this change" }).click();
  await expect(
    page.getByText("Data changed; request a fresh preview"),
  ).toBeVisible();
  await expect(page.getByText("Applied locally", { exact: true })).toHaveCount(
    0,
  );
});
test("coverage inspection distinguishes measurement and fetch timestamps", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app/data-health");
  await expect(
    page.getByRole("columnheader", { name: "Measured", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Fetched", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "garmin ↗" }).first().click();
  await expect(page.getByText("raw ingest id", { exact: true })).toBeVisible();
  await expect(page.getByText("22", { exact: true })).toBeVisible();
});
test("registered baseline analysis uses a bounded source-specific request", async ({
  page,
}) => {
  const { writes } = await installApi(page);
  await page.goto("/app/lab");
  await page
    .getByRole("button", { name: "Personal baseline", exact: true })
    .click();
  await expect(page.getByText("P10–P90 · 57 — 67 ms")).toBeVisible();
  expect(writes.find((w) => w.path === "/lab/analytics")?.body).toMatchObject({
    recipe: "personal_baseline",
    metric: "hrv_overnight_rmssd",
    origin: "garmin",
  });
});
for (const path of [
  "/app/lab",
  "/app/data-health",
  "/app/calendar",
  "/app/notifications",
  "/app/gear",
])
  test(`mobile ${path} stays within the viewport and is accessible`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApi(page, { empty: true });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(result.violations).toEqual([]);
  });
test("Italian performance lab translates its controls", async ({ page }) => {
  await installApi(page, { locale: "it" });
  await page.goto("/app/lab");
  await expect(
    page.getByRole("heading", { name: "Laboratorio performance" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Esperimenti", exact: true }).click();
  await expect(
    page.getByText("Nuovo esperimento", { exact: true }),
  ).toBeVisible();
});

test("compact density persists and navigation fits short screens", async ({
  page,
}) => {
  await installApi(page);
  await page.route("**/lab/entries?kind=privacy_preferences", (route) =>
    route.fulfill({ json: [{ payload: { density: "compact" } }] }),
  );
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/app/lab");
  const card = page.locator("main .panel.p-6").first();
  await expect(card).toHaveCSS("padding-top", "16px");
  const aside = page.locator("aside");
  expect(
    await aside.evaluate((node) => node.scrollHeight <= node.clientHeight),
  ).toBe(true);
  await page.goto("/app/data-health");
  await expect(page.locator("main .panel.p-6").first()).toHaveCSS(
    "padding-top",
    "16px",
  );
});

test("minimal replanning sends a typed request and explains an unchanged plan", async ({
  page,
}) => {
  const { writes } = await installApi(page);
  await page.goto("/app/calendar");
  await page
    .getByRole("button", { name: "Draft the smallest supported adjustment" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "keeping the current plan",
  );
  expect(writes.find((w) => w.path === "/lab/replan")?.body).toEqual({});
});
