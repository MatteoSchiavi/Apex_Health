import { expect, test, type Page, type Route } from "@playwright/test";
import { account, installApi } from "./fixtures";
import { validatedCoachContext } from "../src/features/coach/coachContext";

// Synthetic fixtures only: no real records, provider calls, or live writes.
const date = "2026-10-17";
const workoutContext = { userId: 1, date, plannedSessionId: 87 };
const labels = {
  en: { review: "Review question", keep: "Keep existing question", replace: "Replace with prepared question", changes: "Review proposals", conversation: "Conversation", day: "Return to day", workout: "Return to workout", retry: "Retry context" },
  it: { review: "Rivedi domanda", keep: "Mantieni la domanda esistente", replace: "Sostituisci con la domanda preparata", changes: "Rivedi proposte", conversation: "Conversazione", day: "Torna alla giornata", workout: "Torna all’allenamento", retry: "Riprova contesto" },
};

async function navigateContext(page: Page, context: unknown) {
  await page.evaluate(value => {
    history.pushState({ usr: { coachContext: value }, key: crypto.randomUUID() }, "", "/app/coach");
    dispatchEvent(new PopStateEvent("popstate"));
  }, context);
}

async function setup(page: Page, options: { locale?: "en" | "it"; aiConsent?: boolean; draft?: string; active?: boolean } = {}) {
  const fixture = await installApi(page, options);
  if (options.draft || options.active) await page.addInitScript(({ draft, active }) => {
    if (sessionStorage.getItem("coach-context-seeded")) return;
    sessionStorage.setItem("coach-context-seeded", "true");
    if (draft) localStorage.setItem("apex.chat.1.draft", draft);
    if (active) localStorage.setItem("apex.chat.1.active", "7");
  }, { draft: options.draft, active: options.active });
  let mode: "ready" | "mismatch" | "missing" | "error" = "ready";
  let hold = false;
  const posts: { route: Route; body: { text: string; session_id?: number } }[] = [];
  const dayRequests: string[] = [];
  const oldChat = { id: 7, title: "Earlier conversation", message_count: 1, started_at: date + "T08:00:00Z", last_activity_at: date + "T08:00:00Z" };
  await page.route("**/athlete/day?**", async route => {
    const requested = new URL(route.request().url()).searchParams.get("date")!;
    dayRequests.push(requested);
    if (mode === "error") return route.fulfill({ status: 503, json: { detail: "Synthetic unavailable day" } });
    return route.fulfill({ json: { date: mode === "mismatch" ? "2026-10-18" : requested, timezone: "UTC", training_focus: [], activities: [], sessions: mode === "missing" ? [] : [{ id: 87, plan_id: 3, plan_revision: 1, plan_title: "Synthetic plan", discipline: "running", start_time: null, session_type: "Easy run", duration_min:30, distance_m:null, description:"Comfortable effort", protected:false, plan_protected:false, workout_protected:false, status:"planned", activity_id:null, checkin:null }], legacy_gym_sessions: [], state: "planned", totals: {} } });
  });
  const reply = { id: 8, title: "Day review", messages: [{ id: 2, role: "assistant", content: "Synthetic reviewed reply", referenced_data: { drafts: [{ id: 41 }] } }] };
  await page.route(url => /^\/coach\/chats(?:\/\d+)?$/.test(url.pathname), async route => {
    if (route.request().method() === "POST") {
      posts.push({ route, body: route.request().postDataJSON() });
      if (!hold) await route.fulfill({ json: reply });
      return;
    }
    if (new URL(route.request().url()).pathname === "/coach/chats") return route.fulfill({ json: [oldChat] });
    return route.fulfill({ json: { ...oldChat, messages: [{ id: 1, role: "user", content: "Earlier conversation content", referenced_data: null }] } });
  });
  await page.goto("/app/coach");
  await expect(page.getByRole("textbox")).toBeVisible();
  return { ...fixture, posts, dayRequests, mode: (value: typeof mode) => { mode = value; }, hold: () => { hold = true; }, reply: (index: number) => posts[index].route.fulfill({ json: reply }) };
}

