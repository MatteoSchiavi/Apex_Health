import { expect, test } from "@playwright/test";
import { installApi, today, overview } from "./fixtures";
import { sleepWindow } from "../src/features/sleep/sleep-timing";

test("sleep windows align local bedtime across midnight and DST", () => {
  const [bed, wake] = sleepWindow("2026-10-06T22:02:00Z", "2026-10-07T06:00:00Z", "2026-10-07", "Europe/Rome");
  expect(bed).toBeCloseTo(2 / 60);
  expect(wake).toBe(8);
  expect(sleepWindow("2026-10-24T21:30:00Z", "2026-10-25T07:00:00Z", "2026-10-25", "Europe/Rome")).toEqual([-0.5, 8]);
  expect(sleepWindow("2026-03-28T22:30:00Z", "2026-03-29T06:00:00Z", "2026-03-29", "Europe/Rome")).toEqual([-0.5, 8]);
});

test("rendered sleep window places bedtime above waking and keeps a visible bar", async ({ page }) => {
  await installApi(page);
  await page.goto('/app/sleep');
  const card = page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Bed window', exact: true }) });
  await expect(card.locator('canvas')).toBeVisible();
  const positions = await card.evaluate(async el => {
    const modulePath = '/node_modules/.vite/deps/echarts_core.js';
    const echarts = await import(modulePath);
    const chart = echarts.getInstanceByDom(el.querySelector('[_echarts_instance_]'));
    const [index, bed, wake] = chart.getOption().series[0].data[0];
    const bedY = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [index, bed])[1];
    const wakeY = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [index, wake])[1];
    const bars = chart.getZr().storage.getDisplayList().filter((item: { type: string; shape?: { height?: number } }) => item.type === 'rect' && (item.shape?.height ?? 0) > 10);
    return { bedY, wakeY, bars: bars.length };
  });
  expect(positions.bedY).toBeLessThan(positions.wakeY);
  expect(positions.wakeY - positions.bedY).toBeGreaterThan(50);
  expect(positions.bars).toBeGreaterThan(0);
});

test("favourites persist on the account and can be unstarred", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app/biometrics");
  await expect(page.getByRole("tab", { name: "Favourites", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Star metrics in Health or Training & recovery to build your quick view.")).toBeVisible();
  await page.getByRole("tab", { name: "Health metrics", exact: true }).click();
  await page.getByRole("button", { name: "Star Resting Heart Rate", exact: true }).click();
  await expect.poll(() => writes.some(w => w.path === "/lab/entries" && (w.body.entry as { metrics?: string[] })?.metrics?.includes("resting_hr"))).toBe(true);
  await page.getByRole("tab", { name: "Favourites", exact: true }).click();
  await expect(page.getByRole("button", { name: "Unstar Resting Heart Rate", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await page.getByRole("button", { name: "Unstar Resting Heart Rate", exact: true }).click();
  await expect(page.getByText("Star metrics in Health or Training & recovery to build your quick view.")).toBeVisible();
});

test("sidebar expands on hover and keyboard focus without moving its targets", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/app");
  const aside = page.locator("aside");
  await expect(aside).toHaveCSS("width", "76px");
  await aside.hover();
  await expect(aside).toHaveCSS("width", "224px");
  await aside.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/settings$/);
  await page.mouse.move(800, 200);
  await expect(aside).toHaveCSS("width", "76px");
  // Keyboard navigation deliberately opens labels; mouse focus must not keep
  // the sidebar expanded after the pointer has left it.
  await page.keyboard.press("Tab");
  const settings = aside.getByRole("link", { name: "Settings", exact: true });
  await settings.focus();
  await expect(aside).toHaveCSS("width", "224px");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/settings$/);
});

test("search finds a training tab and specific metrics", async ({ page }) => {
  await installApi(page);
  await page.goto("/app");
  await page.getByRole("button", { name: "Go to a page…" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("training load");
  await dialog.getByRole("button", { name: "Training · Training load", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/training\?tab=load$/);
  await expect(page.getByRole("tab", { name: "Training load" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "Go to a page…" }).click();
  await page.getByRole("dialog").getByRole("textbox").fill("resting_hr");
  await page.getByRole("dialog").getByRole("button", { name: "Resting Heart Rate", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/biometrics\/resting_hr$/);
});

test("overview has one warning, a full activity grid and visible daily scores", async ({ page }) => {
  await installApi(page);
  await page.route("**/dashboard/overview*", route => route.fulfill({ json: { ...overview, alerts: Array.from({ length: 8 }, (_, i) => ({ severity: "warning", type: "sync_failure", message: `Garmin warning ${i}` })) } }));
  await page.goto("/app");
  await expect(page.getByText(/Garmin warning \d/)).toHaveCount(1);
  const grid = page.getByRole("group", { name: "Activity · last 52 weeks" });
  await expect(grid.locator(":scope > *")).toHaveCount(364);
  await expect(page.getByRole("region", { name: "Daily readiness, recovery, strain and sleep" })).toBeVisible();
  await expect(grid.locator(`a[href="/app/activities?date=${today}"]`)).toBeVisible();
});

test("overview load chart resizes across desktop and mobile widths", async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/app");
  const plot = page.getByRole("img", { name: /^Training load ·/ });
  await expect(plot.locator("canvas")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => plot.evaluate(el => {
    const canvas = el.querySelector("canvas")!;
    return Math.abs(canvas.getBoundingClientRect().width - el.getBoundingClientRect().width);
  })).toBeLessThan(2);
});

for (const theme of ["dark", "light"] as const) test(`GPS map and route follow ${theme} theme`, async ({ page }) => {
  await installApi(page, { theme });
  await page.route("https://*.basemaps.cartocdn.com/**", route => route.abort());
  await page.route(url => url.pathname === "/activities/1/streams", route => route.fulfill({ json: {
    activity_id: 1, t: [0, 60], columns: { hr: [120, 130], lat: [45.46, 45.461], lon: [9.18, 9.181] },
  } }));
  await page.goto("/app/activities/1");
  await expect(page.locator('.leaflet-overlay-pane path[fill="none"]')).toHaveAttribute("stroke", theme === "dark" ? "#ffffff" : "#000000");
  await expect(page.locator(".leaflet-tile").first()).toHaveAttribute("src", new RegExp(theme === "dark" ? "/dark_all/" : "/light_all/"));
});
