import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi } from "./fixtures";
import type { ImportProposal } from "../src/features/athlete/importTypes";

const sourceText = "I run for health. Tuesday is an easy run; Thursday is a ride. Autumn goals are flexible.";
const emptyProposal = (): ImportProposal => ({ profile: { training_focus: null, context: {} }, weekly: null, dated: null, issues: [], sources: [] });
const workout = (id: string, day: number, discipline = "running") => ({ id, day, discipline, session_type: "Easy", duration_min: null, distance_m: null, start_time: null, description: "From the source", intensity_targets: {}, protected: false });

async function importApi(page: Page, options: { proposal?: ImportProposal; ai?: boolean; locale?: "en" | "it"; pdfText?: string | null; conflict?: "review" | "profile" | "activation"; aiFailure?: boolean; holdProfile?: boolean } = {}) {
  await installApi(page, { aiConsent: options.ai ?? false, locale: options.locale ?? "en" });
  let doc: any = null;
  let imports: any[] = [];
  let templates: any[] = [];
  let profile: any = { training_focus: [], context: {}, revision: 0 };
  let draft: any = null;
  const writes: { path: string; method: string; body: any }[] = [];
  let releaseProfile: (() => void) | null = null;
  await page.route("**/athlete/profile", route => route.fulfill({ json: profile }));
  await page.route("**/lab/documents**", async route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method === "GET") return route.fulfill({ json: doc ? [doc] : [] });
    if (path === "/lab/documents") {
      writes.push({ path: route.request().url(), method, body: route.request().postData() });
      const pdf = route.request().postData()?.includes("application/pdf");
      doc = { id: 21, filename: pdf ? "athlete.pdf" : "athlete-information.txt", content_hash: "a".repeat(64), revision: 1, status: "unconfirmed", excerpt: pdf ? options.pdfText ?? null : sourceText, coach_eligible: false, extraction_state: pdf && !options.pdfText ? "manual_paste_required" : "text_ready" };
      return route.fulfill({ status: 201, json: doc });
    }
    const body = route.request().postDataJSON(); writes.push({ path, method, body });
    doc = { ...doc, revision: 2, status: "confirmed", excerpt: body.reviewed_text };
    return route.fulfill({ json: doc });
  });
  await page.route("**/lab/athlete-imports**", async route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method === "GET") return route.fulfill({ json: /\/\d+$/.test(path) ? imports.find(item => item.id === Number(path.split("/").at(-1))) : imports });
    const body = route.request().postDataJSON(); writes.push({ path, method, body });
    if (path === "/lab/athlete-imports") {
      if (options.aiFailure && body.use_ai) return route.fulfill({ status: 429, json: { detail: "AI budget exhausted. Use manual review." } });
      const current = { id: 1, document_id: 21, document_revision: 2, version: 1, proposal: structuredClone(options.proposal ?? emptyProposal()), payload_hash: "b".repeat(64), extraction_method: body.use_ai ? "ai_review_required" : "manual_review", receipts: {}, source_text: doc.excerpt, category_hints: ["profile", "weekly", "goals"] };
      imports = [current]; return route.fulfill({ status: 201, json: current });
    }
    const original = imports.find(item => item.id === Number(path.split("/")[3]));
    if (method === "PUT") {
      if (options.conflict === "review") return route.fulfill({ status: 409, json: { detail: "Source changed" } });
      const next = { ...original, id: original.id + 1, version: original.version + 1, proposal: body.proposal, payload_hash: "c".repeat(64), receipts: {} };
      imports.unshift(next); return route.fulfill({ json: next });
    }
    if (path.endsWith("/profile-confirm")) {
      if (options.holdProfile) await new Promise<void>(resolve => { releaseProfile = resolve; });
      if (options.conflict === "profile") return route.fulfill({ status: 409, json: { detail: "Profile changed" } });
      for (const field of body.fields) {
        if (field === "training_focus") profile.training_focus = original.proposal.profile.training_focus;
        else profile.context[field.replace("context.", "")] = original.proposal.profile.context[field.replace("context.", "")];
      }
      profile.revision++;
      original.receipts.profile = { fields: body.fields, profile_revision: profile.revision };
      return route.fulfill({ json: { import: original, profile } });
    }
    if (path.endsWith("/template-confirm")) {
      const template = { id: 31, revision: 1, source_document_id: 21, source_document_revision: 2, import_draft_id: original.id, structure: original.proposal.weekly };
      templates = [template]; original.receipts.template = { template_id: 31, revision: 1 };
      return route.fulfill({ json: { import: original, template } });
    }
    if (path.endsWith("/dated-plan")) {
      draft = { id: 51, document_id: 21, document_revision: 2, version: 1, payload_hash: "d".repeat(64), status: "draft", confirmed_at: null, structure: original.proposal.dated };
      original.receipts.dated_plan = { draft_id: 51 };
      return route.fulfill({ json: draft });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.route("**/athlete/templates**", route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method === "GET") return route.fulfill({ json: templates });
    const body = route.request().postDataJSON(); writes.push({ path, method, body });
    const weekly = templates[0].structure;
    draft = { id: 51, document_id: null, template_id: 31, template_revision: 1, version: 1, payload_hash: "d".repeat(64), status: "draft", confirmed_at: null, structure: { title: weekly.title, starts_on: body.starts_on, ends_on: body.ends_on, weekly_structure: weekly.notes, protected: false, ambiguities: [], sessions: weekly.rows.map((row: any, index: number) => { const { id, day, ...fields } = row; return { ...fields, date: index === 0 ? "2026-10-13" : "2026-10-15" }; }) } };
    return route.fulfill({ json: draft });
  });
  await page.route("**/lab/plan-drafts", route => route.fulfill({ json: draft ? [draft] : [] }));
  await page.route("**/lab/plan-drafts/51/confirm", route => {
    const path = new URL(route.request().url()).pathname;
    const body = route.request().postDataJSON(); writes.push({ path, method: "POST", body });
    if (options.conflict === "activation") return route.fulfill({ status: 409, json: { detail: "Draft changed" } });
    draft = { ...draft, status: "confirmed" }; return route.fulfill({ json: { draft, plan_id: 61 } });
  });
  return { writes, finishProfile: () => releaseProfile?.() };
}