for (const locale of ["en", "it"] as const) {
  test(`workout context prepares a localized new question only after explicit review (${locale})`, async ({ page }) => {
    await page.setViewportSize({width:390,height:844});
    const ui = labels[locale];
    const fixture = await setup(page, { locale, active: true });
    await expect(page.getByText("Earlier conversation content", { exact: true })).toBeVisible();
    await page.route("**/athlete/planned-sessions/87/workout", route => route.fulfill({json:{planned_session_id:87,plan_revision:1,protected:false,editable:false,edit_block_reason:"past",workout:null,education:[],session:{date,discipline:"running",session_type:"Easy run",duration_min:30,description:"Comfortable effort"}}}));
    await page.goto("/app/workouts/87");
    const ask = page.getByRole("link",{name:locale === "en" ? "Ask Coach about this workout" : "Chiedi al Coach di questo allenamento"});
    await expect(ask).toHaveAttribute("href","/app/coach");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await ask.click();
    const review = page.getByRole("button", { name: ui.review, exact: true });
    await expect(review).toBeEnabled();
    const composer = page.getByRole("textbox");
    await expect(composer).toHaveValue("");
    expect(fixture.posts).toHaveLength(0);
    expect(fixture.dayRequests.length).toBeGreaterThan(0);
    expect(fixture.dayRequests.every(requested => requested === date)).toBe(true);
    await expect(page.getByRole("link", { name: ui.day, exact: true })).toHaveAttribute("href", "/app?date=" + date);
    await expect(page.getByRole("link", { name: ui.workout, exact: true })).toHaveAttribute("href", "/app/workouts/87");
    await review.click();
    const prepared = await composer.inputValue();
    expect(prepared).toContain(date);
    expect(prepared).toContain("#87");
    expect(prepared).toContain(locale === "en" ? "Review planned workout" : "Rivedi l’allenamento pianificato");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByText("Earlier conversation content", { exact: true })).toHaveCount(0);
    expect(fixture.posts).toHaveLength(0);
    await composer.fill(prepared + " My editable question.");
    await page.reload();
    await expect(composer).toHaveValue(prepared + " My editable question.");
    expect(fixture.posts).toHaveLength(0);
    await composer.press("Enter");
    await expect.poll(() => fixture.posts.length).toBe(1);
    expect(fixture.posts[0].body).toEqual({ text: prepared + " My editable question." });
    await expect(page.getByText("Synthetic reviewed reply", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: ui.changes, exact: true }).click();
    await expect(page.getByRole("link", { name: ui.day, exact: true })).toHaveAttribute("href", "/app?date=" + date);
    await page.getByRole("button", { name: ui.conversation, exact: true }).click();
    await expect(page.getByRole("link", { name: ui.workout, exact: true })).toHaveAttribute("href", "/app/workouts/87");
    expect(fixture.writes.filter(write => write.path.includes("/approve"))).toEqual([]);
    const state = await page.evaluate(() => history.state.usr);
    expect(state).toEqual({ coachContext: workoutContext });
  });

  test(`existing draft survives navigation and requires explicit replacement (${locale})`, async ({ page }) => {
    const ui = labels[locale];
    const fixture = await setup(page, { locale, draft: "Keep my existing question", active: true });
    await navigateContext(page, workoutContext);
    const composer = page.getByRole("textbox");
    await expect(page.getByRole("button", { name: ui.review, exact: true })).toBeEnabled();
    await expect(composer).toHaveValue("Keep my existing question");
    await page.getByRole("button", { name: ui.review, exact: true }).click();
    await expect(composer).toHaveValue("Keep my existing question");
    await page.getByRole("button", { name: ui.keep, exact: true }).click();
    await expect(page.getByText("Earlier conversation content", { exact: true })).toBeVisible();
    await composer.fill("A newer question while reviewing");
    await navigateContext(page, { userId: 1, date: "2026-10-16" });
    await expect(composer).toHaveValue("A newer question while reviewing");
    await expect(page.getByRole("button", { name: ui.review, exact: true })).toBeEnabled();
    await page.getByRole("button", { name: ui.review, exact: true }).click();
    await page.getByRole("button", { name: ui.replace, exact: true }).click();
    expect(await composer.inputValue()).toContain("2026-10-16");
    expect(await composer.inputValue()).not.toContain("#87");
    await expect(page.getByText("Earlier conversation content", { exact: true })).toHaveCount(0);
    expect(fixture.posts).toHaveLength(0);
  });

  test(`AI off still permits an unsent review draft (${locale})`, async ({ page }) => {
    const fixture = await setup(page, { locale, aiConsent: false });
    await page.goto("/app?date="+date);
    await page.getByRole("link",{name:locale === "en" ? "Ask Coach about this day" : "Chiedi al Coach di questa giornata"}).click();
    const review = page.getByRole("button", { name: labels[locale].review, exact: true });
    await expect(review).toBeEnabled();
    await review.click();
    const composer = page.getByRole("textbox");
    expect(await composer.inputValue()).toContain(date);
    await composer.press("Enter");
    await expect(page.getByRole("button", { name: locale === "en" ? "Send" : "Invia", exact: true })).toBeDisabled();
    expect(fixture.posts).toHaveLength(0);
    expect(fixture.writes).toEqual([]);
  });
}

