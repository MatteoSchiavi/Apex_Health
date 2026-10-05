import { test, expect } from "@playwright/test";
import { installApi, today } from "./fixtures";

test("notifications open from the top bar and return focus on Escape", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app");
  const bell = page.getByRole("button", { name: "Notifications" });
  await expect(bell).toBeVisible();
  await bell.click();
  const panel = page.getByRole("dialog", { name: "Notifications" });
  await expect(panel.getByText("Evidence needs attention")).toBeVisible();
  await panel.getByRole("button", { name: "Mark read" }).click();
  await expect.poll(() => writes.some((write) => write.path === "/lab/notifications/4" && (write.body as { state?: string })?.state === "read")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(bell).toBeFocused();
});

test("Settings holds notification preferences and data health, with monthly calendar", async ({ page }) => {
  await installApi(page);
  await page.goto("/app/settings?tab=notifications");
  await expect(page.getByRole("tab", { name: "Notification preferences" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Data health" }).click();
  await expect(page.getByText("Data coverage", { exact: true }).first()).toBeVisible();
  await page.route("**/schedule/calendar?**", async (route) => route.fulfill({ json: { sessions: [{ id: 1, date: today, session_type: "easy ride", description: "Easy", duration_min: 45 }] } }));
  await page.goto("/app/calendar");
  const grid = page.getByRole("grid", { name: "Calendar" });
  await expect(grid.getByRole("gridcell").first()).toBeVisible();
  await expect(grid.getByText("easy ride")).toBeVisible();
  const month = await page.locator("h2").first().textContent();
  await page.getByRole("button", { name: /Next month|navigation.next_month/ }).click();
  await expect(page.locator("h2").first()).not.toHaveText(month ?? "");
});
