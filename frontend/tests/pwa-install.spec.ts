import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("install prompt received on dashboard is available in Settings", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Your daily overview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Install app" })).toHaveCount(0);

  const captured = await page.evaluate(() => {
    const event = new Event("beforeinstallprompt", { cancelable: true });
    Object.defineProperties(event, {
      prompt: { value: async () => {} },
      userChoice: {
        value: Promise.resolve({ outcome: "dismissed", platform: "web" }),
      },
    });
    return { dispatched: window.dispatchEvent(event), prevented: event.defaultPrevented };
  });
  expect(captured).toEqual({ dispatched: false, prevented: true });

  await page.locator("aside nav").getByRole("link", { name: "Settings" }).click();
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  await expect(page.getByRole("button", { name: "Install app" })).toBeVisible();
});
