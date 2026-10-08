import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

// Opt-in browser proof consumes the actual database presentation produced by
// backend/tests/test_original_strength_recordings.py. Keep this private JSON
// and its recordings outside Git; CI uses synthetic regression fixtures.
const evidencePath = process.env.APEX_FIT_VERIFICATION_OUTPUT;
const evidence = evidencePath ? JSON.parse(readFileSync(evidencePath, "utf8")) as {
  file: string; sets: number; reps: number;
  presentation: { strength: { name: string; muscle_group: string | null; sets: number }[] };
  activity: Record<string, unknown>; stream_view: Record<string, unknown>;
}[] : [];

test("original FIT database presentations render totals and filterable body groups", async ({ page }) => {
  test.skip(!evidencePath, "private original FIT presentation supplied only for opt-in verification");
  expect(evidence.length).toBeGreaterThan(0);
  await installApi(page);
  for (const recording of evidence) {
    await page.route(url => url.pathname === "/activities/1", route => route.fulfill({ json: {
      ...recording.activity, id: 1,
    } }));
    await page.route(url => url.pathname === "/activities/1/streams", route => route.fulfill({ json: { ...recording.stream_view, activity_id: 1 } }));
    await page.goto("/app/activities/1");
    const totals = page.getByRole("heading", { name: "Session totals", exact: true }).locator("..");
    await expect(totals.locator(".stat-pod").filter({ has: page.getByText("Sets", { exact: true }) })).toContainText(String(recording.sets));
    await expect(totals.locator(".stat-pod").filter({ has: page.getByText("Reps", { exact: true }) })).toContainText(String(recording.reps));
    for (const exercise of recording.presentation.strength) {
      await expect(page.getByRole("heading", { name: exercise.name, exact: true })).toBeVisible();
    }
    for (const group of ["legs", "push", "pull", "core", "full_body"]) {
      const hasGroup = recording.presentation.strength.some(e => e.muscle_group === group);
      const region = page.locator('svg g[role="button"]').nth(["legs", "push", "pull", "core", "full_body"].indexOf(group));
      await expect(region).toHaveAttribute("aria-disabled", String(!hasGroup));
      if (!hasGroup) continue;
      await region.focus();
      await page.keyboard.press("Enter");
      for (const exercise of recording.presentation.strength) {
        await expect(page.getByRole("heading", { name: exercise.name, exact: true })).toHaveCount(exercise.muscle_group === group ? 1 : 0);
      }
      await page.getByRole("button", { name: "All groups", exact: true }).click();
    }
    if (process.env.APEX_FIT_SCREENSHOT_DIR) {
      await page.screenshot({ path: `${process.env.APEX_FIT_SCREENSHOT_DIR}/${recording.file}.png`, fullPage: true });
    }
  }
});
