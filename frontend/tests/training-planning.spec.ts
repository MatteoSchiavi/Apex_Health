import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi } from "./fixtures";

const session = (date: string | null = null) => ({ date, discipline: "running", session_type: "Easy run", duration_min: 30, distance_m: null, start_time: null, description: "Easy conversational effort", intensity_targets: {}, protected: false });
const structure = (count = 12) => ({ title: "Autumn training", starts_on: null, ends_on: null, weekly_structure: "Review actual training dates", sessions: Array.from({ length: count }, () => session()), ambiguities: ["Confirm the intended calendar dates"], protected: false });
const source = { id: 4, filename: "coach-plan.txt", content_hash: "a".repeat(64), status: "confirmed", revision: 2, excerpt: "Twelve training sessions; no calendar dates were supplied." };

async function legacyPlanApi(page: Page, options: { count?: number; locale?: "en" | "it" } = {}) {
  await installApi(page, { aiConsent: false, locale: options.locale ?? "en" });
  let draft = { id: 8, document_id: 4, document_revision: 2, version: 1, structure: structure(options.count), payload_hash: "b".repeat(64), status: "draft", confirmed_at: null };
  const writes: { path: string; body: any }[] = [];
  await page.route("**/lab/documents", route => route.fulfill({ json: [source] }));
  await page.route("**/lab/plan-drafts", route => route.fulfill({ json: [draft] }));
  await page.route("**/lab/documents/4/plan-drafts", route => {
    const body = route.request().postDataJSON(); writes.push({ path: "save", body });
    draft = { ...draft, version: draft.version + 1, structure: body.structure, payload_hash: "c".repeat(64) };
    return route.fulfill({ json: draft });
  });
  await page.route("**/lab/plan-drafts/8/confirm", route => {
    writes.push({ path: "activate", body: route.request().postDataJSON() });
    draft = { ...draft, status: "confirmed" };
    return route.fulfill({ json: { plan_id: 12, draft } });
  });
  return writes;
}

