import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("login sends the Remember me choice", async ({ page }) => {
  await installApi(page, { locale: "en" });
  const loginBodies: Record<string, unknown>[] = [];
  await page.route("**/auth/login", async (route) => {
    loginBodies.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true } });
  });

  await page.goto("/login");
  const rememberMe = page.getByRole("checkbox", {
    name: "Remember me on this device",
  });
  await expect(rememberMe).not.toBeChecked();

  await page.getByLabel("Email").fill("athlete@example.com");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);

  await page.goto("/login");
  await page.getByLabel("Email").fill("athlete@example.com");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await rememberMe.check();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);

  expect(loginBodies.map((body) => body.remember_me)).toEqual([false, true]);
});
