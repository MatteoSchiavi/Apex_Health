import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("owner gets admin tools while a friend is redirected away", async ({ page }) => {
  await installApi(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Owner administration" })).toBeVisible();
  await expect(page.getByText("13.4%")).toBeVisible();
  await expect(page.getByText("Delivered").first()).toBeVisible();

  await installApi(page, { role: "friend" });
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Owner administration" })).toHaveCount(0);
});

test("feedback dialog supports Escape, focus return, successful single submit and inline failure", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app");
  const opener = page.getByRole("button", { name: "Feedback" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Share feedback" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();

  await opener.click();
  await page.getByLabel("Category").selectOption("idea");
  await page.getByLabel("Message", { exact: true }).fill("Please improve the trend chart.");
  const send = page.getByRole("button", { name: "Send feedback" });
  await send.dblclick();
  await expect(page.getByRole("status").filter({ hasText: "Feedback saved." })).toBeVisible();
  expect(writes.filter((w) => w.path === "/api/feedback")).toHaveLength(1);
  expect(writes.find((w) => w.path === "/api/feedback")?.body.page_url).toBe("/app");

  await installApi(page, { fail: "/api/feedback" });
  await page.goto("/app");
  await page.getByRole("button", { name: "Feedback" }).click();
  await page.getByLabel("Message", { exact: true }).fill("A report that should fail.");
  await page.getByRole("button", { name: "Send feedback" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Feedback could not be saved" })).toBeVisible();
});

test("admin confirms revocation, reports notification status and supports paging", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/admin");
  await expect(page.getByText("Friend 1", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Revoke access" }).first().click();
  await expect.poll(() => writes.some((w) => w.path === "/api/admin/users/2" && w.body.disabled === true)).toBe(true);

  await page.getByRole("button", { name: "Next" }).nth(0).click();
  await expect(page.getByText("Friend 21", { exact: true })).toBeVisible();
  await expect(page.getByText("Friend 1", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Next" }).nth(1).click();
  await expect(page.getByText("22", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next" }).nth(2).click();
  await expect(page.getByText("#21", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Next" }).nth(3).click();
  await expect(page.getByText("Feedback 21", { exact: true })).toBeVisible();

  await expect(page.getByText("Retrying").first()).toBeVisible();
  await expect(page.getByText("Pending notifications: 2")).toBeVisible();
  await page.getByRole("button", { name: "Send test notification" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Test notification queued" })).toBeVisible();

  await installApi(page, { fail: "/api/admin/notifications/test" });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Send test notification" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Could not queue the test notification" })).toBeVisible();
});

test("mobile navigation uses a compact More menu and public legal aliases redirect", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApi(page);
  await page.goto("/app");
  await expect(page.getByRole("button", { name: "More" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole("button", { name: "More" }).click();
  await expect(page.getByRole("link", { name: "Owner administration" })).toBeVisible();
  await page.getByRole("button", { name: "Go to a page…" }).click();
  await expect(page.getByRole("dialog", { name: "Go to a page…" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "More" })).toBeFocused();
  await page.goto("/privacy");
  await expect(page).toHaveURL(/\/legal\/privacy$/);
  await page.goto("/terms");
  await expect(page).toHaveURL(/\/legal\/terms$/);
  await page.goto("/cookies");
  await expect(page).toHaveURL(/\/legal\/cookies$/);
});