test("Training makes all twelve missing dates actionable and activates only the explicitly reviewed schedule", async ({ page }) => {
  const writes = await legacyPlanApi(page);
  await page.goto("/app/training?tab=planning#document-4");
  await expect(page.getByRole("heading", { name: "Your training plan", exact: true })).toBeVisible();
  const requirements = page.getByRole("region", { name: "Before you can activate this plan", exact: true });
  await expect(requirements.getByText("Choose the plan start date.", { exact: true })).toBeVisible();
  await expect(requirements.getByText("Choose the plan end date.", { exact: true })).toBeVisible();
  await expect(requirements.getByText("Choose actual dates for 12 workouts:")).toBeVisible();
  await expect(requirements.getByText(/12\. Running/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review what Apex understood", exact: true })).toHaveCount(0);
  const activate = page.getByRole("button", { name: "Confirm structure and activate plan", exact: true });
  await page.getByRole("checkbox", { name: /I have reviewed these workouts/ }).check();
  await expect(activate).toBeDisabled();
  expect(writes).toEqual([]);
  await page.getByRole("button", { name: "Edit workouts and dates", exact: true }).click();
  await expect(page.getByLabel("Workout description", { exact: true }).first()).toBeHidden();
  const dates = page.getByLabel("Date (optional for a draft)", { exact: true });
  await expect(dates).toHaveCount(12);
  await expect(dates.first()).toHaveValue("");
  await page.getByLabel("Start date", { exact: true }).fill("2026-10-19");
  await page.getByLabel("End date", { exact: true }).fill("2026-10-30");
  for (let index = 0; index < 12; index++) await dates.nth(index).fill(`2026-10-${19 + index}`);
  await page.getByRole("button", { name: "Save reviewable structure", exact: true }).click();
  await expect(activate).toBeDisabled();
  expect(writes.map(item => item.path)).toEqual(["save"]);
  expect(writes[0].body.structure.sessions.map((item: any) => item.date)).toEqual(Array.from({ length: 12 }, (_, index) => `2026-10-${19 + index}`));
  await page.getByRole("checkbox", { name: /I have reviewed these workouts/ }).check();
  await activate.click();
  await expect(page.getByRole("link", { name: "Open today’s training", exact: true })).toBeVisible();
  expect(writes.filter(item => item.path === "activate")).toEqual([{ path: "activate", body: { payload_hash: "c".repeat(64), ambiguities_reviewed: true } }]);
});

test("date corrections show invalid ranges and out-of-range sessions before writing a draft", async ({ page }) => {
  const writes = await legacyPlanApi(page, { count: 1 });
  await page.goto("/app/training?tab=planning#document-4");
  await page.getByRole("button", { name: "Edit workouts and dates", exact: true }).click();
  const save = page.getByRole("button", { name: "Save reviewable structure", exact: true });
  await page.getByLabel("Start date", { exact: true }).fill("2026-10-20");
  await page.getByLabel("End date", { exact: true }).fill("2026-10-19");
  await expect(page.getByText("The end date must be on or after the start date.", { exact: true })).toBeVisible();
  await expect(save).toBeDisabled();
  await page.getByLabel("End date", { exact: true }).fill("2026-10-22");
  await page.getByLabel("Date (optional for a draft)", { exact: true }).fill("2026-10-23");
  await expect(page.getByText("Move workouts 1 inside the plan’s date range, or adjust the range.", { exact: true })).toBeVisible();
  await expect(save).toBeDisabled();
  expect(writes).toEqual([]);
  await page.getByLabel("Date (optional for a draft)", { exact: true }).fill("2026-10-21");
  await expect(save).toBeEnabled();
});

test("import deep links open plan review directly while saved profile details stay collapsed", async ({ page }) => {
  await installApi(page, { aiConsent: false });
  await page.route("**/lab/documents", route => route.fulfill({ json: [{ ...source, coach_eligible: false }] }));
  await page.route("**/lab/athlete-imports", route => route.fulfill({ json: [{ id: 1, document_id: 4, document_revision: 2, version: 1, payload_hash: "b".repeat(64), extraction_method: "manual_review", source_text: source.excerpt, category_hints: ["weekly"], receipts: { profile: { fields: [], profile_revision: 1 } }, proposal: { profile: { training_focus: null, context: {} }, weekly: null, dated: structure(1), sources: [], issues: [] } }] }));
  await page.goto("/app/training?tab=planning#document-4");
  await expect(page.getByRole("heading", { name: "Review your imported plan", exact: true })).toBeVisible();
  await expect(page.getByText("Your athlete profile is saved. Review the training plan and its dates separately.", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Start date", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview dated plan", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save review for later", exact: true })).toBeVisible();
  await expect(page.getByLabel("Read or paste the text to analyze", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save to my athlete profile", exact: true })).toBeHidden();
});

test("template deep links retain explicit date choice and a separate preview before activation", async ({ page }) => {
  await installApi(page, { aiConsent: false });
  const weekly = { title: "Two easy runs", notes: "Conversational effort", rows: [{ ...session(), id: "row-1", day: 0 }] };
  await page.route("**/athlete/templates", route => route.fulfill({ json: [{ id: 31, revision: 1, source_document_id: 4, source_document_revision: 2, import_draft_id: 1, structure: weekly }] }));
  const writes: any[] = [];
  await page.route("**/athlete/templates/31/preview", route => {
    const body = route.request().postDataJSON(); writes.push(body);
    return route.fulfill({ json: { id: 51, document_id: null, template_id: 31, template_revision: 1, version: 1, structure: { ...structure(1), starts_on: body.starts_on, ends_on: body.ends_on, sessions: [session(body.starts_on)], ambiguities: [] }, payload_hash: "d".repeat(64), status: "draft", confirmed_at: null } });
  });
  await page.goto("/app/training?tab=planning&date=2024-03-05#template-31");
  await expect(page).toHaveURL(/date=2024-03-05#template-31$/);
  await expect(page.getByLabel("Start date", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: "Preview calendar", exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
  await page.getByLabel("Start date", { exact: true }).fill("2026-10-19");
  await page.getByLabel("End date", { exact: true }).fill("2026-10-25");
  await page.getByRole("button", { name: "Preview calendar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Activate this reviewed plan", exact: true })).toBeVisible();
  expect(writes).toEqual([{ expected_revision: 1, starts_on: "2026-10-19", ends_on: "2026-10-25" }]);
});

test("Italian planning remains readable and accessible on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await legacyPlanApi(page, { count: 2, locale: "it" });
  await page.goto("/app/training?tab=planning#document-4");
  await expect(page.getByRole("heading", { name: "Il tuo piano di allenamento", exact: true })).toBeVisible();
  await expect(page.getByText("Scegli date reali per 2 allenamenti:")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});


test("a saved plan auto-selection and planning links retain the selected day without inferring workout dates", async ({ page }) => {
  await legacyPlanApi(page, { count: 1 });
  const writes: string[] = [];
  page.on("request", request => { if (!["GET", "HEAD"].includes(request.method())) writes.push(request.url()); });
  await page.goto("/app/training?tab=planning&date=2024-03-05");
  await expect(page).toHaveURL(/\/app\/training\?tab=planning&date=2024-03-05#document-4$/);
  const review = page.getByRole("link", { name: "Continue plan review", exact: true });
  await expect(review).toHaveAttribute("href", "/app/training?tab=planning&date=2024-03-05#document-4");
  const importPlan = page.getByRole("link", { name: "Import a plan", exact: true });
  await expect(importPlan).toHaveAttribute("href", "/app/training?tab=planning&date=2024-03-05#import");
  await importPlan.click();
  await expect(page).toHaveURL(/date=2024-03-05#import$/);
  await review.click();
  await expect(page).toHaveURL(/date=2024-03-05#document-4$/);
  await page.getByRole("button", { name: "Edit workouts and dates", exact: true }).click();
  await expect(page.getByLabel("Start date", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("End date", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Date (optional for a draft)", { exact: true })).toHaveValue("");
  expect(writes).toEqual([]);
});
