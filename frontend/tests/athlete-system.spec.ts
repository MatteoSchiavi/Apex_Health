import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi, today } from "./fixtures";

async function openAvailability(page: Page, locale: "en" | "it" = "en") {
  await page.getByRole("button", { name: locale === "en" ? "Complete later" : "Completa più avanti", exact: true }).click();
  await page.locator("summary").filter({ hasText: locale === "en" ? "Usual availability" : "Disponibilità abituale" }).click();
}

for (const locale of ["en", "it"] as const) {
  test(`bulk availability persists five weekdays and reports later edits: ${locale}`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, aiConsent: false });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/settings?tab=profile");
    const panel = page.locator(".panel").filter({ has: page.getByText(locale === "en" ? "Your athlete context" : "Il tuo contesto sportivo", { exact: true }) });
    await page.getByLabel(locale === "en" ? "Running" : "Corsa", { exact: true }).check();
    await page.getByLabel(locale === "en" ? "Gym" : "Palestra", { exact: true }).check();
    await openAvailability(page, locale);
    await page.locator("textarea[maxlength='8000']").fill("Running and strength around work.");
    await page.getByRole("button", { name: locale === "en" ? "Weekdays" : "Giorni feriali", exact: true }).click();
    await page.getByLabel(locale === "en" ? "Start time for selected days" : "Ora di inizio per i giorni selezionati", { exact: true }).fill("18:00");
    await page.getByLabel(locale === "en" ? "End time for selected days" : "Ora di fine per i giorni selezionati", { exact: true }).fill("20:00");
    const save = page.getByRole("button", { name: locale === "en" ? "Save athlete context" : "Salva il contesto sportivo", exact: true });
    await expect(save).toBeDisabled();
    await page.getByRole("button", { name: locale === "en" ? "Apply time to selected days" : "Applica orario ai giorni selezionati", exact: true }).click();
    await save.click();
    await expect(panel.getByRole("status").filter({ hasText: locale === "en" ? "Athlete context saved." : "Contesto sportivo salvato." })).toBeVisible();
    const body = writes.find(w => w.path === "/athlete/profile")!.body;
    expect(body.training_focus).toEqual(["running", "gym"]);
    expect((body.context as Record<string, unknown>).availability).toEqual([0, 1, 2, 3, 4].map(day => ({ day, start: "18:00", end: "20:00" })));
    expect(writes.some(w => /plan-drafts|confirm/.test(w.path))).toBe(false);
    await page.reload();
    await expect(page.locator("textarea[maxlength='8000']")).toHaveValue("Running and strength around work.");
    await expect(page.getByLabel(locale === "en" ? "Running" : "Corsa", { exact: true })).toBeChecked();
    await page.locator("summary").filter({ hasText: locale === "en" ? "Usual availability" : "Disponibilità abituale" }).click();
    const schedule = page.getByRole("region", { name: locale === "en" ? "Your weekly schedule" : "Il tuo calendario settimanale", exact: true });
    await expect(schedule.getByRole("combobox")).toHaveCount(5);
    for (let index = 0; index < 5; index++) {
      await expect(schedule.getByRole("combobox").nth(index)).toHaveValue(String(index));
      await expect(schedule.locator('input[type="time"]').nth(index * 2)).toHaveValue("18:00");
      await expect(schedule.locator('input[type="time"]').nth(index * 2 + 1)).toHaveValue("20:00");
    }
    await save.click();
    await expect(panel.getByText(locale === "en" ? "Saved" : "Salvato", { exact: true })).toBeVisible();
    await page.locator("textarea[maxlength='8000']").fill("A changed biography.");
    await expect(panel.getByText(locale === "en" ? "Saved" : "Salvato", { exact: true })).toHaveCount(0);
    await expect(panel.getByRole("status").filter({ hasText: locale === "en" ? "unsaved changes" : "modifiche non salvate" })).toBeVisible();
    await page.locator("textarea[maxlength='8000']").fill("Running and strength around work.");
    await expect(panel.getByText(locale === "en" ? "Saved" : "Salvato", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  });
}

