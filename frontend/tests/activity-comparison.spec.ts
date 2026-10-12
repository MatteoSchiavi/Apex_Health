import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

for (const locale of ["en", "it"] as const) {
  test(`comparison context requires review, handles stale save and clears only assertion: ${locale}`, async ({ page }) => {
    await installApi(page, { locale, aiConsent: false });
    const writes: Record<string, unknown>[] = [];
    let staleNextSave = false;
    let revision = "a".repeat(64);
    let assertions: { provider: string; context: Record<string, unknown>; provenance: { asserted_at: string; verified: false } }[] = [];
    await page.route("**/activities/1/comparison-context", async route => {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        writes.push(body);
        if (staleNextSave) {
          staleNextSave = false;
          revision = "c".repeat(64);
          return route.fulfill({ status: 409, json: { detail: "Comparison context changed; reload and review before saving" } });
        }
        expect(body.expected_revision).toBe(revision);
        expect(body.reviewed).toBe(true);
        revision = assertions.length ? "d".repeat(64) : "b".repeat(64);
        assertions = body.context ? [{ provider: "garmin", context: body.context as Record<string, unknown>, provenance: { asserted_at: "2026-10-12T10:00:00Z", verified: false } }] : [];
      }
      return route.fulfill({ json: { activity_id: 1, revision, providers: ["garmin"], assertions,
        recorded_context_providers: [], outdoor_weather_available: false } });
    });
    await page.goto("/app/activities/1");
    const en = locale === "en";
    const routeInput = page.getByLabel(en ? "Route identity" : "Identità del percorso", { exact: true });
    const review = page.getByRole("button", { name: en ? "Review context" : "Rivedi il contesto", exact: true });
    await expect(review).toBeDisabled();
    await routeInput.fill("Measured indoor loop clockwise");
    await page.getByRole("combobox", { name: en ? "Terrain" : "Terreno", exact: true }).selectOption("paved");
    await page.getByRole("combobox", { name: en ? "Setting" : "Ambiente", exact: true }).selectOption("indoor");
    await page.getByRole("combobox", { name: en ? "Time convention" : "Convenzione temporale", exact: true }).selectOption("elapsed");
    await page.getByRole("combobox", { name: en ? "Effort intent" : "Intento dello sforzo", exact: true }).selectOption("easy");
    await review.click();
    expect(writes).toHaveLength(0);
    const save = page.getByRole("button", { name: en ? "Save reviewed context" : "Salva il contesto verificato", exact: true });
    const acknowledge = page.getByRole("checkbox", { name: en ? "I reviewed the route, terrain, setting, time convention and effort intent for this session." : "Ho verificato percorso, terreno, ambiente, convenzione temporale e intento dello sforzo per questa sessione.", exact: true });
    await expect(save).toBeDisabled();
    await acknowledge.check();
    await save.click();
    await expect(routeInput).toHaveValue("Measured indoor loop clockwise");
    expect(writes[0]).toMatchObject({ provider: "garmin", reviewed: true, context: {
      route_id: "Measured indoor loop clockwise", terrain: "paved", indoor: true, effort_type: "easy", time_convention: "elapsed",
    } });
    staleNextSave = true;
    await routeInput.fill("Unsaved changed route");
    await review.click();
    await acknowledge.check();
    await save.click();
    await expect(page.getByRole("alert").filter({ hasText: en ? "The context changed since you opened it" : "Il contesto è cambiato dopo l’apertura" })).toBeVisible();
    await page.getByRole("button", { name: en ? "Reload current context" : "Ricarica il contesto attuale", exact: true }).click();
    await expect(routeInput).toHaveValue("Measured indoor loop clockwise");
    await page.getByRole("button", { name: en ? "Review removal" : "Rivedi la rimozione", exact: true }).click();
    await expect(save).toBeDisabled();
    await acknowledge.check();
    await save.click();
    await expect(routeInput).toHaveValue("");
    expect(writes.at(-1)).toMatchObject({ provider: "garmin", context: null, expected_revision: "c".repeat(64), reviewed: true });
  });
}
