import { expect, test, type Page } from "@playwright/test";
import { referencedProposalLinks } from "../src/features/coach/proposalLinks";
import { account, installApi } from "./fixtures";

function proposal(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id, kind: "session_patch", status: "draft",
    before: { target_id: id + 100, target_duration_min: 60 },
    after: { target_id: id + 100, target_duration_min: 45 },
    reason: `Synthetic proposal ${id}`, payload_hash: "a".repeat(64),
    snapshot_revision: "b".repeat(64), evidence_ids: [],
    expires_at: new Date(Date.now() + 86400000).toISOString(), receipt: null,
    ...overrides,
  };
}

async function reviewFixture(page: Page, drafts: ReturnType<typeof proposal>[], status = 200) {
  const { writes } = await installApi(page);
  const changesWrites: string[] = [];
  await page.route("**/lab/changes**", async route => {
    if (route.request().method() !== "GET") changesWrites.push(route.request().url());
    const id = /^\/lab\/changes\/(\d+)$/.exec(new URL(route.request().url()).pathname)?.[1];
    const selected = id ? drafts.find(draft => draft.id === Number(id)) : null;
    await route.fulfill({ status: status === 200 && id && !selected ? 404 : status,
      json: status !== 200 ? { detail: "Synthetic unavailable changes" } : id ? selected ?? { detail: "Draft not found" } : drafts });
  });
  return () => [...writes, ...changesWrites];
}

test("typed proposal references produce only unique positive safe integer anchors", () => {
  expect(referencedProposalLinks([
    { type: "change", id: 42, payload_hash: "a".repeat(64) },
    { type: "change", id: 42 }, { type: "change", id: 41 },
    { type: "change", id: 0 }, { type: "change", id: -1 },
    { type: "change", id: 1.5 }, { type: "change", id: "43" },
    { type: "change", id: Number.MAX_SAFE_INTEGER + 1 },
    { type: "change", id: Infinity }, { type: "change", id: NaN },
    { type: "other", id: 44 }, { id: 45 }, null, 46, [],
  ])).toEqual([
    { id: 42, href: "/app/coach?tab=changes#change-42" },
    { id: 41, href: "/app/coach?tab=changes#change-41" },
  ]);
  for (const invalid of [null, {}, "drafts", 12]) expect(referencedProposalLinks(invalid)).toEqual([]);
});

test("an older selected proposal loads beyond the newest 50 without hiding the other drafts", async ({ page }) => {
  const writes = await reviewFixture(page, Array.from({ length: 50 }, (_, index) => proposal(100 + index)));
  let release: (() => Promise<void>) | undefined;
  await page.route("**/lab/changes/41", route => { release = () => route.fulfill({ json: proposal(41) }); });
  await page.goto("/app/coach?tab=changes#change-41");
  await expect.poll(() => !!release).toBe(true);
  await expect(page.getByText("This proposal is unavailable.", { exact: false })).toHaveCount(0);
  await expect(page.locator("#change-100")).toBeVisible();
  await release!();
  await expect(page.locator("#change-41")).toBeFocused();
  await expect(page.locator("#change-41")).toHaveAttribute("data-selected", "true");
  await expect(page.locator('section[id^="change-"]')).toHaveCount(51);
  expect(writes()).toEqual([]);
});

test("a failed older-proposal read retries the exact ID and keeps unrelated drafts available", async ({ page }) => {
  const writes = await reviewFixture(page, [proposal(100)]);
  let failed = true;
  await page.route("**/lab/changes/41", route => route.fulfill({ status: failed ? 503 : 200, json: failed ? { detail: "Temporary failure" } : proposal(41) }));
  await page.goto("/app/coach?tab=changes#change-41");
  await expect(page.getByRole("alert")).toContainText("The proposal could not be loaded");
  await expect(page.locator("#change-100")).toBeVisible();
  await expect(page.locator('[data-selected="true"]')).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.locator("#change-41")).toBeFocused();
  expect(writes()).toEqual([]);
});

