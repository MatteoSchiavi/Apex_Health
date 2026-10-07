import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

const device = {
  id: 42,
  name: "Alpha iPhone",
  created_at: "2026-10-07T10:00:00Z",
  last_used_at: "2026-10-07T12:00:00Z",
  revoked_at: null as string | null,
  absolute_expires_at: "2099-01-01T00:00:00Z",
  checkpoint: 12,
  last_success_at: "2026-10-07T12:00:00Z",
};

test("HealthKit creates an ephemeral one-time code and labels native validation pending", async ({ page }) => {
  await installApi(page);
  await page.route("**/healthkit/devices", (route) => route.fulfill({ json: [] }));
  let created = 0;
  await page.route("**/healthkit/pairings", async (route) => {
    expect(route.request().method()).toBe("POST");
    created += 1;
    await route.fulfill({ json: { code: "ONE-TIME-ALPHA-CODE", expires_at: new Date(Date.now() + 600_000).toISOString() } });
  });
  await page.goto("/app/settings?tab=devices");
  const panel = page.getByTestId("healthkit-panel");
  await expect(panel.getByText("Development only", { exact: true })).toBeVisible();
  await expect(panel.getByText(/physical-device validation are still pending/i)).toBeVisible();
  await panel.getByRole("button", { name: "Create pairing code" }).click();
  await expect(panel.getByTestId("healthkit-pairing-code")).toHaveText("ONE-TIME-ALPHA-CODE");
  expect(created).toBe(1);
  const stored = await page.evaluate(() => [JSON.stringify(localStorage), JSON.stringify(sessionStorage), document.cookie].join(" "));
  expect(stored).not.toContain("ONE-TIME-ALPHA-CODE");
  await panel.getByRole("button", { name: "Hide code" }).click();
  await expect(panel.getByTestId("healthkit-pairing-code")).toHaveCount(0);
});

test("HealthKit device revocation refreshes the list and removes the action", async ({ page }) => {
  await installApi(page);
  let revoked = false;
  await page.route("**/healthkit/devices", (route) => route.fulfill({ json: [{ ...device, revoked_at: revoked ? "2026-10-07T13:00:00Z" : null }] }));
  await page.route("**/healthkit/devices/42", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    revoked = true;
    await route.fulfill({ status: 204 });
  });
  await page.goto("/app/settings?tab=devices");
  const row = page.getByTestId("healthkit-panel").getByRole("article", { name: "Alpha iPhone" });
  await expect(row.getByText("12", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Revoke device" }).click();
  await expect(row.getByText("Revoked", { exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Revoke device" })).toHaveCount(0);
});

test("expired HealthKit pairing code is cleared automatically", async ({ page }) => {
  await page.clock.install();
  await installApi(page);
  await page.route("**/healthkit/devices", (route) => route.fulfill({ json: [] }));
  await page.route("**/healthkit/pairings", async (route) => {
    const expiresAt = await page.evaluate(() => new Date(Date.now() + 2000).toISOString());
    await route.fulfill({ json: { code: "SHORT-LIVED-CODE", expires_at: expiresAt } });
  });
  await page.goto("/app/settings?tab=devices");
  const panel = page.getByTestId("healthkit-panel");
  await panel.getByRole("button", { name: "Create pairing code" }).click();
  await expect(panel.getByTestId("healthkit-pairing-code")).toHaveText("SHORT-LIVED-CODE");
  await page.clock.runFor(4000);
  await expect(panel.getByTestId("healthkit-pairing-code")).toHaveCount(0);
  await expect(panel.getByText("Code expired. Create a new one.", { exact: true })).toBeVisible();
});

test("HealthKit pairing failures never display raw server content", async ({ page }) => {
  await installApi(page);
  await page.route("**/healthkit/devices", (route) => route.fulfill({ json: [] }));
  await page.route("**/healthkit/pairings", (route) => route.fulfill({ status: 500, json: { detail: "raw-sensitive-provider-content" } }));
  await page.goto("/app/settings?tab=devices");
  const panel = page.getByTestId("healthkit-panel");
  await panel.getByRole("button", { name: "Create pairing code" }).click();
  await expect(panel.getByText("The request could not complete. Please try again.", { exact: true })).toBeVisible();
  await expect(page.getByText("raw-sensitive-provider-content", { exact: true })).toHaveCount(0);
});

test("HealthKit pairing controls use Italian translations", async ({ page }) => {
  await installApi(page, { locale: "it" });
  await page.route("**/healthkit/devices", (route) => route.fulfill({ json: [] }));
  await page.goto("/app/settings?tab=devices");
  const panel = page.getByTestId("healthkit-panel");
  await expect(panel.getByText("Solo sviluppo", { exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Crea codice di abbinamento" })).toBeVisible();
});
