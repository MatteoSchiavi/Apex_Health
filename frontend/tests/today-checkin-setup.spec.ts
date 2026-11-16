import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi, overview, today } from "./fixtures";

for (const locale of ["en", "it"] as const) for (const theme of ["light", "dark"] as const) {
  test(`quick setup and useful Today signals: ${locale}/${theme}`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme, aiConsent: false });
    let checkins = 0;
    await page.route("**/dashboard/check-in", route => {
      checkins++;
      return route.fulfill({ json: { status: "ready", date: today, slot: "morning", generated_at: today+"T08:00:00Z", lines: ["Sleep was shorter today.", "The week's coverage is incomplete.", "Keep the next session easy and reassess."] } });
    });
    await page.route("**/dashboard/overview*", route => route.fulfill({ json: { ...overview,
      provider_signals: [
        {metric:"body_battery", value:52, unit:"/100", origin:"garmin", date:today, fetched_at:today+"T08:00:00Z"},
        {metric:"stress", value:0, unit:"/100", origin:"garmin", date:today, fetched_at:today+"T08:00:00Z"},
        {metric:"hydration", value:750, unit:"ml", origin:"garmin", date:today, fetched_at:today+"T08:00:00Z"},
      ] } }));
    await page.clock.install({time:new Date(today+"T11:59:00Z")});
    await page.setViewportSize({width:390, height:844});
    await page.goto("/app/settings?tab=profile");
    await expect(page.getByTestId("advanced-settings")).not.toHaveAttribute("open");
    await page.getByRole("checkbox", {name:locale === "en" ? "Running" : "Corsa", exact:true}).check();
    await page.getByRole("button", {name:locale === "en" ? "Save athlete context" : "Salva il contesto sportivo", exact:true}).click();
    await expect.poll(() => writes.filter(w => w.path === "/athlete/profile").length).toBe(1);
    expect(writes.find(w => w.path === "/athlete/profile")?.body).toMatchObject({context:{onboarding_step:5}, training_focus:["running"]});
    await page.goto("/app");
    await expect(page.getByTestId("checkin-lines")).toBeVisible();
    await expect(page.getByTestId("today-provider-signals")).toContainText("52");
    await expect(page.getByTestId("today-provider-signals")).toContainText("750");
    const shown = await page.getByTestId("checkin-lines").evaluate(e => ({height:e.getBoundingClientRect().height, lineHeight:parseFloat(getComputedStyle(e).lineHeight)}));
    expect(shown.height).toBeLessThanOrEqual(shown.lineHeight*3+1);
    await expect(page.locator("html")).toHaveJSProperty("scrollWidth",390);
    const initial = checkins;
    await page.clock.fastForward(10*60*1000);
    expect(checkins).toBe(initial);
    await page.setViewportSize({width:1440,height:1000});
    await expect(page.locator("html")).toHaveJSProperty("scrollWidth",1440);
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    await page.getByRole("link", {name:locale === "en" ? "Activities" : "Attività", exact:true}).first().click();
    await page.goBack();
    await expect(page.getByTestId("today-workspace")).toBeVisible();
    expect(checkins).toBe(initial); // internal navigation is not another app open
    if (locale === "en" && theme === "light") await page.screenshot({path:"test-results/today-checkin-desktop.png",fullPage:true});
  });
}

test("historical day does not display today's AI summary as historical evidence", async ({page}) => {
  const { writes, checkins } = await installApi(page);
  await page.goto("/app?date=2026-10-01");
  await expect(page.getByTestId("today-workspace")).toBeVisible();
  await expect(page.getByTestId("today-checkin")).toHaveCount(0);
  await expect.poll(() => checkins.length).toBe(1);
  expect(checkins[0]).toEqual({path:"/dashboard/check-in", body:{}});
  expect(writes).toEqual([]);
});