async function analyzePaste(page: Page) {
  await page.goto("/app/lab?tab=documents");
  await page.getByLabel("Read or paste the text to analyze", { exact: true }).fill(sourceText);
  await page.getByRole("button", { name: "Analyze document", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review what Apex understood", exact: true })).toBeVisible();
}

function reviewCard(page: Page) { return page.locator(".panel").filter({ has: page.getByRole("heading", { name: "Review what Apex understood", exact: true }) }); }

test("manual mixed import saves approved facts and bulk availability without activating or granting AI consent", async ({ page }) => {
  const { writes } = await importApi(page);
  await analyzePaste(page);
  const review = reviewCard(page);
  await review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true }).fill("I enjoy easy running around work.");
  await review.getByRole("checkbox", { name: "Running", exact: true }).check();
  const availability = review.getByRole("group", { name: "Your weekly schedule", exact: true });
  await availability.getByLabel("Start time for selected days", { exact: true }).fill("18:00");
  await availability.getByLabel("End time for selected days", { exact: true }).fill("20:00");
  await expect(review.getByRole("button", { name: "Save to my athlete profile", exact: true })).toBeDisabled();
  await availability.getByRole("button", { name: "Apply time to selected days", exact: true }).click();
  await review.getByRole("button", { name: "Save to my athlete profile", exact: true }).click();
  await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toBeVisible();
  const confirmation = writes.find(write => write.path.endsWith("/profile-confirm"))!;
  expect(confirmation.path).toBe("/lab/athlete-imports/2/profile-confirm");
  expect(confirmation.body).toEqual({ payload_hash: "c".repeat(64), expected_profile_revision: 0, fields: ["context.athlete_notes", "training_focus", "context.availability"] });
  const reviewed = writes.find(write => write.method === "PUT")!.body.proposal;
  expect(reviewed.profile.context.availability).toHaveLength(5);
  expect(reviewed.weekly).toBeNull(); expect(reviewed.dated).toBeNull();
  expect(writes.find(write => write.path === "/lab/athlete-imports")!.body.use_ai).toBe(false);
  expect(writes.some(write => write.path.includes("/confirm") && !write.path.includes("documents") && !write.path.includes("profile-confirm"))).toBe(false);
  expect(writes[0].path).toContain("for_athlete_import=true");
});

