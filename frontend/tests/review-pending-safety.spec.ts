import { test, expect, type Page } from "@playwright/test";
import { installApi, today } from "./fixtures";

function responseGate() {
  let release!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  return { ready, release: () => release() };
}

async function templateApi(page: Page) {
  await installApi(page, { aiConsent: false });
  const workout = { discipline: "running", session_type: "Easy run", duration_min: 30, distance_m: null, start_time: null, description: "Conversational effort", intensity_targets: {}, protected: false };
  const templates = [31, 32].map(id => ({ id, revision: 1, source_document_id: 4, source_document_revision: 2, import_draft_id: 1, structure: { title: `Easy week ${id}`, notes: "", rows: [{ ...workout, id: "row-1", day: 0 }] } }));
  await page.route("**/athlete/templates", route => route.fulfill({ json: templates }));
  const gate = responseGate();
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/athlete/templates/31/preview", async route => {
    const body = route.request().postDataJSON();
    writes.push({ path: "/athlete/templates/31/preview", body });
    await gate.ready;
    await route.fulfill({ json: { id: 51, document_id: null, template_id: 31, template_revision: 1, version: 1, payload_hash: "d".repeat(64), status: "draft", confirmed_at: null, structure: { title: "Easy week 31", starts_on: body.starts_on, ends_on: body.ends_on, weekly_structure: "", protected: false, ambiguities: [], sessions: [{ ...workout, date: body.starts_on }] } } });
  });
  return { gate, writes };
}

