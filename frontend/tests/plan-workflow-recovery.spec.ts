import { expect, test, type Page } from "@playwright/test";
import { installApi } from "./fixtures";
import type { PlanDraft } from "../src/features/athlete/importTypes";

const source = { id: 4, filename: "reviewed-plan.txt", content_hash: "a".repeat(64), status: "confirmed", revision: 2, excerpt: "One explicitly dated easy run." };
const originalDraft = (): PlanDraft => ({
  id: 8, document_id: 4, document_revision: 2, version: 1, payload_hash: "b".repeat(64), status: "draft", confirmed_at: null,
  structure: { title: "Reviewed training", starts_on: "2026-10-19", ends_on: "2026-10-25", weekly_structure: "",
    sessions: [{ date: "2026-10-19", discipline: "running", session_type: "Easy run", duration_min: 30, distance_m: null, start_time: null, description: "Conversational effort", intensity_targets: {}, protected: false }], ambiguities: [], protected: false },
});

async function planFixture(page: Page, options: { locale?: "en" | "it"; theme?: "light" | "dark" } = {}) {
  await installApi(page, { aiConsent: false, ...options });
  const state = { draft: originalDraft(), failRead: "", failSave: false, failSports: false, writes: [] as { path: string; body: Record<string, unknown> }[] };
  for (const path of ["/lab/documents", "/lab/plan-drafts", "/athlete/templates"]) {
    await page.route(`**${path}`, route => route.fulfill({ status: state.failRead === path ? 503 : 200,
      json: state.failRead === path ? { detail: "Synthetic read failure" } : path === "/lab/documents" ? [source] : path === "/lab/plan-drafts" ? [state.draft] : [] }));
  }
  await page.route("**/athlete/disciplines", route => route.fulfill({ status: state.failSports ? 503 : 200,
    json: state.failSports ? { detail: "Synthetic sports failure" } : [{ name: "running" }] }));
  await page.route("**/lab/documents/4/plan-drafts", route => {
    const body = route.request().postDataJSON();
    state.writes.push({ path: "save", body });
    if (state.failSave) return route.fulfill({ status: 503, json: { detail: "Synthetic save failure" } });
    state.draft = { ...state.draft, structure: body.structure, version: state.draft.version + 1, payload_hash: "c".repeat(64) };
    return route.fulfill({ json: state.draft });
  });
  await page.route("**/lab/plan-drafts/8/confirm", route => {
    state.writes.push({ path: "activate", body: route.request().postDataJSON() });
    state.draft = { ...state.draft, status: "confirmed" };
    return route.fulfill({ json: { draft: state.draft } });
  });
  return state;
}

async function refreshAfterReconnect(page: Page) {
  // Query reads become stale after a minute; reconnect exercises their normal
  // background refresh without navigating away from the unsaved editor.
  await page.clock.fastForward(61_000);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("offline"));
    window.dispatchEvent(new Event("online"));
  });
}