test("AI facts show quotes and uncertainty; discarded facts stay unapproved and profile save can end the journey", async ({ page }) => {
  const proposal = emptyProposal(); proposal.profile = { training_focus: ["running"], context: { athlete_notes: "I run for health.", main_goal: "Health", schedule_constraints: "Uncertain evening schedule" } };
  proposal.sources = [{ field: "profile.context.athlete_notes", quote: "I run for health.", certainty: "explicit" }, { field: "profile.context.schedule_constraints", quote: "Autumn goals are flexible.", certainty: "uncertain" }];
  const { writes } = await importApi(page, { proposal, ai: true });
  await page.goto("/app/lab?tab=documents"); await page.getByLabel("Read or paste the text to analyze", { exact: true }).fill(sourceText);
  await page.getByRole("checkbox", { name: /Use my authorized AI access/ }).check(); await page.getByRole("button", { name: "Analyze document", exact: true }).click();
  const review = reviewCard(page); await expect(review.getByText("AI suggestions · review required", { exact: true })).toBeVisible();
  await expect(review.getByText("Explicit in the source", { exact: true })).toBeVisible(); await expect(review.getByText("Uncertain — check this fact", { exact: true })).toBeVisible();
  await review.getByRole("checkbox", { name: "Save: Travel, shift work or variable schedule", exact: true }).uncheck();
  await review.getByLabel("Main goal or next important event (optional)", { exact: true }).fill("Enjoy sustainable running");
  await review.getByRole("button", { name: "Save to my athlete profile", exact: true }).click();
  await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toBeVisible();
  expect(writes.find(write => write.path.endsWith("/profile-confirm"))!.body.fields).toEqual(["training_focus", "context.athlete_notes", "context.main_goal"]);
  expect(writes.some(write => write.path.includes("template") || write.path.includes("plan-drafts"))).toBe(false);
  await expect(page.getByText("SHA-256", { exact: false })).toHaveCount(0);
});

test("weekly template stays undated until explicit dates, previews all sessions and activates only the reviewed hash", async ({ page }) => {
  const proposal = emptyProposal(); proposal.weekly = { title: "Easy week", rows: [workout("tuesday", 1), workout("thursday", 3, "road_cycling")], notes: "Flexible autumn" };
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page);
  await review.getByRole("button", { name: "Review training plan", exact: true }).click();
  await expect(page.getByText("Date unknown", { exact: true })).toHaveCount(0);
  await review.getByRole("button", { name: "Save weekly template", exact: true }).click();
  await expect(review.getByText("Weekly template saved. Choose dates when you want to create a plan.", { exact: true })).toBeVisible();
  expect(writes.some(write => write.path.includes("plan-drafts"))).toBe(false);
  await expect(page.getByRole("button", { name: "Preview calendar", exact: true })).toBeDisabled();
  const dates = page.locator(".panel").filter({ has: page.getByRole("button", { name: "Preview calendar", exact: true }) });
  await dates.getByLabel("Start date", { exact: true }).fill("2026-10-12"); await dates.getByLabel("End date", { exact: true }).fill("2026-10-18"); await dates.getByRole("button", { name: "Preview calendar", exact: true }).click();
  const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true }); await expect(calendar.locator("li")).toHaveCount(2);
  await expect(calendar.getByText("Tuesday, October 13, 2026", { exact: false })).toBeVisible();
  await expect(calendar.getByText("Thursday, October 15, 2026", { exact: false })).toBeVisible();
  expect(writes.find(write => write.path.endsWith("/preview"))!.body).toEqual({ expected_revision: 1, starts_on: "2026-10-12", ends_on: "2026-10-18" });
  expect(writes.some(write => write.path.includes("plan-drafts"))).toBe(false);
  await calendar.getByRole("button", { name: "Activate this reviewed plan", exact: true }).click();
  await expect(calendar.getByText("Training plan activated. These workouts are now on your calendar.", { exact: true })).toBeVisible();
  expect(writes.find(write => write.path.includes("plan-drafts"))!.body).toEqual({ payload_hash: "d".repeat(64), ambiguities_reviewed: true });
});

