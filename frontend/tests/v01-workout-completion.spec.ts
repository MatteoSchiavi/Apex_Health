import { test, expect, type Page } from '@playwright/test';
import { installApi, today } from './fixtures';
import type { AthleteDay, Checkin } from '../src/features/athlete/types';

function session(id = 8, activityId: number | null = null) {
  return { id, plan_id: 3, plan_revision: 1, plan_title: 'Training week', discipline: 'running',
    start_time: '08:00', session_type: 'Easy run', duration_min: 30, distance_m: null,
    description: 'Comfortable effort', protected: false, plan_protected: false,
    workout_protected: false, status: 'planned', activity_id: activityId, checkin: null as Checkin | null };
}

async function setup(page: Page, options: { date?: string; activityId?: number; mismatch?: 'date' | 'session' | 'receipt' } = {}) {
  await installApi(page, { empty: true });
  const date = options.date ?? today;
  const scheduled = session(options.mismatch === 'session' ? 99 : 8, options.activityId ?? null);
  const day: AthleteDay = { date: options.mismatch === 'date' ? '2000-01-01' : date,
    timezone: 'UTC', training_focus: ['running'], sessions: [scheduled],
    legacy_gym_sessions: [], state: 'planned', totals: {}, activities: [] };
  if (options.activityId) day.activities.push({ id: options.activityId, discipline: 'running',
    start_time: `${date}T08:00:00Z`, duration_s: 1800, distance_m: 4000,
    planned_session_id: 8, association: 'confirmed', candidate_session_ids: [], comparison: null, checkin: null });
  if (options.mismatch === 'receipt') scheduled.checkin = { id: 15, revision: 1,
    planned_session_id: 99, activity_id: null, status: 'completed', note: 'Another session',
    rpe: null, pain: null, felt_unwell: null };
  const dayDates: (string | null)[] = [];
  let workoutReads = 0;
  await page.route('**/athlete/day?*', route => {
    dayDates.push(new URL(route.request().url()).searchParams.get('date'));
    return route.fulfill({ json: day });
  });
  await page.route('**/athlete/planned-sessions/8/workout', route => {
    workoutReads++;
    const completed = !!scheduled.checkin;
    return route.fulfill({ json: { planned_session_id: 8, plan_revision: 1, protected: false,
      editable: !completed && !options.activityId, edit_block_reason: completed ? 'completed_or_skipped' : options.activityId ? 'recorded' : null,
      workout: null, session: { date, discipline: 'running', session_type: 'Easy run', duration_min: 30, description: 'Comfortable effort' }, education: [] } });
  });
  const writes: Record<string, unknown>[] = [];
  await page.route('**/athlete/checkins', route => {
    const body = route.request().postDataJSON();
    writes.push(body);
    const receipt = { ...body, activity_id: options.activityId ?? null, planned_session_id: 8,
      id: 15, revision: (scheduled.checkin?.revision ?? 0) + 1 } as Checkin;
    scheduled.checkin = receipt; scheduled.status = receipt.status;
    if (day.activities[0]) day.activities[0].checkin = receipt;
    return route.fulfill({ json: receipt });
  });
  return { writes, dayDates, workoutReads: () => workoutReads };
}

const completion = (page: Page) => page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Record this workout', exact: true }) });

test('the workout destination records completion, refreshes editability and retains feedback after reload', async ({ page }) => {
  const state = await setup(page);
  await page.goto('/app/workouts/8');
  const panel = completion(page);
  await expect(page.getByText('Comfortable effort', { exact: true })).toBeVisible();
  await expect(panel.getByLabel('Perceived fatigue', {exact:true})).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit workout blocks', exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Save check-in', exact: true })).toBeVisible();
  await panel.getByLabel('Optional note', { exact: true }).fill('Comfortable all the way');
  await panel.getByLabel('Perceived effort (RPE 0–10, optional)', { exact: true }).fill('4');
  await panel.getByRole('button', { name: 'Save check-in', exact: true }).click();
  await expect(panel.getByText('Completed', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Edit workout blocks', exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0]).toMatchObject({ planned_session_id: 8, expected_revision: 0, status: 'completed', rpe: 4, note: 'Comfortable all the way' });
  expect(state.writes[0].activity_id).toBeUndefined();
  expect(state.workoutReads()).toBeGreaterThan(1);
  await page.reload();
  await expect(panel.getByLabel('Optional note', { exact: true })).toHaveValue('Comfortable all the way');
  await expect(panel.getByRole('button', { name: 'Save check-in', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Edit workout blocks', exact: true })).toHaveCount(0);
  expect(state.dayDates.every(date => date === today)).toBe(true);
});

test('historical workout feedback uses its date and associated recorded activity', async ({ page }) => {
  const state = await setup(page, { date: '2026-09-18', activityId: 44 });
  await page.goto('/app/workouts/8');
  const panel = completion(page);
  await expect(panel.getByRole('link', { name: /View recorded activity/ })).toHaveAttribute('href', '/app/activities/44');
  const result = panel.getByRole('combobox', { name: 'How much did you complete?', exact: true });
  await expect(result.locator('option[value="skipped"]')).toHaveCount(0);
  await result.selectOption('partial');
  await panel.getByLabel('Optional note', { exact: true }).fill('Stopped early');
  await panel.getByRole('button', { name: 'Save check-in', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Save check-in', exact: true })).toBeDisabled();
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0]).toMatchObject({ planned_session_id: 8, status: 'partial', note: 'Stopped early' });
  expect(state.writes[0]).not.toHaveProperty('activity_id');
  expect(state.dayDates.every(date => date === '2026-09-18')).toBe(true);
  await page.reload();
  await expect(result).toHaveValue('partial');
  await expect(panel.getByLabel('Optional note', { exact: true })).toHaveValue('Stopped early');
});

for (const mismatch of ['date', 'session', 'receipt'] as const) {
  test(`completion never uses a mismatched ${mismatch}`, async ({ page }) => {
    const state = await setup(page, { mismatch });
    await page.goto('/app/workouts/8');
    const panel = completion(page);
    await expect(panel.getByText('Completion details are unavailable for this workout. Open its day or try again.', { exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name: 'Save check-in', exact: true })).toHaveCount(0);
    await expect(panel.getByRole('link', { name: 'Your day', exact: true })).toHaveAttribute('href', `/app?date=${today}`);
    expect(state.writes).toHaveLength(0);
  });
}
