import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

for (const path of ["/app/biometrics?tab=labs", "/app/lab?tab=labs"]) {
  test(`female laboratory intervals can be recorded from ${path}`, async ({ page }) => {
    await installApi(page, { sex: "female" });
    let saved: Record<string, unknown> | undefined;
    await page.route(url => url.pathname === "/labs", async route => {
      if (route.request().method() === "POST") {
        saved = route.request().postDataJSON();
        await route.fulfill({ status: 201, json: { id: 1 } });
      } else await route.fulfill({ json: [] });
    });
    await page.goto(path);
    if (path.includes("biometrics")) {
      await page.getByRole("button", { name: "Add lab panel", exact: true }).click();
      await page.getByLabel("Panel name", { exact: true }).fill("blood");
    }
    const ranges = page.locator("details").filter({ hasText: "Laboratory reference intervals (optional)" });
    await ranges.locator("summary").click();
    const low = page.getByLabel("Hemoglobin · Lower bound", { exact: true });
    const high = page.getByLabel("Hemoglobin · Upper bound", { exact: true });
    await expect(low).toHaveValue("");
    await expect(high).toHaveValue("");
    await low.fill("12");
    await high.fill("16");
    const form = ranges.locator("xpath=ancestor::form");
    await form.locator('button[type="submit"]').click();
    await expect.poll(() => saved?.reference_ranges).toEqual({ hemoglobin: [12, 16] });
    // No male ranges or measurements are invented for the other markers.
    expect(saved?.hemoglobin).toBeNull();
  });
}

test("female lab results display their reported range without replacing it", async ({ page }) => {
  await installApi(page, { sex: "female" });
  await page.route(url => url.pathname === "/labs", route => route.fulfill({ json: [{
    id: 1, panel_date: "2026-10-05", panel_type: "blood", hemoglobin: 12.5,
    hematocrit: null, ferritin: null, iron: null, wbc: null, plt: null,
    markers: [{ marker: "hemoglobin", value: 12.5, unit: "g/dL", ref_low: 12, ref_high: 16 }],
  }] }));
  await page.goto("/app/biometrics?tab=labs");
  await expect(page.getByText("Reported laboratory interval: 12–16 g/dL", { exact: true })).toBeVisible();
});