for (const conflict of ["review", "profile"] as const) test(`import ${conflict} conflict retains inline corrections and does not show success`, async ({ page }) => {
  const { writes } = await importApi(page, { conflict }); await analyzePaste(page); const review = reviewCard(page);
  await review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true }).fill("Keep this correction."); await review.getByRole("button", { name: "Save to my athlete profile", exact: true }).click();
  await expect(review.getByRole("alert")).toContainText("changed while you were reviewing"); await expect(review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true })).toHaveValue("Keep this correction.");
  await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toHaveCount(0);
  expect(writes.some(write => write.path.includes("plan-drafts"))).toBe(false);
});

test("optional profile uncertainty can be deferred and required questions gate selected fields", async ({ page }) => {
  const proposal = emptyProposal(); proposal.profile.context = { main_goal: "Season goal", athlete_notes: "I run" };
  proposal.issues = [{ field: "profile.context.main_goal", question: "Which season goal should be saved?", required: false }, { field: "profile.context.athlete_notes", question: "What is your correct background?", required: true }];
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page);
  await expect(review.getByRole("button", { name: "Save to my athlete profile", exact: true })).toBeDisabled();
  await review.getByRole("button", { name: "Decide later", exact: true }).click(); await expect(review.getByRole("checkbox", { name: "Save: Main goal or next important event (optional)", exact: true })).not.toBeChecked();
  await review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true }).fill("My corrected background."); await review.getByRole("button", { name: "Use my correction", exact: true }).click();
  await review.getByRole("button", { name: "Save to my athlete profile", exact: true }).click(); await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toBeVisible();
  expect(writes.find(write => write.path.endsWith("/profile-confirm"))!.body.fields).toEqual(["context.athlete_notes"]);
});

test("manual weekly editing leaves unknown targets blank and optional deferred rows out", async ({ page }) => {
  const proposal = emptyProposal(); proposal.weekly = { title: "Week", rows: [workout("tue", 1), workout("thu", 3)], notes: "" }; proposal.issues = [{ field: "weekly.rows.0.description", question: "Is Tuesday additional training?", required: false }]; proposal.sources = [{ field: "weekly.rows.1.description", quote: "Thursday is a ride.", certainty: "explicit" }];
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page);
  await review.getByRole("button", { name: "Review training plan", exact: true }).click(); await review.getByRole("button", { name: "Decide later", exact: true }).click(); await expect(review.getByText("“Thursday is a ride.”", { exact: true })).toBeVisible(); await review.getByRole("button", { name: "Save weekly template", exact: true }).click();
  await expect(review.getByText("Weekly template saved. Choose dates when you want to create a plan.", { exact: true })).toBeVisible();
  const rows = writes.find(write => write.method === "PUT")!.body.proposal.weekly.rows; expect(rows).toHaveLength(1); expect(rows[0].day).toBe(3); expect(rows[0].duration_min).toBeNull(); expect(rows[0].intensity_targets).toEqual({}); expect(rows[0]).not.toHaveProperty("date");
});

