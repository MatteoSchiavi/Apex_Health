import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";
import { proposalFields } from "../src/features/coach/ProposalValues";

// All records and writes in this file are synthetic route fixtures.
for (const locale of ["en", "it"] as const) test(`focused Coach starters remain editable and history supports keyboard dismissal (${locale})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const fixture = await installApi(page, { locale });
  const row = { id: 7, title: "Synthetic saved question", last_activity_at: "2026-10-20T09:00:00Z", started_at: "2026-10-20T09:00:00Z", message_count: 1 };
  await page.route("**/coach/chats", route => route.fulfill({ json: [row] }));
  await page.route("**/coach/chats/7", route => route.fulfill({ json: { ...row, messages: [{ id: 1, role: "user", content: "Synthetic saved content", referenced_data: null }] } }));
  await page.goto("/app/coach");
  const history = page.getByRole("button", { name: locale === "en" ? /Past conversations/ : /Conversazioni passate/ });
  await expect(history).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: /^Synthetic saved question/ })).toHaveCount(0);
  for (const label of locale === "en" ? ["Understand today", "Adapt a workout", "Review my week"] : ["Capire la giornata", "Adattare un allenamento", "Rivedere la settimana"]) {
    await page.getByRole("textbox").fill("");
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("textbox")).toBeFocused();
    expect((await page.getByRole("textbox").inputValue()).length).toBeGreaterThan(40);
  }
  const composer = page.getByRole("textbox");
  await composer.fill("My own editable question, saved for later.");
  await page.reload();
  await expect(composer).toHaveValue("My own editable question, saved for later.");
  await history.focus();
  await history.press("Enter");
  await expect(history).toHaveAttribute("aria-expanded", "true");
  const saved = page.getByRole("button", { name: /^Synthetic saved question/ });
  await saved.focus();
  await saved.press("Escape");
  await expect(history).toHaveAttribute("aria-expanded", "false");
  await expect(history).toBeFocused();
  await history.click();
  await saved.click();
  await expect(history).toHaveAttribute("aria-expanded", "false");
  await expect(composer).toBeFocused();
  await expect(composer).toHaveValue("My own editable question, saved for later.");
  await expect(page.getByText("Synthetic saved content", { exact: true })).toBeVisible();
  expect(fixture.writes).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`coach-focused-${locale}.png`), fullPage: true });
});

for (const locale of ["en", "it"] as const) for (const width of [390, 1440]) test(`empty and existing Coach conversations keep composer and send in ${width}x844 viewport (${locale})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 844 });
  await installApi(page, { locale });
  const row = { id: 7, title: "Synthetic saved question", last_activity_at: "2026-10-20T09:00:00Z", started_at: "2026-10-20T09:00:00Z", message_count: 2 };
  await page.route("**/coach/chats", route => route.fulfill({ json: [row] }));
  await page.route("**/coach/chats/7", route => route.fulfill({ json: { ...row, messages: [
    { id: 1, role: "user", content: "Synthetic saved question", referenced_data: null },
    { id: 2, role: "assistant", content: "A long recorded response to exercise transcript scrolling.\n".repeat(30), referenced_data: null },
  ] } }));
  await page.goto("/app/coach");
  const composer = page.getByRole("textbox");
  const send = page.getByRole("button", { name: locale === "en" ? "Send" : "Invia", exact: true });
  const navigation = page.locator("div.fixed.inset-x-0.bottom-0 > nav");
  for (const state of ["empty", "existing"]) {
    if (state === "existing") {
      await page.getByRole("button", { name: locale === "en" ? /Past conversations/ : /Conversazioni passate/ }).click();
      await page.getByRole("button", { name: /^Synthetic saved question/ }).click();
      await expect(page.getByText("A long recorded response", { exact: false })).toHaveCount(1);
    }
    await expect(composer).toBeInViewport({ ratio: 1 });
    await expect(send).toBeInViewport({ ratio: 1 });
    if (width === 390) {
      const navTop = (await navigation.boundingBox())!.y;
      const composerBox = (await composer.boundingBox())!;
      const sendBox = (await send.boundingBox())!;
      expect(composerBox.y + composerBox.height).toBeLessThan(navTop);
      expect(sendBox.y + sendBox.height).toBeLessThan(navTop);
    }
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await page.screenshot({ path: testInfo.outputPath(`coach-viewport-${width}-${state}-${locale}.png`) });
  }
});