test("invalid and other-account context is ignored without fetching or changing a draft", async ({ page }) => {
  const fixture = await setup(page, { draft: "Existing question" });
  for (const invalid of [
    { ...workoutContext, userId: 2 }, { ...workoutContext, userId: "1" },
    { ...workoutContext, date: "2026-02-30" }, { ...workoutContext, date: "2026-2-03" },
    { ...workoutContext, date: "2026-10-17?prompt=private" },
    { ...workoutContext, plannedSessionId: -1 }, { ...workoutContext, plannedSessionId: "87" },
    { ...workoutContext, plannedSessionId: 1.5 }, { ...workoutContext, plannedSessionId: Number.MAX_SAFE_INTEGER + 1 },
  ]) {
    await navigateContext(page, invalid);
    await expect(page.getByRole("button", { name: "Review question", exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox")).toHaveValue("Existing question");
  }
  expect(fixture.posts).toHaveLength(0);
  expect(fixture.dayRequests).toEqual([]);
});

for (const failure of ["error", "mismatch", "missing"] as const) test(`unverified context preserves the draft and retries the exact day (${failure})`, async ({ page }) => {
  const fixture = await setup(page, { draft: "Preserved question" });
  fixture.mode(failure);
  await navigateContext(page, workoutContext);
  await expect(page.getByRole("button", { name: "Retry context", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox")).toHaveValue("Preserved question");
  expect(fixture.posts).toHaveLength(0);
  fixture.mode("ready");
  await page.getByRole("button", { name: "Retry context", exact: true }).click();
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toBeEnabled();
  expect(fixture.dayRequests).toEqual([date, date]);
  await expect(page.getByRole("textbox")).toHaveValue("Preserved question");
});

test("context changes during a pending reply preserve the next question", async ({ page }) => {
  const fixture = await setup(page);
  fixture.hold();
  const composer = page.getByRole("textbox");
  await composer.fill("First question");
  await composer.press("Enter");
  await expect.poll(() => fixture.posts.length).toBe(1);
  await composer.fill("My next question");
  await navigateContext(page, workoutContext);
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toBeDisabled();
  await expect(composer).toHaveValue("My next question");
  await fixture.reply(0);
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toBeEnabled();
  await expect(composer).toHaveValue("My next question");
  expect(fixture.posts).toHaveLength(1);
});

test("signing into another account cannot consume a previous account's handoff or draft", async ({ page }) => {
  const fixture = await setup(page, { draft: "First account private question" });
  await navigateContext(page, workoutContext);
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Sign out", exact: true }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await page.route("**/me", route => route.fulfill({ json: { ...account, user_id: 2, email: "second@example.com", name: "Second athlete" } }));
  await page.getByRole("textbox", { name: "Email", exact: true }).fill("second@example.com");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await navigateContext(page, workoutContext);
  await expect(page.getByRole("textbox")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Review question", exact: true })).toHaveCount(0);
  expect(fixture.posts).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.getItem("apex.chat.2.draft"))).toBeNull();
});

test("context validation checks real calendar days and strips unrelated state", () => {
  expect(validatedCoachContext({ coachContext: { userId: 1, date: "2024-02-29", prompt: "private", note: "private" } }, 1)).toEqual({ userId: 1, date: "2024-02-29" });
  expect(validatedCoachContext({ coachContext: { userId: 1, date: "2025-02-29" } }, 1)).toBeNull();
  expect(validatedCoachContext({ coachContext: { userId: 1, date: "0000-01-01" } }, 1)).toBeNull();
  expect(validatedCoachContext(null, 1)).toBeNull();
});
