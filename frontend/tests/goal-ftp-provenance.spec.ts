import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

for (const locale of ["en", "it"] as const) {
  test(`explicit goal and tested FTP review persist without plan activation: ${locale}`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, aiConsent: false });
    await page.goto("/app/settings?tab=profile");
    await page.getByLabel(locale === "en" ? "Cycling" : "Ciclismo", { exact: true }).check();
    await page.getByRole("button", { name: locale === "en" ? "Complete later" : "Completa più avanti", exact: true }).click();
    await page.locator("summary").filter({ hasText: locale === "en" ? "Optional details" : "Dettagli facoltativi" }).click();
    await page.getByRole("combobox", {name:locale === "en" ? "Goal measurement" : "Misura dell’obiettivo", exact: true}).selectOption("best_power_w");
    const save = page.getByRole("button", { name: locale === "en" ? "Save athlete context" : "Salva il contesto sportivo", exact: true });
    await expect(save).toBeDisabled();
    await page.getByLabel(locale === "en" ? "Target value" : "Valore dell’obiettivo", { exact: true }).fill("300");
    await page.getByLabel(locale === "en" ? "Power duration (seconds)" : "Durata della potenza (secondi)", { exact: true }).fill("300");
    await page.getByLabel(locale === "en" ? "FTP (watts)" : "FTP (watt)", { exact: true }).fill("250");
    await page.getByLabel(locale === "en" ? "FTP measurement date" : "Data di misurazione FTP", { exact: true }).fill("2026-10-12");
    await page.getByRole("combobox", {name:locale === "en" ? "FTP source" : "Origine FTP", exact: true}).selectOption("tested");
    await page.getByLabel(locale === "en" ? "FTP methodology" : "Metodo FTP", { exact: true }).fill("Recorded result");
    await page.getByLabel(locale === "en" ? "Test protocol" : "Protocollo del test", { exact: true }).fill("Ramp test reported by athlete");
    await page.getByLabel(locale === "en" ? "I confirm this dated FTP value." : "Confermo questo valore FTP e la relativa data.", { exact: true }).check();
    await save.click();
    const write = writes.findLast(w => w.path === "/athlete/profile");
    expect(write?.body).toMatchObject({context:{ftp:{source:"tested",watts:250,protocol:"Ramp test reported by athlete"},focuses:{cycling:{measurable_goal:{metric:"best_power_w",target:300,duration_s:300}}}}});
    expect(writes.some(w => w.path.includes("confirm-plan"))).toBe(false);
  });
}