test("an older proposal cached for one account is unavailable after another account signs in", async ({ page }) => {
  await reviewFixture(page, [proposal(100)]);
  let owner = true;
  await page.route("**/lab/changes/41", route => route.fulfill({ status: owner ? 200 : 404,
    json: owner ? proposal(41, { reason: "First account private proposal" }) : { detail: "Draft not found" } }));
  await page.goto("/app/coach?tab=changes#change-41");
  await expect(page.getByText("First account private proposal", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  owner = false;
  await page.route("**/me", route => route.fulfill({ json: { ...account, user_id: 2, email: "second@example.com", name: "Second athlete" } }));
  await page.getByRole("textbox", { name: "Email", exact: true }).fill("second@example.com");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.evaluate(() => {
    history.pushState({ key: crypto.randomUUID() }, "", "/app/coach?tab=changes#change-41");
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByRole("alert")).toContainText("This proposal is unavailable");
  await expect(page.getByText("First account private proposal", { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-selected="true"]')).toHaveCount(0);
});

test("a Coach reference opens and focuses its exact owned proposal while other drafts remain visible", async ({ page }) => {
  const writes = await reviewFixture(page, [proposal(41), proposal(42)]);
  await page.addInitScript(() => localStorage.setItem("apex.chat.1.active", "7"));
  const row = { id: 7, title: "Synthetic review", message_count: 1, started_at: "2026-10-17T10:00:00Z", last_activity_at: "2026-10-17T10:00:00Z" };
  await page.route(url => /^\/coach\/chats(?:\/7)?$/.test(url.pathname), route => route.fulfill({ json: new URL(route.request().url()).pathname.endsWith("/7")
    ? { ...row, messages: [{ id: 1, role: "assistant", content: "Review this specific change.", referenced_data: { drafts: [{ type: "change", id: 42, payload_hash: "a".repeat(64) }] } }] }
    : [row] }));
  await page.goto("/app/coach");
  const reference = page.locator('a[href="/app/coach?tab=changes#change-42"]');
  await expect(reference).toHaveCount(1);
  await reference.click();
  await expect(page).toHaveURL(/tab=changes#change-42$/);
  await expect(page.locator("#change-42")).toBeFocused();
  await expect(page.locator("#change-42")).toHaveAttribute("data-selected", "true");
  await expect(page.locator("#change-41")).not.toHaveAttribute("data-selected", "true");
  await expect(page.getByText("Synthetic proposal 41", { exact: true })).toBeVisible();
  await expect(page.getByText("Synthetic proposal 42", { exact: true })).toBeVisible();
  expect(writes()).toEqual([]);
});

test("a missing owned proposal has a clear escape and never selects an unrelated draft", async ({ page }) => {
  const writes = await reviewFixture(page, [proposal(41), proposal(42)]);
  await page.goto("/app/coach?tab=changes#change-999");
  await expect(page.getByRole("alert")).toContainText("This proposal is unavailable");
  await expect(page.locator('[data-selected="true"]')).toHaveCount(0);
  await expect(page.locator("#change-41")).not.toBeFocused();
  await page.getByRole("button", { name: "Show all proposals", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/coach\?tab=changes$/);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator("#change-42")).toBeVisible();
  expect(writes()).toEqual([]);
});

test("a failed proposal fetch offers retry and show all without approving anything", async ({ page }) => {
  const writes = await reviewFixture(page, [], 503);
  await page.goto("/app/coach?tab=changes#change-42");
  await expect(page.getByText("The proposal could not be loaded. Try again or show all proposals.", { exact: true })).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Show all proposals", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/coach\?tab=changes$/);
  expect(writes()).toEqual([]);
});

test("invalid proposal anchors never select a draft or trigger a mutation", async ({ page }) => {
  const writes = await reviewFixture(page, [proposal(41)]);
  for (const hash of ["change-0", "change--1", "change-1.5", "change-9007199254740992", "change-"]) {
    await page.goto(`/app/coach?tab=changes#${hash}`);
    await expect(page.getByRole("alert")).toContainText("This proposal link is invalid.");
    await expect(page.locator('[data-selected="true"]')).toHaveCount(0);
  }
  expect(writes()).toEqual([]);
});

test("an applied session receipt links only to its valid exact workout", async ({ page }) => {
  const applied = { status: "applied_locally", receipt: { state: "applied_locally", external_delivery: "not_requested", undo_available: true } };
  const writes = await reviewFixture(page, [
    proposal(41, { ...applied, after: { target_id: 141, target_duration_min: 45 } }),
    proposal(42, { ...applied, after: { target_id: -1 } }),
    proposal(43, { ...applied, after: { target_id: "143" } }),
    proposal(44, { ...applied, kind: "context_patch" }),
    proposal(45, { ...applied, status: "undone" }),
    proposal(46, { ...applied, after: { target_id: Number.MAX_SAFE_INTEGER + 1 } }),
  ]);
  await page.goto("/app/coach?tab=changes#change-41");
  const workout = page.getByRole("link", { name: "View updated workout", exact: true });
  await expect(workout).toHaveCount(1);
  await expect(workout).toHaveAttribute("href", "/app/workouts/141");
  await expect(page.locator("#change-41").getByRole("button", { name: "Undo local change", exact: true })).toBeVisible();
  expect(writes()).toEqual([]);
});
