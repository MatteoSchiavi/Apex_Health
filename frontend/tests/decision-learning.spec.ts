import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { installApi, today } from "./fixtures";

async function decisionApi(page: Page, options: { empty?: boolean; locale?: "en" | "it" } = {}) {
  await installApi(page, options);
  const incomplete = !!options.empty;
  const decision = {
    id: 12, date: today, action: incomplete ? "collect_more_data" : "reduce_volume",
    state: incomplete ? "insufficient_data" : "adjustment_suggested",
    headline: options.locale === "it" ? "Mantieni l’obiettivo, riduci il volume" : incomplete ? "Add current evidence before adjusting training" : "Keep the focus, reduce the volume",
    reasons: [incomplete ? "Current measurements are missing." : "Recorded sleep was shorter than six hours; use a conservative volume adjustment."],
    contributors: [options.locale === "it" ? "Il sonno registrato è inferiore a sei ore." : incomplete ? "Current measurements are missing." : "Recorded sleep was shorter than six hours; use a conservative volume adjustment."],
    evidence: incomplete ? [] : [{ id: "observation:7:1", metric: "sleep_duration", value: 5.5, unit: "h", origin: "garmin", local_date: today }],
    key_changes: incomplete ? [] : [{ metric: "sleep_duration", current: 5.5, baseline: null, delta: null, origin: "garmin" }],
    data_completeness: { coverage_pct: incomplete ? 0 : 100, missing: incomplete ? ["hrv_overnight_rmssd"] : [] },
    data_coverage: { coverage_pct: incomplete ? 0 : 100, missing: incomplete ? ["hrv_overnight_rmssd"] : [] },
    confidence: incomplete ? "limited" : "supported_by_coverage",
    recommended_action: { action: incomplete ? "collect_more_data" : "reduce_volume", reason: "Review a small session change before applying it.", planned_session_id: 55 },
    alternatives: [{ action: "swap_session", reason: "Choose an easy technical session or low-impact movement." }],
    counterfactual: "New observations or a symptom note may change this decision.", next_step: "Review a small session change.",
    formula_version: "daily-decision-v1", limitations: ["Planning rules are not a diagnosis."],
    outcome: null as Record<string, unknown> | null,
  };
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/lab/decision**", async (route) => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path !== "/lab/decision" && path !== "/lab/decision/12/outcome") return route.fallback();
    if (req.method() === "POST") {
      const body = req.postDataJSON();
      writes.push({ path, body });
      decision.outcome = { ...decision.outcome, ...body };
      return route.fulfill({ json: { id: 12, outcome: decision.outcome } });
    }
    return route.fulfill({ json: decision });
  });
  await page.route("**/lab/constraints?**", (route) => route.fulfill({ json: { date: today, events: [], sessions: [{ id: 55, date: today, session_type: "easy", description: "Easy ride", duration_min: 40 }] } }));
  await page.route("**/lab/changes", (route) => route.fulfill({ json: [{ id: 41, kind: "session_patch", status: "draft", after: { target_id: 55, date: today }, before: { target_id: 55, date: today }, reason: "Less volume", payload_hash: "a".repeat(64) }] }));
  return { decision, writes };
}

