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

async function installWorkout(page: Page) {
  await page.route("**/athlete/planned-sessions/12/workout", route => route.fulfill({ json: {
    planned_session_id: 12, plan_revision: 1, protected: false, editable: false,
    edit_block_reason: "recorded", workout: null, education: [],
    session: { date: today, discipline: "running", session_type: "Easy run", duration_min: 30, description: "Comfortable effort" },
  } }));
}

function linkedDay(checkin: Checkin): AthleteDay {
  const day = dayFor(initial(null));
  day.sessions[0] = { ...day.sessions[0], activity_id: checkin.activity_id, checkin };
  day.activities = dayFor({ ...checkin, activity_id: 44 }).activities;
  day.activities[0] = { ...day.activities[0], planned_session_id: 12, association: "confirmed", checkin };
  return day;
}

for (const destination of ["day", "workout"] as const) {
  for (const choice of ["keep", "saved"] as const) {
    test(`${destination} feedback survives a new activity association until the athlete chooses ${choice}`, async ({ page }) => {
      await installApi(page, { empty: true });
      await installWorkout(page);
      let day = dayFor(initial(null));
      day.sessions[0] = { ...day.sessions[0], status: "planned", checkin: null };
      const writes: Record<string, unknown>[] = [];
      let current = { ...initial(44), planned_session_id: 12, revision: 2, note: "Saved recorded feedback" };
      await page.route("**/athlete/day**", route => route.fulfill({ json: day }));
      await page.route("**/athlete/checkins", route => {
        const body = route.request().postDataJSON();
        writes.push(body);
        if (writes.length === 1) {
          day = linkedDay(current);
          // The real API rejects skipping a newly recorded session before
          // checking the feedback revision.
          return route.fulfill({ status: 422, json: { detail: "Recorded associated activity cannot be skipped" } });
        }
        expect(body).toMatchObject({ planned_session_id: 12, expected_revision: 2 });
        expect(body).not.toHaveProperty("activity_id");
        current = { ...current, ...body, revision: 3 };
        day = linkedDay(current);
        return route.fulfill({ json: current });
      });
      if (destination === "day") await openCheckin(page);
      else await page.goto("/app/workouts/12");
      const note = page.getByLabel("Optional note", { exact: true });
      const result = page.getByRole("combobox", { name: "How much did you complete?", exact: true });
      const save = page.getByRole("button", { name: "Save check-in", exact: true });
      await note.fill("Unsaved observations before sync");
      await result.selectOption("skipped");
      await save.click();
      await page.getByRole("button", { name: "Review the saved check-in", exact: true }).click();
      const review = page.getByRole("region", { name: "Review the saved check-in", exact: true });
      await expect(review).toContainText("Saved recorded feedback");
      await expect(review).toContainText("Unsaved observations before sync");
      await expect(review).toContainText("recorded activity has changed");
      await expect(note).toHaveValue("Unsaved observations before sync");
      expect(writes).toHaveLength(1);
      if (choice === "keep") {
        await page.getByRole("button", { name: "Keep my edits", exact: true }).click();
        await expect(note).toHaveValue("Unsaved observations before sync");
        await expect(result).toHaveValue("skipped");
        await expect(save).toBeDisabled();
        await expect(page.getByRole("alert")).toContainText("now has a recorded activity");
        await result.selectOption("partial");
        await save.click();
        await expect.poll(() => writes.length).toBe(2);
        expect(writes[1]).toMatchObject({ status: "partial", note: "Unsaved observations before sync" });
      } else {
        await page.getByRole("button", { name: "Use saved version", exact: true }).click();
      }
      await expect(note).toHaveValue(choice === "keep" ? "Unsaved observations before sync" : "Saved recorded feedback");
      expect(writes).toHaveLength(choice === "keep" ? 2 : 1);
      await page.reload();
      if (destination === "day") {
        await page.getByTestId("daily-details").locator("summary").first().click();
        await page.locator("summary").filter({ hasText: "Quick post-session check-in" }).click();
      }
      await expect(note).toHaveValue(choice === "keep" ? "Unsaved observations before sync" : "Saved recorded feedback");
      await expect(save).toBeDisabled();
    });
  }
}

test("workout feedback stays with its opened workout when the activity is reassociated elsewhere", async ({ page }) => {
  await installApi(page, { empty: true });
  await installWorkout(page);
  let day = linkedDay({ ...initial(44), planned_session_id: 12 });
  const writes: Record<string, unknown>[] = [];
  await page.route("**/athlete/day**", route => route.fulfill({ json: day }));
  await page.route("**/athlete/checkins", route => {
    const body = route.request().postDataJSON();
    writes.push(body);
    if (writes.length === 1) {
      day.sessions[0] = { ...day.sessions[0], activity_id: null, checkin: null, status: "planned" };
      day.activities[0] = { ...day.activities[0], planned_session_id: 99,
        checkin: { ...day.activities[0].checkin!, planned_session_id: 99, revision: 2, note: "Feedback for workout 99" } };
      return route.fulfill({ status: 409, json: { detail: "Check-in changed" } });
    }
    const receipt = { ...initial(null), ...body, revision: 1 };
    day.sessions[0] = { ...day.sessions[0], checkin: receipt };
    return route.fulfill({ json: receipt });
  });
  await page.goto("/app/workouts/12");
  const note = page.getByLabel("Optional note", { exact: true });
  await note.fill("Feedback only for workout 12");
  await page.getByRole("button", { name: "Save check-in", exact: true }).click();
  await page.getByRole("button", { name: "Review the saved check-in", exact: true }).click();
  const review = page.getByRole("region", { name: "Review the saved check-in", exact: true });
  await expect(review).not.toContainText("Feedback for workout 99");
  await page.getByRole("button", { name: "Keep my edits", exact: true }).click();
  await expect(note).toHaveValue("Feedback only for workout 12");
  await page.getByRole("button", { name: "Save check-in", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toMatchObject({ planned_session_id: 12, expected_revision: 0, note: "Feedback only for workout 12" });
  expect(writes[1]).not.toHaveProperty("activity_id");
  expect(day.activities[0].checkin?.note).toBe("Feedback for workout 99");
});