test("availability deduplicates ranges, adds another window and permits individual exceptions", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app/settings?tab=profile");
  await openAvailability(page);
  const start = page.getByLabel("Start time for selected days", { exact: true });
  const end = page.getByLabel("End time for selected days", { exact: true });
  const apply = page.getByRole("button", { name: "Apply time to selected days", exact: true });
  const schedule = page.getByRole("region", { name: "Your weekly schedule", exact: true });
  const save = page.getByRole("button", { name: "Save athlete context", exact: true });
  for (let repeat = 0; repeat < 2; repeat++) {
    await start.fill("18:00"); await end.fill("20:00"); await apply.click();
    await expect(schedule.getByRole("combobox")).toHaveCount(5);
  }
  await start.fill("19:00"); await end.fill("21:00"); await apply.click();
  await expect(page.getByRole("alert")).toContainText("cannot overlap");
  await expect(schedule.getByRole("combobox")).toHaveCount(5);
  await expect(save).toBeDisabled();
  await start.fill("22:00"); await end.fill("06:00"); await apply.click();
  await expect(page.getByRole("alert")).toContainText("Overnight windows are not supported");
  await page.getByRole("button", { name: "Cancel time entry", exact: true }).click();
  await page.getByRole("button", { name: "Weekend", exact: true }).click();
  await start.fill("08:00"); await end.fill("10:00"); await apply.click();
  await expect(schedule.getByRole("combobox")).toHaveCount(7);
  await page.getByRole("button", { name: "Weekdays", exact: true }).click();
  await start.fill("07:00"); await end.fill("08:00"); await apply.click();
  await expect(schedule.getByRole("combobox")).toHaveCount(12);
  await page.getByLabel("Start for time 1", { exact: true }).fill("19:00");
  await page.getByLabel("End for time 1", { exact: true }).fill("20:00");
  await expect(save).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("cannot overlap");
  await page.getByLabel("Start for time 1", { exact: true }).fill("07:30");
  await page.getByLabel("End for time 1", { exact: true }).fill("08:30");
  await schedule.getByRole("button", { name: "Remove time", exact: true }).last().click();
  await save.click();
  await expect.poll(() => writes.filter(w => w.path === "/athlete/profile").length).toBe(1);
  const availability = (writes.find(w => w.path === "/athlete/profile")!.body.context as { availability: unknown[] }).availability;
  expect(availability).toHaveLength(11);
  expect(availability[0]).toEqual({ day: 0, start: "07:30", end: "08:30" });
});

for (const status of [503, 409]) {
  test(`profile save ${status} preserves edits and reports no success`, async ({ page }) => {
    await installApi(page);
    let attempts = 0;
    await page.route("**/athlete/profile", route => {
      if (route.request().method() === "PUT" && attempts++ === 0) return route.fulfill({ status, json: { detail: "Cannot save" } });
      return route.fallback();
    });
    await page.goto("/app/settings?tab=profile");
    await page.getByRole("button", { name: "Complete later", exact: true }).click();
    const notes = page.locator("textarea[maxlength='8000']");
    await notes.fill("Keep my draft after an error.");
    await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(status === 409 ? "This record changed" : "Could not save");
    await expect(notes).toHaveValue("Keep my draft after an error.");
    await expect(page.getByText("Athlete context saved.", { exact: false })).toHaveCount(0);
    if (status === 409) {
      page.once("dialog", dialog => dialog.dismiss());
      await page.getByRole("button", { name: "Reload current context", exact: true }).click();
      await expect(notes).toHaveValue("Keep my draft after an error.");
      page.once("dialog", dialog => dialog.accept());
      await page.getByRole("button", { name: "Reload current context", exact: true }).click();
      await expect(notes).toHaveValue("");
    } else {
      await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
      await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
    }
  });
}