test("daily interpretation leads the overview and evidence stays progressive", async ({ page }) => {
  await decisionApi(page);
  await page.goto("/app");
  await page.locator("summary").filter({ hasText: /Recovery context and daily guidance|Contesto di recupero/ }).click();
  const daily = page.getByText("Today's training decision", { exact: true });
  const signals = page.getByRole("heading", { name: "Recorded signals", exact: true });
  await expect(daily).toBeVisible();
  await expect(page.getByRole("heading", { name: "Keep the focus, reduce the volume" })).toBeVisible();
  expect(await daily.evaluate((node) => !!(node.compareDocumentPosition(document.querySelector('section[aria-label="Recorded signals"]')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await expect(signals).toBeVisible();
  await expect(page.getByRole("link", { name: "Ask Apex about this decision" })).toHaveAttribute("href", "/app/coach");
  await expect(page.getByText("Comparable baseline unavailable")).not.toBeVisible();
  await page.getByText("Evidence and alternatives", { exact: true }).click();
  await expect(page.getByText("Comparable baseline unavailable")).toBeVisible();
  await expect(page.getByText(`garmin · Measured ${today}`)).toBeVisible();
  await expect(page.getByText("Planning rules are not a diagnosis.")).toBeVisible();
});

test("optional influence and session feedback reuse outcome without approving a proposal", async ({ page }) => {
  const { writes } = await decisionApi(page);
  await page.goto("/app");
  await page.locator("summary").filter({ hasText: /Recovery context and daily guidance|Contesto di recupero/ }).click();
  await page.getByRole("button", { name: "Modified", exact: true }).click();
  await expect(page.getByRole("button", { name: "Modified", exact: true })).toBeDisabled();
  await page.getByText("Did this help your plan?", { exact: true }).click();
  await page.getByLabel("Influenced my plan").selectOption("partly");
  await page.getByLabel("Was this useful?").selectOption("yes");
  await page.getByLabel("Reason or note (optional)").fill("Shorter ride fit my day");
  await page.getByRole("button", { name: "Save feedback" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Feedback saved" })).toBeVisible();
  expect(writes.at(-1)?.body).toMatchObject({ state: "modified", influenced_plan: "partly", useful: true, notes: "Shorter ride fit my day", planned_session_id: 55 });
  expect(writes.at(-1)?.body).not.toHaveProperty("pain");
  await page.getByText("After your session (optional)", { exact: true }).click();
  await page.getByLabel("Session completion").selectOption("partial");
  await page.getByLabel("Effort · RPE (0–10)").fill("4.5");
  await page.getByLabel("Soreness (0–10)").fill("2");
  await page.getByRole("combobox", { name: /^Pain/ }).selectOption("no");
  await page.getByLabel("Related proposal").selectOption("41");
  await page.getByRole("button", { name: "Save feedback" }).click();
  await expect.poll(() => writes.at(-1)?.body.completion).toBe("partial");
  expect(writes.at(-1)?.body).toMatchObject({ state: "modified", draft_id: 41, planned_session_id: 55, completion: "partial", rpe: 4.5, soreness: 2, pain: false });
  expect(writes.every((write) => write.path === "/lab/decision/12/outcome")).toBe(true);
  await page.getByRole("button", { name: "Decide later", exact: true }).click();
  expect(writes.at(-1)?.body).toEqual({ state: "snoozed" });
});

test("empty current overview still explains incomplete evidence", async ({ page }) => {
  await decisionApi(page, { empty: true });
  await page.goto("/app");
  await page.locator("summary").filter({ hasText: /Recovery context and daily guidance|Contesto di recupero/ }).click();
  await expect(page.getByRole("heading", { name: "Add current evidence before adjusting training" })).toBeVisible();
  await expect(page.getByText("0% of required signals covered")).toBeVisible();
  await expect(page.getByText("Did this help your plan?", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Decide later", exact: true }).click();
  await page.getByText("Did this help your plan?", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Save feedback" })).toBeEnabled();
});

test("Italian mobile decision feedback is localized and accessible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await decisionApi(page, { locale: "it" });
  await page.goto("/app");
  await page.locator("summary").filter({ hasText: /Recovery context and daily guidance|Contesto di recupero/ }).click();
  await expect(page.getByRole("heading", { name: "Mantieni l’obiettivo, riduci il volume" })).toBeVisible();
  await page.getByRole("button", { name: "Modificata", exact: true }).click();
  await page.getByText("Ti è stato utile per il piano?", { exact: true }).click();
  await expect(page.getByLabel("Ha influenzato il mio piano")).toBeVisible();
  await expect(page.getByRole("link", { name: "Chiedi ad Apex questa decisione" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(result.violations).toEqual([]);
});

test("editing a session proposal requires review and approval of its replacement hash", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApi(page);
  let drafts = [{
    id: 41, kind: "session_patch", status: "draft", reason: "Less volume",
    before: { target_id: 55, date: today, target_duration_min: 40, description: "Original session" },
    after: { target_id: 55, date: today, target_duration_min: 28, description: "Shortened session" },
    payload_hash: "a".repeat(64), snapshot_revision: "test", evidence_ids: [],
    expires_at: new Date(Date.now() + 86_400_000).toISOString(), receipt: null,
  }];
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/lab/changes**", async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path === "/lab/changes") return route.fulfill({ json: drafts });
    if (request.method() !== "POST") return route.fallback();
    const body = request.postDataJSON();
    writes.push({ path, body });
    if (path === "/lab/changes/41/edit") {
      const original = drafts[0];
      const replacement = { ...original, id: 42, reason: body.reason, payload_hash: "b".repeat(64), after: { ...original.after, target_duration_min: body.target_duration_min, description: body.description } };
      drafts = [{ ...original, status: "superseded" }, replacement];
      return route.fulfill({ json: replacement });
    }
    if (path === "/lab/changes/42/approve") {
      drafts = drafts.map((draft) => draft.id === 42 ? { ...draft, status: "applied_locally" } : draft);
      return route.fulfill({ json: drafts[1] });
    }
    return route.fulfill({ status: 409, json: { detail: "Use the replacement proposal" } });
  });
  await page.goto("/app/coach?tab=changes");
  await page.getByRole("button", { name: "Edit proposal", exact: true }).click();
  await expect(page.getByRole("button", { name: "Approve this change", exact: true })).toHaveCount(0);
  await page.getByLabel("Duration · min").fill("24");
  await page.getByLabel("Session description").fill("Easy recovery ride");
  await page.getByLabel("Reason for the edit").fill("Fit the available time");
  await page.getByRole("button", { name: "Save replacement proposal", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("needs a new review and approval");
  await expect(page.getByText("Replaced by an edited proposal", { exact: true })).toBeVisible();
  await expect(page.getByText("24", { exact: true })).toBeVisible();
  await expect(page.getByText("Easy recovery ride", { exact: true })).toBeVisible();
  expect(writes).toEqual([{ path: "/lab/changes/41/edit", body: { target_duration_min: 24, description: "Easy recovery ride", reason: "Fit the available time" } }]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Approve this change", exact: true }).click();
  await expect.poll(() => writes.at(-1)?.path).toBe("/lab/changes/42/approve");
  expect(writes.at(-1)?.body).toEqual({ payload_hash: "b".repeat(64) });
});
