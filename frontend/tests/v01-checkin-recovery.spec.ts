import { expect, test, type Page } from "@playwright/test";
import { installApi, today } from "./fixtures";
import type { AthleteDay, Checkin } from "../src/features/athlete/types";

const initial = (activityId: number | null): Checkin => ({
  id: 90, activity_id: activityId, planned_session_id: activityId ? null : 12,
  revision: 1, status: "completed", rpe: 5, pain: false, felt_unwell: false,
  note: "Original feedback", fatigue: null, soreness: null, workout_quality: null,
  modification_reason: "", terrain_notes: "",
});

function dayFor(checkin: Checkin): AthleteDay {
  return {
    date: today, timezone: "UTC", training_focus: ["running"], state: "one_session", totals: {}, legacy_gym_sessions: [],
    sessions: checkin.activity_id ? [] : [{
      id: 12, plan_id: 2, plan_revision: 1, plan_title: "Synthetic plan", discipline: "running",
      start_time: "08:00:00", session_type: "Easy run", duration_min: 30, distance_m: null,
      description: null, protected: false, plan_protected: false, workout_protected: false,
      status: checkin.status, activity_id: null, checkin,
    }],
    activities: checkin.activity_id ? [{
      id: checkin.activity_id, discipline: "running", start_time: today + "T08:00:00Z",
      duration_s: 1800, distance_m: 4000, planned_session_id: null, association: "independent",
      candidate_session_ids: [], comparison: null, checkin,
    }] : [],
  };
}

async function openCheckin(page: Page) {
  await page.goto("/app");
  await page.getByTestId("daily-details").locator("summary").first().click();
  await page.locator("summary").filter({ hasText: "Quick post-session check-in" }).click();
}

test("conflicting planned-session feedback survives failed review and saves local edits only after explicit reconciliation", async ({ page }) => {
  await installApi(page, { empty: true });
  let checkin = initial(null);
  let failReview = false;
  const writes: Record<string, unknown>[] = [];
  await page.route("**/athlete/day**", route => {
    if (failReview) {
      failReview = false;
      return route.fulfill({ status: 503, json: { detail: "Temporary failure" } });
    }
    return route.fulfill({ json: dayFor(checkin) });
  });
  await page.route("**/athlete/checkins", route => {
    const body = route.request().postDataJSON();
    writes.push(body);
    if (writes.length === 1) {
      checkin = { ...checkin, revision: 2, note: "Saved on another device", rpe: 7 };
      return route.fulfill({ status: 409, json: { detail: "Check-in changed" } });
    }
    if (body.expected_revision !== checkin.revision) return route.fulfill({ status: 409, json: { detail: "Still stale" } });
    checkin = { ...checkin, ...body, revision: 3 };
    return route.fulfill({ json: checkin });
  });
  await openCheckin(page);
  const note = page.getByLabel("Optional note", { exact: true });
  const save = page.getByRole("button", { name: "Save check-in", exact: true });
  await note.fill("Keep my unsaved observations");
  await save.click();
  await expect(page.getByRole("alert")).toContainText("This record changed");
  await expect(save).toBeDisabled();

  failReview = true;
  await page.getByRole("button", { name: "Review the saved check-in", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "could not be loaded" })).toBeVisible();
  await expect(note).toHaveValue("Keep my unsaved observations");
  await expect(save).toBeDisabled();
  expect(writes).toHaveLength(1);

  await page.getByRole("button", { name: "Review the saved check-in", exact: true }).click();
  const review = page.getByRole("region", { name: "Review the saved check-in", exact: true });
  await expect(review).toContainText("Saved on another device");
  await expect(review).toContainText("Keep my unsaved observations");
  await expect(save).toBeDisabled();
  await page.getByRole("button", { name: "Keep my edits", exact: true }).click();
  await expect(review).toHaveCount(0);
  await expect(note).toHaveValue("Keep my unsaved observations");
  await expect(save).toBeEnabled();
  expect(writes).toHaveLength(1);

  await save.click();
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toMatchObject({ planned_session_id: 12, expected_revision: 2, note: "Keep my unsaved observations", rpe: 5 });
  expect(writes[1]).not.toHaveProperty("activity_id");
  await page.reload();
  await page.getByTestId("daily-details").locator("summary").first().click();
  await page.locator("summary").filter({ hasText: "Quick post-session check-in" }).click();
  await expect(note).toHaveValue("Keep my unsaved observations");
  await expect(save).toBeDisabled();
});

test("choosing the saved activity feedback discards local edits without another write", async ({ page }) => {
  await installApi(page, { empty: true });
  let checkin = initial(4);
  const writes: Record<string, unknown>[] = [];
  await page.route("**/athlete/day**", route => route.fulfill({ json: dayFor(checkin) }));
  await page.route("**/athlete/checkins", route => {
    writes.push(route.request().postDataJSON());
    checkin = { ...checkin, revision: 2, note: "Current activity feedback", status: "partial", rpe: 8 };
    return route.fulfill({ status: 409, json: { detail: "Check-in changed" } });
  });
  await openCheckin(page);
  const note = page.getByLabel("Optional note", { exact: true });
  await note.fill("Local draft to discard");
  await page.getByRole("button", { name: "Save check-in", exact: true }).click();
  await page.getByRole("button", { name: "Review the saved check-in", exact: true }).click();
  await expect(page.getByRole("region", { name: "Review the saved check-in", exact: true })).toContainText("Current activity feedback");
  await page.getByRole("button", { name: "Use saved version", exact: true }).click();
  await expect(note).toHaveValue("Current activity feedback");
  await expect(page.getByRole("combobox", { name: "How much did you complete?", exact: true })).toHaveValue("partial");
  await expect(page.getByRole("button", { name: "Save check-in", exact: true })).toBeDisabled();
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ activity_id: 4, expected_revision: 1 });
  expect(writes[0]).not.toHaveProperty("planned_session_id");
});