test("profile saving waits for server confirmation and survives a failed account refresh", async ({ page }) => {
  await installApi(page);
  let finish: () => void = () => {};
  await page.route("**/athlete/profile", async route => {
    if (route.request().method() === "PUT") await new Promise<void>(resolve => { finish = resolve; });
    return route.fallback();
  });
  await page.goto("/app/settings?tab=profile");
  await page.getByRole("button", { name: "Complete later", exact: true }).click();
  const notes = page.locator("textarea[maxlength='8000']");
  await notes.fill("A server-confirmed biography.");
  await page.route("**/me", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
  await expect(page.getByRole("button", { name: "Saving athlete context…", exact: true })).toBeDisabled();
  await expect(notes).toBeDisabled();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toHaveCount(0);
  finish();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
  await expect(notes).toBeEnabled();
});

test("dirty profile guards links and settings tabs, retains browser-back drafts and clears clean guards", async ({ page }) => {
  await installApi(page);
  await page.goto("/app");
  await page.locator('a[href="/app/settings"]').first().click();
  await page.getByRole("button", { name: "Complete later", exact: true }).click();
  await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
  const notes = page.locator("textarea[maxlength='8000']");
  await notes.fill("Retain this when I use browser back.");
  await page.locator("summary").filter({ hasText: "Usual availability" }).click();
  await page.getByLabel("Start time for selected days", { exact: true }).fill("18:00");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  await expect(notes).toBeVisible();
  const profileTab = page.getByRole("tab", { name: "Profile", exact: true });
  await profileTab.focus();
  page.once("dialog", dialog => dialog.dismiss());
  await profileTab.press("ArrowRight");
  await expect(notes).toBeVisible();
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator('a[href="/app"]').first().click();
  await expect(notes).toHaveValue("Retain this when I use browser back.");
  expect(await page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })))).toBe(true);
  await page.goBack();
  await expect(page).toHaveURL(/\/app$/);
  await page.goForward();
  await expect(notes).toHaveValue("Retain this when I use browser back.");
  await page.locator("summary").filter({ hasText: "Usual availability" }).click();
  await expect(page.getByLabel("Start time for selected days", { exact: true })).toHaveValue("18:00");
  await page.getByRole("button", { name: "Cancel time entry", exact: true }).click();
  await page.getByRole("button", { name: "Save athlete context", exact: true }).click();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
  expect(await page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })))).toBe(false);
  let dialogs = 0;
  const dismiss = (dialog: import("@playwright/test").Dialog) => { dialogs++; void dialog.dismiss(); };
  page.on("dialog", dismiss);
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  await expect(page).toHaveURL(/tab=appearance/);
  expect(dialogs).toBe(0);
  page.off("dialog", dismiss);
  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await notes.fill("Discard this only after explicit confirmation.");
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  await page.getByRole("tab", { name: "Profile", exact: true }).click();
  await expect(notes).toHaveValue("Retain this when I use browser back.");
});

