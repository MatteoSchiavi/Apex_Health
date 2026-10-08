import { expect, test } from "@playwright/test";
import { installApi, today } from "./fixtures";

test("collapsed sidebar keeps the Apex mark as the brand", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/app");
  await page.mouse.move(600, 400);
  await expect(page.locator("aside")).toHaveCSS("width", "76px");

  const brand = page.locator("aside").getByRole("link", { name: "Apex Health" });
  await expect(brand).toBeVisible();
  await expect(brand.locator("svg path")).toHaveAttribute(
    "d",
    "M16 2L31 29H23L16 15L9 29H1Z",
  );
});

test("sleep stage timeline names each phase in its legend", async ({ page }) => {
  await installApi(page);
  await page.route(`**/sleep/${today}/stages`, (route) =>
    route.fulfill({
      json: {
        date: today,
        source: "garmin",
        segments: [
          {
            stage: "deep",
            t_start: `${today}T00:00:00Z`,
            t_end: `${today}T00:30:00Z`,
          },
          {
            stage: "rem",
            t_start: `${today}T00:30:00Z`,
            t_end: `${today}T01:00:00Z`,
          },
        ],
      },
    }),
  );
  await page.goto(`/app/sleep/${today}`);
  const legend = page.getByLabel("Architecture");
  for (const phase of ["Deep", "REM", "Core", "Awake"]) {
    await expect(legend.getByText(phase, { exact: true })).toBeVisible();
  }
});
