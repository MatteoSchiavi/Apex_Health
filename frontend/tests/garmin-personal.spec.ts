import { expect, test } from "@playwright/test";
import { installApi, today } from "./fixtures";

const legacyDevice = {
  integration_id: 1,
  provider: "garmin",
  status: "active",
  is_main: true,
  last_synced_at: today + "T06:00:00Z",
  connected_at: today + "T00:00:00Z",
  auth_method: "garmin_connect",
};

for (const locale of ["en", "it"] as const) {
  const en = locale === "en";

  test(`Garmin Personal API preserves a legacy connection through failed verification and queues cleanly: ${locale}`, async ({ page }) => {
    await page.setViewportSize({width:390,height:844});
    const { writes } = await installApi(page, { locale });
    let device = legacyDevice;
    let attempts = 0;
    await page.route("**/settings/devices", route => route.fulfill({ json: [device] }));
    await page.route("**/settings/integrations/garmin/personal/connect", route => {
      attempts++;
      const body = route.request().postDataJSON();
      writes.push({ path: "/settings/integrations/garmin/personal/connect", body });
      if (attempts === 1) return route.fulfill({ status: 401, json: { detail: "Invalid key" } });
      device = { ...legacyDevice, auth_method: "personal_api_key" };
      return route.fulfill({ json: { connected: true, backfill_enqueued: false } });
    });

    await page.goto("/app/settings?tab=devices");
    const garmin = page.getByText("Garmin Connect", { exact: true }).locator("xpath=../../..");
    await expect(garmin.getByRole("button", { name: en ? "Use Personal API" : "Usa Personal API" })).toBeVisible();
    await expect(garmin.getByRole("button", { name: en ? "Disconnect" : "Disconnetti" })).toBeVisible();
    await garmin.getByRole("button", { name: en ? "Use Personal API" : "Usa Personal API" }).click();

    const key = page.getByLabel(en ? "Garmin Personal API key" : "Chiave Garmin Personal API");
    await key.fill("  synthetic-private-key  ");
    await page.getByRole("button", { name: en ? "Verify and connect" : "Verifica e collega" }).click();
    await expect(page.getByText(en ? "Garmin could not verify this key." : "Garmin non ha verificato questa chiave.", { exact: false })).toBeVisible();
    await expect(key).toHaveValue("  synthetic-private-key  ");
    await expect(key).toHaveAttribute("type", "password");
    await expect(page.getByText("synthetic-private-key", { exact: true })).toHaveCount(0);
    await expect(garmin.getByRole("button", { name: en ? "Disconnect" : "Disconnetti" })).toBeVisible();
    await expect(garmin.getByRole("button", { name: en ? "Close" : "Chiudi", exact: true })).toBeVisible();

    await page.getByRole("button", { name: en ? "Verify and connect" : "Verifica e collega" }).click();
    await expect(page.getByRole("status")).toContainText(en
      ? "Garmin Personal API connected. Synchronization could not be queued. Choose Sync now to try again."
      : "Garmin Personal API collegata. Non è stato possibile avviare la sincronizzazione. Scegli Sincronizza ora per riprovare.");
    await expect(garmin.getByRole("button", { name: en ? "Sync now" : "Sincronizza ora" })).toBeVisible();
    await expect(page.getByText(en ? "Personal API" : "Personal API", { exact: true })).toBeVisible();
    await expect(key).toHaveCount(0);
    await expect(page.locator("html")).toHaveJSProperty("scrollWidth", 390);
    expect(writes.filter(write => write.path === "/settings/integrations/garmin/personal/connect")).toEqual([
      { path: "/settings/integrations/garmin/personal/connect", body: { api_key: "synthetic-private-key" } },
      { path: "/settings/integrations/garmin/personal/connect", body: { api_key: "synthetic-private-key" } },
    ]);
  });

  test(`friend cannot open Garmin Personal API controls: ${locale}`, async ({ page }) => {
    await installApi(page, { locale, role: "friend" });
    await page.route("**/settings/devices", route => route.fulfill({ json: [legacyDevice] }));
    await page.goto("/app/settings?tab=devices");
    await expect(page.getByText("Garmin Connect", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: en ? "Use Personal API" : "Usa Personal API" })).toHaveCount(0);
    await expect(page.getByLabel(en ? "Garmin Personal API key" : "Chiave Garmin Personal API")).toHaveCount(0);
  });
}