test("onboarding has one primary save action and keeps all advanced details optional", async ({ page }) => {
  const { writes } = await installApi(page, { aiConsent: false });
  await page.goto("/app/settings?tab=profile");
  await page.getByLabel("Running", { exact: true }).check();
  await page.getByLabel("Gym", { exact: true }).check();
  for (let step = 0; step < 5; step++) {
    await expect(page.getByRole("button", { name: "Save athlete context", exact: true })).toHaveCount(0);
    const save = page.getByRole("button", { name: step === 4 ? "Save these first details" : "Save and continue", exact: true });
    await expect(save).toHaveCount(1);
    await save.click();
    await expect.poll(() => writes.filter(w => w.path === "/athlete/profile").length).toBe(step + 1);
    await expect(page.getByRole("button", { name: "Saving athlete context…", exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Save athlete context", exact: true })).toBeVisible();
  const saves = writes.filter(w => w.path === "/athlete/profile");
  expect(saves.map(w => w.body.expected_revision)).toEqual([0, 1, 2, 3, 4]);
  expect((saves.at(-1)!.body.context as Record<string, unknown>).onboarding_step).toBe(5);
});

test("confirmed FTP survives context saves and deletion clears prior save feedback", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app/settings?tab=profile");
  await page.getByLabel("Cycling", { exact: true }).check();
  await page.getByRole("button", { name: "Complete later", exact: true }).click();
  await page.locator("summary").filter({ hasText: "Optional details" }).click();
  await page.getByLabel("FTP (watts)", { exact: true }).fill("250");
  await page.getByLabel("FTP measurement date", { exact: true }).fill(today);
  await page.getByRole("checkbox", { name: "I confirm this dated FTP value.", exact: true }).check();
  const save = page.getByRole("button", { name: "Save athlete context", exact: true });
  await save.click();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toBeVisible();
  await page.locator("textarea[maxlength='8000']").fill("Updated context, same measured FTP.");
  await save.click();
  await expect.poll(() => writes.filter(w => w.path === "/athlete/profile").length).toBe(2);
  const latest = writes.filter(w => w.path === "/athlete/profile").at(-1)!;
  expect((latest.body.context as Record<string, unknown>).ftp).toEqual({ watts: 250, measured_on: today, confirmed: true });
  await page.getByRole("button", { name: "Delete athlete context", exact: true }).click();
  await expect(page.locator("textarea[maxlength='8000']")).toHaveValue("");
  await expect(page.getByText("Athlete context deleted.", { exact: false })).toBeVisible();
  await expect(page.getByText("Athlete context saved.", { exact: false })).toHaveCount(0);
});

for (const locale of ["en", "it"] as const) for (const theme of ["light", "dark"] as const) {
  test(`progressive athlete profile is optional, localized and accessible: ${locale}/${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const { writes } = await installApi(page, { locale, theme, aiConsent: false });
    await page.goto("/app/settings?tab=profile");
    await expect(page.getByText(locale === "en" ? "Your athlete context" : "Il tuo contesto sportivo", { exact: true })).toBeVisible();
    await page.getByLabel(locale === "en" ? "Running" : "Corsa", { exact: true }).check();
    await page.getByLabel(locale === "en" ? "Cycling" : "Ciclismo", { exact: true }).check();
    await page.getByLabel(locale === "en" ? "Gym" : "Palestra", { exact: true }).check();
    await page.getByRole("button", { name: locale === "en" ? "Move up" : "Sposta in alto", exact: true }).last().click();
    await page.getByRole("button", { name: locale === "en" ? "Complete later" : "Completa più avanti", exact: true }).click();
    const notes = page.locator("textarea[maxlength='8000']");
    await notes.fill("I train around a variable schedule.");
    await page.getByRole("button", { name: locale === "en" ? "Save athlete context" : "Salva il contesto sportivo", exact: true }).click();
    await expect.poll(() => writes.filter(w => w.path === "/athlete/profile").length).toBe(1);
    const body = writes.find(w => w.path === "/athlete/profile")!.body;
    expect(body.training_focus).toEqual(["running", "gym", "cycling"]);
    expect((body.context as Record<string,unknown>).athlete_notes).toBe("I train around a variable schedule.");
    expect(writes.some(w => w.path.includes("consent") || w.path.includes("chats"))).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const scan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(scan.violations).toEqual([]);
  });
}

test("AI disclosure starts unticked and consent can be withdrawn", async ({ page }) => {
  const { writes } = await installApi(page, { aiConsent: false });
  await page.goto("/app/settings?tab=profile");
  const agreement = page.getByRole("checkbox", { name: /I agree to the use of my selected training/ });
  await expect(agreement).not.toBeChecked();
  const enable = page.getByRole("button", { name: "Give voluntary AI consent", exact: true });
  await expect(enable).toBeDisabled();
  await agreement.check(); await enable.click();
  await page.getByRole("button", { name: "Withdraw AI consent", exact: true }).click();
  await expect(enable).toBeDisabled(); await expect(agreement).not.toBeChecked();
  expect(writes.filter(w => w.path === "/athlete/ai/consent").map(w => w.body.active)).toEqual([true,false]);
});

const sessions = [
  { id: 10, plan_id: 5, plan_revision: 1, plan_title: "Autumn plan", discipline: "running", duration_min: 30, description: "Easy run", start_time: "08:00:00", protected: true, plan_protected: false, workout_protected: true, status: "planned", activity_id: null, checkin: null },
  { id: 11, plan_id: 5, plan_revision: 1, plan_title: "Autumn plan", discipline: "road_cycling", duration_min: 45, description: "Easy ride", start_time: "18:00:00", protected: false, plan_protected: false, workout_protected: false, status: "planned", activity_id: null, checkin: null },
];

test("Your day requires confirmation, shares session identity and keeps other sports visible", async ({ page }) => {
  await installApi(page);
  let linked = false, checkin: unknown = null;
  const writes: { path: string; body: any }[] = [];
  await page.route("**/athlete/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/athlete/day") return route.fulfill({ json: {
      date: today, timezone: "UTC", training_focus: ["running", "cycling"], state: linked ? "multiple_sessions" : "unplanned",
      sessions: sessions.map(s => ({ ...s, activity_id: s.id===10 && linked ? 42 : null, status: s.id===10 && linked ? "partial" : "planned", checkin: s.id===10 ? checkin : null })), legacy_gym_sessions: [], totals: {},
      activities: [{ id: 42, discipline: "running", start_time: today+"T08:00:00Z", duration_s: 1500, distance_m: 5000, planned_session_id: linked ? 10 : null, association: linked ? "confirmed" : "needs_confirmation", candidate_session_ids: [10], comparison: linked ? { target_duration_min:30, recorded_duration_min:25, duration_delta_min:-5 } : null, checkin },
      { id:43,discipline:"sailing",start_time:today+"T15:00:00Z",duration_s:1800,planned_session_id:null,association:"independent",candidate_session_ids:[],comparison:null,checkin:null }],
    } });
    if (path.endsWith("/association")) { writes.push({ path,body:route.request().postDataJSON() }); linked = true; return route.fulfill({ json: { state:"confirmed" } }); }
    if (path.endsWith("/checkins")) { const body=route.request().postDataJSON(); writes.push({path,body}); checkin={...body,id:1,revision:1};return route.fulfill({json:checkin}); }
    return route.fallback();
  });
  await page.goto("/app");
  const hero = page.locator(".panel").filter({ has: page.getByText("Your day",{exact:true}) });
  await hero.getByTestId("daily-details").locator("summary").first().click();
  await expect(hero.getByText("Needs confirmation",{exact:true})).toBeVisible();
  await expect(hero.getByRole("link",{name:"Sailing ↗",exact:true})).toBeVisible();
  await expect(hero.getByText("Protected",{exact:true})).toBeVisible();
  await hero.getByRole("combobox",{name:"Associate with a planned session",exact:true}).selectOption("10");
  await hero.getByRole("button",{name:"Confirm association",exact:true}).click();
  await expect(hero.getByText("Association confirmed",{exact:true})).toBeVisible();
  const recorded = hero.getByRole("region",{name:"Recorded activities"}).locator("li").filter({has: page.getByRole("link",{name:"Running ↗",exact:true})});
  await recorded.getByText("Quick post-session check-in",{exact:true}).click();
  await recorded.getByLabel("Perceived effort (RPE 0–10, optional)",{exact:true}).fill("6");
  await recorded.getByRole("button",{name:"Save check-in",exact:true}).click();
  expect(writes.find(w=>w.path.endsWith("/association"))?.body).toEqual({planned_session_id:10});
  await expect.poll(()=>writes.find(w=>w.path.endsWith("/checkins"))?.body.planned_session_id).toBe(10);
});

test("reviewed document creates a draft before explicit activation, with ambiguity acknowledgement", async ({ page }) => {
  await installApi(page, { aiConsent:false });
  const doc={ id:7,filename:"coach-plan.txt",media_type:"text/plain",content_hash:"a".repeat(64),status:"confirmed",revision:2,excerpt:"Dates remain unclear",created_at:today+"T00:00:00Z" };
  await page.route("**/lab/documents",route=>route.fulfill({json:[doc]}));
  let draft: any = null; const writes: {path:string;body:any}[]=[];
  await page.route("**/lab/plan-drafts*",route=>route.fulfill({json:draft?[draft]:[]}));
  await page.route("**/lab/documents/7/plan-drafts",route=>{const body=route.request().postDataJSON();writes.push({path:"draft",body});draft={id:8,document_id:7,document_revision:2,version:1,payload_hash:"b".repeat(64),status:"draft",confirmed_at:null,structure:{...body.structure,ambiguities:["Intensity not specified"]}};return route.fulfill({json:draft});});
  await page.route("**/lab/plan-drafts/8/confirm",route=>{writes.push({path:"confirm",body:route.request().postDataJSON()});draft={...draft,status:"confirmed"};return route.fulfill({json:{plan_id:5,draft}});});
  await page.goto("/app/lab?tab=documents");
  await page.locator("summary").filter({ hasText: "Advanced: general documents" }).click();
  await page.getByRole("button",{name:"Review a plan draft",exact:true}).click();
  await expect(page.getByRole("button",{name:"Extract a draft with AI",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Add a workout from the document",exact:true}).click();
  await page.getByRole("combobox",{name:"Sport",exact:true}).selectOption("sailing");
  await page.getByLabel("Start date",{exact:true}).fill(today);
  await page.getByLabel("End date",{exact:true}).fill(today);
  await page.getByLabel("Date (optional for a draft)",{exact:true}).fill(today);
  await page.getByRole("button",{name:"Save reviewable structure",exact:true}).click();
  await expect(page.getByText("Intensity not specified",{exact:true})).toBeVisible();
  const confirm=page.getByRole("button",{name:"Confirm structure and activate plan",exact:true});
  await expect(confirm).toBeDisabled();
  expect(writes.some(w=>w.path==="confirm")).toBe(false);
  await page.getByRole("checkbox",{name:/I have reviewed these workouts/}).check();await confirm.click();
  await expect(page.getByText("Structure confirmed",{exact:true})).toBeVisible();
  expect(writes.find(w=>w.path==="draft")?.body.structure.sessions[0].duration_min).toBeNull();
  expect(writes.find(w=>w.path==="confirm")?.body).toEqual({payload_hash:"b".repeat(64),ambiguities_reviewed:true});
});

test("missing cycling power remains unavailable with formula and source details on mobile",async({page})=>{
  await page.setViewportSize({width:390,height:844});await installApi(page,{theme:"dark"});
  await page.route("**/activities/1/endurance",route=>route.fulfill({json:{sport:"cycling",metrics:[{key:"normalized_power",value:null,unit:"W",kind:"calculated",formula:"fourth_root(mean(rolling_power^4))",formula_version:"apex-cycling-v1",source_dependencies:["streams:1:power"],availability:"unavailable",unavailable_reason:"requires_dense_continuous_power_stream",limitations:["descriptive_not_prediction"],prerequisites:["1Hz_recorded_power"]}]}}));
  await page.goto("/app/activities/1");
  await page.getByRole("tab",{name:"Session",exact:true}).click();
  await expect(page.getByText("Apex Normalized Power",{exact:true})).toBeVisible();
  await page.getByText("Formula, source requirements and quality",{exact:true}).click();
  await expect(page.getByText("apex-cycling-v1",{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa"]).analyze()).violations).toEqual([]);
});

for (const priorities of [[], ["Running"], ["Running", "Gym"], ["Cycling", "Running", "Gym"]]) {
  test(`any priority selection can be saved without health details: ${priorities.join(",") || "none"}`, async ({ page }) => {
    const { writes } = await installApi(page, { aiConsent:false });
    await page.goto("/app/settings?tab=profile");
    for (const priority of priorities) await page.getByRole("checkbox",{name:priority,exact:true}).check();
    await page.getByRole("button",{name:"Complete later",exact:true}).click();
    await page.getByRole("button",{name:"Save athlete context",exact:true}).click();
    await expect.poll(()=>writes.filter(w=>w.path==="/athlete/profile").length).toBe(1);
    expect(writes.find(w=>w.path==="/athlete/profile")?.body.training_focus).toEqual(priorities.map(p=>p.toLowerCase()));
    expect(writes.some(w=>w.path.includes("consent"))).toBe(false);
  });
}