test("template dates stay bound to the pending preview and changing them removes its approval", async ({ page }) => {
  const { gate, writes } = await templateApi(page);
  await page.goto("/app/lab?tab=documents#template-31");
  const start = page.getByLabel("Start date", { exact: true });
  const end = page.getByLabel("End date", { exact: true });
  await start.fill("2026-10-19");
  await end.fill("2026-10-25");
  await page.getByRole("button", { name: "Preview calendar", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(start).toBeDisabled();
  await expect(end).toBeDisabled();
  for (const button of await page.getByRole("button", { name: "Choose dates and preview", exact: true }).all()) await expect(button).toBeDisabled();
  gate.release();
  const calendar = page.getByRole("region", { name: "Full calendar preview", exact: true });
  await expect(calendar).toContainText("2026-10-19 – 2026-10-25");
  await expect(start).toBeEnabled();
  await expect(end).toHaveValue("2026-10-25");
  await start.fill("2026-10-20");
  await expect(calendar).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Activate this reviewed plan", exact: true })).toHaveCount(0);
  expect(writes).toEqual([{ path: "/athlete/templates/31/preview", body: { expected_revision: 1, starts_on: "2026-10-19", ends_on: "2026-10-25" } }]);
});

test("a hash change during preview cannot attach the old calendar to another template", async ({ page }) => {
  const { gate, writes } = await templateApi(page);
  await page.goto("/app/lab?tab=documents#template-31");
  const start = page.getByLabel("Start date", { exact: true });
  await start.fill("2026-10-19");
  await page.getByLabel("End date", { exact: true }).fill("2026-10-25");
  await page.getByRole("button", { name: "Preview calendar", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await page.evaluate(() => { window.location.hash = "#template-32"; });
  await expect(page).toHaveURL(/#template-32$/);
  await expect(start).toBeDisabled();
  await expect(start).toHaveValue("2026-10-19");
  gate.release();
  await expect(start).toBeEnabled();
  await expect(start).toHaveValue("");
  await expect(page.getByLabel("End date", { exact: true })).toHaveValue("");
  await expect(page.getByRole("region", { name: "Full calendar preview", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Preview calendar", exact: true })).toBeDisabled();
  expect(writes).toHaveLength(1);
});

function proposal(id: number) {
  return { id, kind: "session_patch", status: "draft", reason: `Less volume ${id}`, before: { target_id: 55, date: today, target_duration_min: 40, description: "Original session" }, after: { target_id: 55, date: today, target_duration_min: 28, description: "Shortened session" }, payload_hash: "a".repeat(64), snapshot_revision: "test", evidence_ids: [], expires_at: new Date(Date.now() + 86_400_000).toISOString(), receipt: null };
}

test("proposal fields freeze until replacement completes and approval uses the replacement hash", async ({ page }) => {
  await installApi(page);
  const original = proposal(41);
  let drafts = [original];
  const gate = responseGate();
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/lab/changes**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path === "/lab/changes") return route.fulfill({ json: drafts });
    if (request.method() !== "POST") return route.fallback();
    const body = request.postDataJSON();
    writes.push({ path, body });
    if (path === "/lab/changes/41/edit") {
      await gate.ready;
      const replacement = { ...original, id: 42, reason: body.reason, payload_hash: "b".repeat(64), after: { ...original.after, target_duration_min: body.target_duration_min, description: body.description } };
      drafts = [{ ...original, status: "superseded" }, replacement];
      return route.fulfill({ json: replacement });
    }
    if (path === "/lab/changes/42/approve") {
      drafts = drafts.map(draft => draft.id === 42 ? { ...draft, status: "applied_locally" } : draft);
      return route.fulfill({ json: drafts[1] });
    }
    return route.fulfill({ status: 409, json: { detail: "Use the replacement proposal" } });
  });
  await page.goto("/app/coach?tab=changes#change-41");
  await page.getByRole("button", { name: "Edit proposal", exact: true }).click();
  await page.getByLabel("Duration · min").fill("24");
  await page.getByLabel("Session description").fill("Easy recovery ride");
  await page.getByLabel("Reason for the edit").fill("Fit the available time");
  await page.getByRole("button", { name: "Save replacement proposal", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(page.getByLabel("Duration · min")).toBeDisabled();
  await expect(page.getByLabel("Session description")).toBeDisabled();
  await expect(page.getByLabel("Reason for the edit")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
  gate.release();
  await expect(page).toHaveURL(/#change-42$/);
  await expect(page.locator("#change-42")).toContainText("Easy recovery ride");
  expect(writes).toEqual([{ path: "/lab/changes/41/edit", body: { reason: "Fit the available time", description: "Easy recovery ride", target_duration_min: 24 } }]);
  await page.locator("#change-42").getByRole("button", { name: "Approve this change", exact: true }).click();
  await expect.poll(() => writes.at(-1)?.path).toBe("/lab/changes/42/approve");
  expect(writes.at(-1)?.body).toEqual({ payload_hash: "b".repeat(64) });
});

test("dirty proposal edits require confirmation before cancel or switching proposals", async ({ page }) => {
  await installApi(page);
  const drafts = [proposal(41), proposal(43)];
  const writes: string[] = [];
  await page.route("**/lab/changes**", route => {
    if (route.request().method() !== "GET") writes.push(route.request().url());
    return route.fulfill({ json: drafts });
  });
  await page.goto("/app/coach?tab=changes");
  await page.locator("#change-41").getByRole("button", { name: "Edit proposal", exact: true }).click();
  const reason = page.getByLabel("Reason for the edit");
  await reason.fill("Keep my unfinished correction");
  let confirmations = 0;
  page.on("dialog", async dialog => { confirmations++; await dialog.dismiss(); });
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(reason).toHaveValue("Keep my unfinished correction");
  await page.locator("#change-43").getByRole("button", { name: "Edit proposal", exact: true }).click();
  await expect(page.locator("#change-41").getByLabel("Reason for the edit")).toHaveValue("Keep my unfinished correction");
  await expect(page.locator("#change-43").getByLabel("Reason for the edit")).toHaveCount(0);
  expect(confirmations).toBe(2);
  page.removeAllListeners("dialog");
  page.once("dialog", dialog => dialog.accept());
  await page.locator("#change-43").getByRole("button", { name: "Edit proposal", exact: true }).click();
  await expect(page.locator("#change-43").getByLabel("Reason for the edit")).toHaveValue("Less volume 43");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Reason for the edit")).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("showing all proposals preserves a dirty editor loaded outside the latest list", async ({ page }) => {
  await installApi(page);
  await page.route("**/lab/changes", route => route.fulfill({ json: [proposal(43)] }));
  await page.route("**/lab/changes/41", route => route.fulfill({ json: proposal(41) }));
  await page.goto("/app/coach?tab=changes#change-41");
  await page.locator("#change-41").getByRole("button", { name: "Edit proposal", exact: true }).click();
  await page.getByLabel("Reason for the edit").fill("Keep this older proposal correction");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "Show all proposals", exact: true }).click();
  await expect(page).toHaveURL(/#change-41$/);
  await expect(page.getByLabel("Reason for the edit")).toHaveValue("Keep this older proposal correction");
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Show all proposals", exact: true }).click();
  await expect(page).toHaveURL(/tab=changes$/);
  await expect(page.getByLabel("Reason for the edit")).toHaveCount(0);
});
