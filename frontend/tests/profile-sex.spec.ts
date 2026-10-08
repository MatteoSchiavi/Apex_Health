import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("signup defaults to male and submits the selected female profile", async ({ page }) => {
  await installApi(page);
  let submitted: Record<string, unknown> | undefined;
  await page.route(url => url.pathname === "/auth/invite/redeem", async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { user_id: 1, role: "friend" } });
  });
  await page.goto("/join");
  await expect(page.getByRole("combobox", { name: "Sex", exact: true })).toHaveValue("male");
  await page.getByRole("combobox", { name: "Sex", exact: true }).selectOption("female");
  await page.getByLabel("Invite code", { exact: true }).fill("a-valid-invite-code");
  await page.getByLabel("Name", { exact: true }).fill("Alex");
  await page.getByLabel("Email", { exact: true }).fill("alex@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-strong-password-9");
  await page.locator('button[type="submit"]').click();
  await expect.poll(() => submitted?.sex).toBe("female");
});

test("settings preserves and saves female profile selection", async ({ page }) => {
  await installApi(page, { sex: "female" });
  await page.goto("/app/settings");
  const select = page.getByRole("combobox", { name: "Sex", exact: true });
  await expect(select).toHaveValue("female");
  await select.selectOption("male");
  await select.locator("xpath=ancestor::form").getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved", { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Sex", exact: true })).toHaveValue("male");
});