test("confirmation waits for the server and freezes editable fields", async ({ page }) => {
  const controls = await importApi(page, { holdProfile: true }); await analyzePaste(page); const review = reviewCard(page); const notes = review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true });
  await notes.fill("Wait for confirmation."); await review.getByRole("button", { name: "Save to my athlete profile", exact: true }).click();
  await expect(review.getByText("Saving your review…", { exact: true })).toBeVisible(); await expect(notes).toBeDisabled(); await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toHaveCount(0);
  await expect.poll(() => controls.writes.some(write => write.path.endsWith("/profile-confirm"))).toBe(true); controls.finishProfile(); await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toBeVisible();
});

for (const locale of ["en", "it"] as const) test(`manual import is localized, keyboard accessible and fits mobile: ${locale}`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await importApi(page, { locale }); await page.goto("/app/lab?tab=documents");
  const text = page.getByLabel(locale === "en" ? "Read or paste the text to analyze" : "Leggi o incolla il testo da analizzare", { exact: true }); await text.fill(sourceText);
  const analyze = page.getByRole("button", { name: locale === "en" ? "Analyze document" : "Analizza documento", exact: true }); await analyze.focus(); await analyze.press("Enter");
  await expect(page.getByRole("heading", { name: locale === "en" ? "Review what Apex understood" : "Rivedi cosa ha compreso Apex", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

for (const readable of [true, false]) test(`PDF ${readable ? "extracted text is reviewed" : "scanned source has manual fallback"} before analysis`, async ({ page }) => {
  const { writes } = await importApi(page, { pdfText: readable ? sourceText : null }); await page.goto("/app/lab?tab=documents");
  await page.getByLabel("Athlete information file", { exact: true }).setInputFiles({ name: "athlete.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 synthetic") });
  const text = page.getByLabel("Read or paste the text to analyze", { exact: true });
  if (readable) await expect(text).toHaveValue(sourceText); else { await expect(page.getByText("This PDF has no readable text.", { exact: false })).toBeVisible(); await expect(page.getByRole("button", { name: "Analyze document", exact: true })).toBeDisabled(); await text.fill(sourceText); }
  await page.getByRole("button", { name: "Analyze document", exact: true }).click(); await expect(page.getByRole("heading", { name: "Review what Apex understood", exact: true })).toBeVisible();
  expect(writes.filter(write => write.path.includes("for_athlete_import"))).toHaveLength(1); expect(writes.find(write => write.path.endsWith("/documents/21/confirm"))!.body.reviewed_text).toBe(sourceText);
});

test("AI failure leaves the source reusable for a manual review without granting consent", async ({ page }) => {
  const { writes } = await importApi(page, { ai: true, aiFailure: true }); await page.goto("/app/lab?tab=documents"); await page.getByLabel("Read or paste the text to analyze", { exact: true }).fill(sourceText);
  const ai = page.getByRole("checkbox", { name: /Use my authorized AI access/ }); await ai.check(); await page.getByRole("button", { name: "Analyze document", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Use manual review"); await ai.uncheck(); await page.getByRole("button", { name: "Analyze document", exact: true }).click(); await expect(page.getByRole("heading", { name: "Review what Apex understood", exact: true })).toBeVisible();
  expect(writes.filter(write => write.path === "/lab/athlete-imports").map(write => write.body.use_ai)).toEqual([true, false]); expect(writes.filter(write => write.path.includes("for_athlete_import"))).toHaveLength(1);
});

test("direct manual dated plan requires complete dates and previews exact targets before activation", async ({ page }) => {
  const { writes } = await importApi(page); await analyzePaste(page); const review = reviewCard(page);
  await review.getByRole("button", { name: "Review training plan", exact: true }).click();
  await review.locator("summary").filter({ hasText: "Dated workouts and specific plans" }).click();
  await review.getByRole("button", { name: "Add dated workouts manually", exact: true }).click();
  await review.getByRole("button", { name: "Add a workout from the document", exact: true }).click();
  const previewButton = review.getByRole("button", { name: "Preview dated plan", exact: true }); await expect(previewButton).toBeDisabled();
  await review.getByLabel("Start date", { exact: true }).fill("2026-10-13"); await review.getByLabel("End date", { exact: true }).fill("2026-10-13");
  await review.getByLabel("Date (optional for a draft)", { exact: true }).fill("2026-10-13"); await review.getByRole("combobox", { name: "Sport", exact: true }).selectOption("running");
  await review.locator("summary").filter({ hasText: "Optional intensity targets" }).click(); await review.getByLabel("Recorded plan RPE target (0–10)", { exact: true }).fill("3–4");
  await previewButton.click(); const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true }); await expect(calendar.locator("li")).toHaveCount(1);
  const reviewed = writes.find(write => write.method === "PUT")!.body.proposal.dated;
  expect(reviewed.sessions[0].date).toBe("2026-10-13"); expect(reviewed.sessions[0].duration_min).toBeNull(); expect(reviewed.sessions[0].intensity_targets).toEqual({ rpe: "3–4" });
  expect(writes.find(write => write.path.endsWith("/dated-plan"))!.body).toEqual({ payload_hash: "c".repeat(64) });
  expect(writes.some(write => write.path.endsWith("/profile-confirm") || write.path.endsWith("/template-confirm") || write.path.includes("plan-drafts"))).toBe(false);
  await calendar.getByRole("button", { name: "Activate this reviewed plan", exact: true }).click(); await expect(calendar.getByText("Training plan activated. These workouts are now on your calendar.", { exact: true })).toBeVisible();
});

test("template activation conflict retains the complete calendar without a success receipt", async ({ page }) => {
  const proposal = emptyProposal(); proposal.weekly = { title: "Week", rows: [workout("tue", 1), workout("thu", 3)], notes: "" };
  await importApi(page, { proposal, conflict: "activation" }); await analyzePaste(page); const review = reviewCard(page); await review.getByRole("button", { name: "Review training plan", exact: true }).click(); await review.getByRole("button", { name: "Save weekly template", exact: true }).click();
  const dates = page.locator(".panel").filter({ has: page.getByRole("button", { name: "Preview calendar", exact: true }) }); await dates.getByLabel("Start date", { exact: true }).fill("2026-10-12"); await dates.getByLabel("End date", { exact: true }).fill("2026-10-18"); await dates.getByRole("button", { name: "Preview calendar", exact: true }).click();
  const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true }); await calendar.getByRole("button", { name: "Activate this reviewed plan", exact: true }).click();
  await expect(calendar.getByRole("alert")).toContainText("changed while you were reviewing"); await expect(calendar.locator("li")).toHaveCount(2); await expect(calendar.getByText("Training plan activated. These workouts are now on your calendar.", { exact: true })).toHaveCount(0);
  await dates.getByLabel("End date", { exact: true }).fill("2026-10-19"); await expect(calendar).toHaveCount(0);
});

test("changing approved field selection after a receipt creates an explicit new review", async ({ page }) => {
  const proposal = emptyProposal(); proposal.profile.context = { athlete_notes: "Running background", main_goal: "Health" };
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page); const save = review.getByRole("button", { name: "Save to my athlete profile", exact: true });
  await save.click(); await expect(review.getByText("Athlete profile saved. Your active plan has not changed.", { exact: true })).toBeVisible();
  await review.getByRole("checkbox", { name: "Save: Main goal or next important event (optional)", exact: true }).uncheck(); await save.click();
  await expect.poll(() => writes.filter(write => write.path.endsWith("/profile-confirm")).length).toBe(2);
  const latest = writes.filter(write => write.path.endsWith("/profile-confirm")).at(-1)!;
  expect(latest.path).toBe("/lab/athlete-imports/2/profile-confirm"); expect(latest.body.expected_profile_revision).toBe(1); expect(latest.body.fields).toEqual(["context.athlete_notes"]);
  expect(writes.filter(write => write.method === "PUT")).toHaveLength(1);
});