for (const locale of ["en", "it"] as const) test(`starter replacement requires an explicit choice and persists without sending (${locale})`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApi(page, { locale });
  let posts = 0;
  await page.route("**/coach/chats", route => {
    if (route.request().method() === "POST") posts++;
    return route.fulfill({ json: [] });
  });
  await page.goto("/app/coach");
  const composer = page.getByRole("textbox");
  const unfinished = "My unfinished question must be preserved.";
  await composer.fill(unfinished);
  const starter = page.getByRole("button", { name: locale === "en" ? "Review my week" : "Rivedere la settimana", exact: true });
  await starter.click();
  await expect(composer).toHaveValue(unfinished);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("apex.chat.1.draft"))).toBe(unfinished);
  await page.getByRole("button", { name: locale === "en" ? "Keep existing question" : "Mantieni la domanda esistente", exact: true }).click();
  await expect(composer).toHaveValue(unfinished);
  await expect(composer).toBeFocused();
  await page.reload();
  await expect(composer).toHaveValue(unfinished);
  await starter.click();
  await expect(composer).toHaveValue(unfinished);
  await page.getByRole("button", { name: locale === "en" ? "Replace with starter question" : "Sostituisci con la domanda iniziale", exact: true }).click();
  await expect(composer).toBeFocused();
  const replacement = await composer.inputValue();
  expect(replacement).toContain(locale === "en" ? "this training week" : "questa settimana");
  expect(replacement).not.toBe(unfinished);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("apex.chat.1.draft"))).toBe(replacement);
  await page.reload();
  await expect(composer).toHaveValue(replacement);
  expect(posts).toBe(0);
});

for (const locale of ["en", "it"] as const) test(`proposal review labels exact values and keeps unknown changes visible (${locale})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const fixture = await installApi(page, { locale });
  const draft = { id: 41, kind: "session_patch", status: "draft", reason: "Synthetic proposal review", before: { target_id: 987654, date: "2026-10-29", target_duration_min: 60, description: null, _future_field: { exact_amount: 0.125, enabled: false } }, after: { target_id: 987654, date: "2026-10-29", target_duration_min: 45, description: "Keep this exact workout instruction.", _future_field: { exact_amount: 0, enabled: true } }, payload_hash: "a".repeat(64), snapshot_revision: "b".repeat(64), evidence_ids: [], expires_at: "2099-01-01T00:00:00Z", receipt: null };
  await page.route("**/lab/changes", route => route.fulfill({ json: [draft] }));
  await page.goto("/app/coach?tab=changes#change-41");
  const selected = page.locator("#change-41");
  await expect(selected).toBeFocused();
  await expect(selected).toHaveAttribute("data-selected", "true");
  await expect(selected.getByText(locale === "en" ? "Duration" : "Durata", { exact: true })).toHaveCount(2);
  await expect(selected.getByText("60 min", { exact: true })).toBeVisible();
  await expect(selected.getByText("45 min", { exact: true })).toBeVisible();
  await expect(selected.getByText("0.125", { exact: true })).toBeVisible();
  await expect(selected.getByText("0", { exact: true })).toBeVisible();
  await expect(selected.getByText("_future_field", { exact: true })).toHaveCount(2);
  await expect(selected.getByText("987654", { exact: true }).first()).not.toBeVisible();
  await expect(selected.getByRole("button", { name: locale === "en" ? "Approve this change" : "Approva questa modifica", exact: true })).toBeVisible();
  await expect(selected.getByRole("button", { name: locale === "en" ? "Reject" : "Rifiuta", exact: true })).toBeVisible();
  await selected.locator("details > summary").click();
  await expect(selected.getByText("987654", { exact: true }).first()).toBeVisible();
  expect(fixture.writes).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`proposal-focused-${locale}.png`), fullPage: true });
});

test("only known bookkeeping fields move into proposal details", () => {
  const payload = { target_id: 87, payload_hash: "exact-hash", target_duration_min: 45, _unknown: false, future_id: 99, content: "Exact text\nwith spaces " };
  expect(proposalFields(payload)).toEqual({ target_duration_min: 45, _unknown: false, future_id: 99, content: "Exact text\nwith spaces " });
  expect(proposalFields(payload, true)).toEqual({ target_id: 87, payload_hash: "exact-hash" });
});
