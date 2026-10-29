import { expect, test } from "@playwright/test";
import { installApi, today } from "./fixtures";

for (const locale of ["en", "it"] as const) {
  const en = locale === "en";
  test(`an untouched invited profile still needs athlete context: ${locale}`, async ({ page }) => {
    await installApi(page, { locale });
    await page.route("**/athlete/day?*", route => route.fulfill({ json: {
      date: today, timezone: "UTC", training_focus: [], sessions: [], activities: [], legacy_gym_sessions: [], state: "no_plan", totals: {},
      planning_context: { state: "no_profile", profile_state: "none", profile_revision: 0, active_plan_id: null, draft_id: null, draft_document_id: null },
    } }));
    await page.goto("/app");
    await page.getByTestId("overview-setup").locator("summary").click();
    const profile = page.locator('a[href="/app/settings?tab=profile"]').filter({ hasText: en ? "Complete your profile" : "Completa il profilo" });
    await expect(profile).toContainText(en ? "Add your training focus, goal, or context" : "Aggiungi il tuo sport, obiettivo o contesto");
    await expect(profile).not.toContainText("✓");
    await profile.click();
    await expect(page.getByRole("tab", { name: en ? "Profile" : "Profilo", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("checkbox", { name: en ? "Running" : "Corsa", exact: true })).not.toBeChecked();
  });

  test(`canceling athlete context deletion retains saved and unsaved details: ${locale}`, async ({ page }) => {
    const { writes } = await installApi(page, { locale });
    await page.goto("/app/settings?tab=profile");
    const running = page.getByRole("checkbox", { name: en ? "Running" : "Corsa", exact: true });
    await running.check();
    await page.getByRole("button", { name: en ? "Complete later" : "Completa più avanti", exact: true }).click();
    const notes = page.locator("textarea[maxlength='8000']");
    await notes.fill("My saved training context.");
    const save = page.getByRole("button", { name: en ? "Save athlete context" : "Salva il contesto sportivo", exact: true });
    await save.click();
    await expect(page.getByText(en ? "Athlete context saved." : "Contesto sportivo salvato.", { exact: false })).toBeVisible();
    await notes.fill("My unsaved training context.");
    await page.getByRole("button", { name: en ? "Delete athlete context" : "Elimina il contesto sportivo", exact: true }).click();
    const review = page.getByRole("region", { name: en ? "Delete your athlete context?" : "Eliminare il tuo contesto sportivo?", exact: true });
    await expect(review).toBeVisible();
    await expect(review).toContainText(en ? "This cannot be undone." : "Questa operazione è irreversibile.");
    await expect(save).toBeDisabled();
    await expect(notes).toHaveValue("My unsaved training context.");
    expect(writes.filter(write => write.path === "/athlete/profile")).toHaveLength(1);
    await review.getByRole("button", { name: en ? "Cancel" : "Annulla", exact: true }).click();
    await expect(review).toBeHidden();
    await expect(notes).toHaveValue("My unsaved training context.");
    await expect(running).toBeChecked();
    await expect(save).toBeEnabled();
    expect(await page.evaluate(async () => (await fetch("/athlete/profile")).json())).toMatchObject({
      training_focus: ["running"], context: { athlete_notes: "My saved training context." },
    });
  });
}

for (const profileState of ["incomplete", "ready"] as const) {
  test(`setup follows saved athlete readiness ${profileState} without requiring optional details`, async ({ page }) => {
    await installApi(page);
    let dayReads = 0;
    await page.route("**/athlete/day?*", route => {
      dayReads++;
      return route.fulfill({ json: {
        date: today, timezone: "UTC", training_focus: profileState === "ready" ? ["running"] : [], sessions: [], activities: [], legacy_gym_sessions: [], state: "no_plan", totals: {},
        planning_context: { state: profileState === "ready" ? "profile_ready" : "profile_incomplete", profile_state: profileState, profile_revision: 1, active_plan_id: null, draft_id: null, draft_document_id: null },
      } });
    });
    await page.goto("/app");
    await page.getByTestId("overview-setup").locator("summary").click();
    const profile = page.locator('a[href="/app/settings?tab=profile"]').filter({ hasText: "Complete your profile" });
    await expect(profile).toContainText(profileState === "ready" ? "Profile details available" : "Add your training focus, goal, or context");
    if (profileState === "ready") await expect(profile).toContainText("✓");
    else await expect(profile).not.toContainText("✓");
    expect(dayReads).toBe(1);
  });
}

test("deletion waits for confirmation and server success, and a failed attempt preserves edits", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app/settings?tab=profile");
  await page.getByRole("checkbox", { name: "Running", exact: true }).check();
  await page.getByRole("button", { name: "Complete later", exact: true }).click();
  const notes = page.locator("textarea[maxlength='8000']");
  await notes.fill("Saved context.");
  await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
  await notes.fill("Keep my latest draft if deletion fails.");
  let attempts = 0;
  let finish: () => void = () => {};
  await page.route("**/athlete/profile", async route => {
    if (route.request().method() !== "DELETE") return route.fallback();
    attempts++;
    if (attempts === 1) return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    await new Promise<void>(resolve => { finish = resolve; });
    return route.fallback();
  });
  await page.getByRole("button", { name: "Delete athlete context", exact: true }).click();
  const review = page.getByRole("region", { name: "Delete your athlete context?", exact: true });
  expect(attempts).toBe(0);
  await review.getByRole("button", { name: "Yes, delete athlete context", exact: true }).click();
  await expect(review.getByRole("alert")).toContainText("Your saved context and unsaved edits are still available.");
  await expect(notes).toHaveValue("Keep my latest draft if deletion fails.");
  expect(await page.evaluate(async () => (await fetch("/athlete/profile")).json())).toMatchObject({
    training_focus: ["running"], context: { athlete_notes: "Saved context." },
  });
  await review.getByRole("button", { name: "Yes, delete athlete context", exact: true }).click();
  await expect(review.getByRole("button", { name: "Deleting athlete context…", exact: true })).toBeDisabled();
  await expect(notes).toBeDisabled();
  await expect(notes).toHaveValue("Keep my latest draft if deletion fails.");
  finish();
  await expect(review).toBeHidden();
  await expect(notes).toHaveValue("");
  await expect(page.getByRole("checkbox", { name: "Running", exact: true })).not.toBeChecked();
  await expect(page.getByText("Athlete context deleted.", { exact: false })).toBeVisible();
  expect(writes.filter(write => write.path === "/athlete/profile")).toHaveLength(2);
});