test("unsaved import corrections guard Lab navigation and browser unload", async ({ page }) => {
  await importApi(page); await page.goto("/app");
  const tools = page.getByRole("button", { name: "Tools & more", exact: true });
  await expect(tools).toHaveAttribute("aria-expanded", "false");
  await tools.click(); await expect(tools).toHaveAttribute("aria-expanded", "true");
  await page.locator('#workspace-tools a[href="/app/lab"]').click();
  await page.getByRole("button", { name: "Documents", exact: true }).click(); await page.getByLabel("Read or paste the text to analyze", { exact: true }).fill(sourceText); await page.getByRole("button", { name: "Analyze document", exact: true }).click();
  const review = reviewCard(page); const notes = review.getByLabel("Tell Apex anything else that may help it understand your training, goals, schedule, preferences, or constraints.", { exact: true }); await notes.fill("Keep these unsaved facts.");
  page.once("dialog", dialog => dialog.dismiss()); await page.getByRole("button", { name: "Baselines", exact: true }).click(); await expect(notes).toHaveValue("Keep these unsaved facts.");
  page.once("dialog", dialog => dialog.dismiss()); await page.locator('a[href="/app/settings"]').first().click(); await expect(notes).toHaveValue("Keep these unsaved facts.");
  expect(await page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })))).toBe(true);
  // BrowserRouter back navigation cannot be cancelled; retain the unsaved
  // review in memory and restore it when the user returns.
  await page.goBack(); await expect(page).toHaveURL(/\/app\/lab$/); await page.goForward();
  await expect(notes).toHaveValue("Keep these unsaved facts.");
  await review.getByRole("button", { name: "Save review for later", exact: true }).click(); await expect(review.getByText("Review saved. You can return later; no plan has been activated.", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })))).toBe(false);
});

