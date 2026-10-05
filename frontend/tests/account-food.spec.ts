import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("session discovery and logout clear private drafts without erasing preferences", async ({ page }) => {
  await installApi(page);
  await page.addInitScript(() => {
    localStorage.setItem("apex.chat.1.draft", "Owner private draft");
    localStorage.setItem("apex.chat.99.draft", "Another account's private draft");
    localStorage.setItem("apex.sync.99", "private-job");
  });
  await page.goto("/app/coach");
  await expect(page.getByRole("textbox", { name: "Ask about your data, training, recovery…" })).toHaveValue("Owner private draft");
  expect(await page.evaluate(() => localStorage.getItem("apex.chat.99.draft"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("apex.sync.99"))).toBeNull();
  await page.getByRole("button", { name: "Sign out", exact: true }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem("apex.chat.1.draft"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("apex.theme"))).toBe("light");
});

test("Food reads an external diary and remains disconnectable after app credentials are unset", async ({ page }) => {
  await installApi(page);
  let connected = true;
  await page.route("**/nutrition/fitbit/**", async (route) => {
    if (route.request().url().endsWith("/status")) {
      await route.fulfill({ json: { configured: false, connected, provider: "fitbit" } });
    } else {
      await route.fulfill({ json: { date: "2026-10-05", summary: { calories: 1200, protein: 65 }, foods: [{ name: "Oats", amount: 1, unit: "cup", calories: 300 }] } });
    }
  });
  await page.route("**/nutrition/fitbit", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    connected = false;
    await route.fulfill({ status: 204 });
  });
  await page.goto("/app/lab?tab=nutrition");
  await expect(page.getByText("Oats · 1 cup", { exact: true })).toBeVisible();
  await expect(page.getByText("1,200", { exact: true })).toBeVisible();
  // A disconnected/unconfigured app should never strand stored tokens.
  const button = page.getByRole("button", { name: "Disconnect", exact: true });
  await button.click();
  await expect(button).toHaveCount(0);
  await expect(page.getByText("Oats · 1 cup", { exact: true })).toHaveCount(0);
});
