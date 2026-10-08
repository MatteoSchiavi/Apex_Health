import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { activity, installApi } from "./fixtures";

const exercises = [
  { name: "Back squat", muscle_group: "legs", sets: 5, reps: 40, volume_kg: 2000, weighted_sets: 5 },
  { name: "Bench press", muscle_group: "push", sets: 2, reps: 16, volume_kg: 800, weighted_sets: 2 },
  { name: "Seated row", muscle_group: "pull", sets: 3, reps: 24, volume_kg: 900, weighted_sets: 3 },
  { name: "Crunch", muscle_group: "core", sets: 4, reps: 40, volume_kg: null, weighted_sets: 0 },
  { name: "Unclassified movement", muscle_group: null, sets: 2, reps: 20, volume_kg: null, weighted_sets: 0 },
].map(exercise => ({ ...exercise, exercise_id: null, recorded_sets: [], previous: null,
  delta_sets: null, delta_reps: null, delta_volume_kg: null }));

async function show(page: Page, options: { theme?: "light" | "dark"; unknownOnly?: boolean; fullBodyOnly?: boolean } = {}) {
  await installApi(page, { theme: options.theme ?? "light" });
  await page.route(url => url.pathname === "/activities/1", route => route.fulfill({ json: {
    ...activity, discipline: "strength", has_streams: false,
    presentation: { kind: "strength", avg_speed_m_s: null, max_speed_m_s: null, avg_cadence: null,
      slope_count: null, zones: [], strength: options.unknownOnly ? exercises.slice(-1) : options.fullBodyOnly
        ? [{ ...exercises[0], name: "Burpee", muscle_group: "full_body" }] : exercises },
  } }));
  await page.goto("/app/activities/1");
}

test("front and back regions use relative recorded sets and filter the same exercises", async ({ page }) => {
  await show(page);
  const diagram = page.locator(".strength-anatomy");
  await expect(diagram.getByText("Front", { exact: true })).toBeVisible();
  await expect(diagram.getByText("Back", { exact: true })).toBeVisible();
  // Ratios are independently known: 5/5, 2/5, 3/5 and 4/5.
  for (const [group, count, intensity] of [["legs", 5, 4], ["push", 2, 2], ["pull", 3, 3], ["core", 4, 4]] as const) {
    const region = diagram.locator(`[role="button"][data-group="${group}"]`);
    await expect(region).toHaveAttribute("data-set-count", String(count));
    await expect(region).toHaveAttribute("data-intensity", String(intensity));
  }
  const calves = diagram.locator('path[data-muscle="calves"]').first();
  await calves.click();
  await expect(diagram.locator('[data-group="legs"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Back squat", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bench press", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "All groups", exact: true }).click();
  await diagram.locator('[data-group="push"]').focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("heading", { name: "Bench press", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Back squat", exact: true })).toHaveCount(0);
});

test("full-body recorded sets own coloured regions and keep them interactive", async ({ page }) => {
  await show(page, { fullBodyOnly: true });
  const fullBody = page.locator('.strength-anatomy [data-group="full_body"]');
  await expect(fullBody).toHaveAttribute("aria-disabled", "false");
  await expect(fullBody).toHaveAttribute("data-intensity", "4");
  await fullBody.locator('path[data-muscle="quads"]').first().click();
  await expect(fullBody).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Burpee", exact: true })).toBeVisible();
  await expect(page.locator('.strength-anatomy [aria-disabled="true"] path[data-muscle]')).toHaveCount(0);
});

test("unclassified sets never paint a muscle or create an enabled anatomical region", async ({ page }) => {
  await show(page, { unknownOnly: true });
  const regions = page.locator('.strength-anatomy [role="button"]');
  await expect(regions).toHaveCount(5);
  for (const region of await regions.all()) {
    await expect(region).toHaveAttribute("aria-disabled", "true");
    await expect(region).toHaveAttribute("data-intensity", "0");
    await expect(region).toHaveAttribute("tabindex", "-1");
  }
  await expect(page.getByRole("heading", { name: "Unclassified movement", exact: true })).toBeVisible();
});

for (const variant of ["light", "dark", "mobile"] as const) {
  test(`anatomical map remains legible in ${variant}`, async ({ page }) => {
    if (variant === "mobile") await page.setViewportSize({ width: 390, height: 844 });
    await show(page, { theme: variant === "dark" ? "dark" : "light" });
    const diagram = page.locator(".strength-anatomy");
    await expect(diagram).toBeVisible();
    await expect(diagram.getByText("Front", { exact: true })).toBeVisible();
    await expect(diagram.getByText("Back", { exact: true })).toBeVisible();
    const rest = await diagram.evaluate(element => getComputedStyle(element).getPropertyValue("--anatomy-rest").trim());
    expect(rest).toBe(variant === "dark" ? "#45493f" : "#dedbd3");
    const bounds = await diagram.boundingBox();
    expect(bounds!.width).toBeLessThan(page.viewportSize()!.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
    if (process.env.APEX_ANATOMY_SCREENSHOT_DIR) {
      mkdirSync(process.env.APEX_ANATOMY_SCREENSHOT_DIR, { recursive: true });
      await diagram.screenshot({ path: `${process.env.APEX_ANATOMY_SCREENSHOT_DIR}/${variant}.png` });
    }
  });
}