test("Today template anchor resumes the exact saved calendar draft after leaving the import", async ({ page }) => {
  const proposal = emptyProposal(); proposal.weekly = { title: "Saved week", rows: [workout("tue", 1), workout("thu", 3)], notes: "" };
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page); await review.getByRole("button", { name: "Review training plan", exact: true }).click(); await review.getByRole("button", { name: "Save weekly template", exact: true }).click();
  const dates = page.locator(".panel").filter({ has: page.getByRole("button", { name: "Preview calendar", exact: true }) }); await dates.getByLabel("Start date", { exact: true }).fill("2026-10-12"); await dates.getByLabel("End date", { exact: true }).fill("2026-10-18"); await dates.getByRole("button", { name: "Preview calendar", exact: true }).click(); await expect(page.getByRole("region", { name: "Full calendar preview", exact: true }).locator("li")).toHaveCount(2);
  await page.goto("/app/lab?tab=documents#template-31"); const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true }); await expect(calendar.locator("li")).toHaveCount(2);
  expect(writes.filter(write => write.path.endsWith("/preview"))).toHaveLength(1);
  await calendar.getByRole("button", { name: "Activate this reviewed plan", exact: true }).click(); await expect(calendar.getByText("Training plan activated. These workouts are now on your calendar.", { exact: true })).toBeVisible(); expect(writes.find(write => write.path.includes("plan-drafts"))!.body.payload_hash).toBe("d".repeat(64));
});

test("Today document anchor resumes an imported dated plan without the earlier document workflow", async ({ page }) => {
  const proposal = emptyProposal(); const { id, day, ...fields } = workout("tue", 1); proposal.dated = { title: "Dated source", starts_on: "2026-10-13", ends_on: "2026-10-13", weekly_structure: "", sessions: [{ ...fields, date: "2026-10-13" }], ambiguities: [], protected: false };
  const { writes } = await importApi(page, { proposal }); await analyzePaste(page); const review = reviewCard(page); await review.getByRole("button", { name: "Review training plan", exact: true }).click(); await review.getByRole("button", { name: "Preview dated plan", exact: true }).click(); await expect(page.getByRole("region", { name: "Full calendar preview", exact: true })).toBeVisible();
  await page.goto("/app/lab?tab=documents#document-21"); const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true }); await expect(calendar.locator("li")).toHaveCount(1);
  expect(writes.filter(write => write.path.endsWith("/dated-plan"))).toHaveLength(1); await expect(page.getByText("Review a structured plan", { exact: true })).toHaveCount(0);
});