for (const scenario of [
  { path: "/lab/documents", locale: "it", theme: "dark", width: 390, edit: "Modifica allenamenti e date", title: "Titolo del piano", retry: "Riprova", error: "Non è stato possibile aggiornare i piani salvati." },
  { path: "/athlete/templates", locale: "en", theme: "light", width: 1440, edit: "Edit workouts and dates", title: "Plan title", retry: "Retry", error: "Saved plans could not be refreshed." },
] as const) {
  test(`unsaved plan survives a failed ${scenario.path} refresh and retry in ${scenario.locale}`, async ({ page }) => {
    const state = await planFixture(page, scenario);
    await page.setViewportSize({ width: scenario.width, height: 900 });
    await page.clock.install();
    await page.goto("/app/training?tab=planning&date=2026-10-19#document-4");
    await page.getByRole("button", { name: scenario.edit, exact: true }).click();
    const title = page.getByLabel(scenario.title, { exact: true });
    await title.fill("Keep my unsaved plan corrections");
    state.failRead = scenario.path;
    await refreshAfterReconnect(page);
    await expect(page.getByRole("alert").filter({ hasText: scenario.error })).toBeVisible();
    await expect(title).toHaveValue("Keep my unsaved plan corrections");
    expect(state.writes).toEqual([]);
    state.failRead = "";
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === scenario.path && response.status() === 200);
    await page.getByRole("button", { name: scenario.retry, exact: true }).click();
    await refreshed;
    await expect(page.getByRole("alert").filter({ hasText: scenario.error })).toHaveCount(0);
    await expect(title).toHaveValue("Keep my unsaved plan corrections");
    await expect(page).toHaveURL(/date=2026-10-19#document-4$/);
    expect(state.writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("a failed sport read can be retried without restarting the review or inventing dates", async ({ page }) => {
  const state = await planFixture(page);
  state.failSports = true;
  await page.goto("/app/training?tab=planning#document-4");
  await page.getByRole("button", { name: "Edit workouts and dates", exact: true }).click();
  const title = page.getByLabel("Plan title", { exact: true });
  await title.fill("Keep corrections while sports are unavailable");
  await expect(page.getByRole("button", { name: "Save reviewable structure", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Retry plan details", exact: true })).toBeVisible();
  state.failSports = false;
  await page.getByRole("button", { name: "Retry plan details", exact: true }).click();
  await expect(title).toHaveValue("Keep corrections while sports are unavailable");
  await expect(page.getByLabel("Date (optional for a draft)", { exact: true })).toHaveValue("2026-10-19");
  await expect(page.getByRole("button", { name: "Save reviewable structure", exact: true })).toBeEnabled();
  expect(state.writes).toEqual([]);
});

test("a failed draft save retains corrections and retries only when the athlete saves again", async ({ page }) => {
  const state = await planFixture(page);
  await page.goto("/app/training?tab=planning#document-4");
  await page.getByRole("button", { name: "Edit workouts and dates", exact: true }).click();
  await page.getByLabel("Plan title", { exact: true }).fill("My corrected plan");
  await page.getByLabel("Date (optional for a draft)", { exact: true }).fill("2026-10-21");
  state.failSave = true;
  const save = page.getByRole("button", { name: "Save reviewable structure", exact: true });
  await save.click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Plan title", { exact: true })).toHaveValue("My corrected plan");
  await expect(page.getByLabel("Date (optional for a draft)", { exact: true })).toHaveValue("2026-10-21");
  expect(state.writes).toHaveLength(1);
  state.failSave = false;
  await save.click();
  await expect(page.getByRole("button", { name: "Confirm structure and activate plan", exact: true })).toBeDisabled();
  expect(state.writes).toHaveLength(2);
  expect(state.writes[1]).toEqual(state.writes[0]);
  expect(state.writes[1].body).toMatchObject({ expected_document_revision: 2, use_ai: false,
    structure: { title: "My corrected plan", sessions: [{ date: "2026-10-21" }] } });
});

test("a changed draft requires fresh agreement and activation uses exactly the newly reviewed hash", async ({ page }) => {
  const state = await planFixture(page);
  await page.clock.install();
  await page.goto("/app/training?tab=planning#document-4");
  const agreement = page.getByRole("checkbox", { name: /I have reviewed these workouts/ });
  await agreement.check();
  const activate = page.getByRole("button", { name: "Confirm structure and activate plan", exact: true });
  await expect(activate).toBeEnabled();
  state.draft = { ...state.draft, version: 2, payload_hash: "d".repeat(64), structure: { ...state.draft.structure, title: "Updated training dates",
    sessions: [{ ...state.draft.structure.sessions[0], date: "2026-10-22" }] } };
  await refreshAfterReconnect(page);
  await expect(page.getByRole("region", { name: "Existing training plan", exact: true }).getByRole("heading", { name: "Updated training dates", exact: true })).toBeVisible();
  await expect(agreement).not.toBeChecked();
  await expect(activate).toBeDisabled();
  await expect(page.getByRole("status").filter({ hasText: "This plan changed since you reviewed it." })).toBeVisible();
  expect(state.writes).toEqual([]);
  await agreement.check();
  await activate.click();
  await expect(page.getByRole("link", { name: "Open today’s training", exact: true })).toBeVisible();
  expect(state.writes).toEqual([{ path: "activate", body: { payload_hash: "d".repeat(64), ambiguities_reviewed: true } }]);
});
