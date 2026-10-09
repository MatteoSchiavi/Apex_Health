import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi, today } from "./fixtures";

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
  await page.getByRole("button",{name:"Use this as my active plan",exact:true}).click();
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
  await page.getByText("Formula, inputs and limits",{exact:true}).click();
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
