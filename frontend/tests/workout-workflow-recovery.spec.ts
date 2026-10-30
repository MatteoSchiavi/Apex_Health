import { expect, test, type Page } from '@playwright/test';
import { installApi, today } from './fixtures';
import type { StructuredWorkout } from '../src/features/athlete/StructuredWorkoutSteps';

const structure = (title = 'Easy run'): StructuredWorkout => ({
  title, objective: 'Comfortable consistency', steps: [{ id: 'easy', kind: 'easy', duration_s: 1800,
    distance_m: null, target: null, description: 'Keep the effort comfortable', exercise: null,
    sets: null, reps: null, load_kg: null, repetitions: 1, steps: [] }],
});
const receipt = (id = 8) => ({
  planned_session_id: id, plan_revision: 3, protected: false, editable: true, edit_block_reason: null,
  pending_draft: null as null | ReturnType<typeof draft>, history: [],
  workout: { id: 11, planned_session_id: id, revision: 2, payload_hash: 'a'.repeat(64), source: 'user_reviewed',
    duration_total_s: 1800, structure: structure(id === 8 ? 'Easy run' : 'Second workout') },
  session: { date: today, discipline: 'running', session_type: 'Easy run', duration_min: 30, description: 'Comfortable effort' },
  education: [],
});
const draft = (id = 21, title = 'Reviewed changes') => ({ id, planned_session_id: 8,
  plan_revision: 3, workout_revision: 2, payload_hash: 'b'.repeat(64), status: 'draft',
  duration_total_s: 1800, structure: structure(title) });

async function changeWorkoutRoute(page: Page, id: number) {
  // Exercise a client-side route change without unmounting the application.
  await page.evaluate(next => {
    history.pushState({ key: crypto.randomUUID() }, '', `/app/workouts/${next}`);
    dispatchEvent(new PopStateEvent('popstate'));
  }, id);
}

for (const locale of ['en', 'it'] as const) {
  for (const theme of ['light', 'dark'] as const) {
    test(`workout load recovery keeps navigation available (${locale}, ${theme})`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: theme === 'dark' ? 390 : 1280, height: 844 });
      await installApi(page, { empty: true, locale, theme });
      let failing = true;
      const writes: string[] = [];
      await page.route('**/athlete/planned-sessions/8/workout', route => route.fulfill(failing
        ? { status: 503, json: { detail: 'Temporary failure' } } : { json: receipt() }));
      page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/athlete/')) writes.push(request.url()); });
      await page.goto('/app/workouts/8');
      const reload = page.getByRole('button', { name: locale === 'en' ? 'Reload current workout' : 'Ricarica l’allenamento corrente', exact: true });
      await expect(reload).toBeEnabled();
      await expect(page.getByRole('link', { name: locale === 'en' ? 'Back to calendar' : 'Torna al calendario', exact: true })).toHaveAttribute('href', '/app/calendar');
      failing = false;
      await reload.click();
      await expect(page.getByRole('heading', { name: 'Easy run', exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: locale === 'en' ? 'Your day' : 'La tua giornata', exact: true }).first()).toHaveAttribute('href', `/app?date=${today}`);
      await expect(page.getByRole('button', { name: locale === 'en' ? 'Edit workout blocks' : 'Modifica i blocchi dell’allenamento', exact: true })).toBeVisible();
      expect(writes).toEqual([]);
      expect(await page.locator('main').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`workout-recovered-${locale}-${theme}.png`), fullPage: true });
    });
  }
}

test('failed conflict recovery preserves local changes and successful recovery restores the exact current review', async ({ page }) => {
  await installApi(page, { empty: true });
  let failing = false;
  let recoveryGate: Promise<void> | null = null;
  let currentDraft: ReturnType<typeof draft> | null = null;
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route('**/athlete/planned-sessions/8/workout', async route => {
    if (recoveryGate) await recoveryGate;
    return route.fulfill(failing ? { status: 503, json: { detail: 'Temporary failure' } }
      : { json: { ...receipt(), pending_draft: currentDraft } });
  });
  await page.route('**/athlete/planned-sessions/8/workout-drafts', route => {
    writes.push({ path: new URL(route.request().url()).pathname, body: route.request().postDataJSON() });
    return route.fulfill({ status: 409, json: { detail: 'Workout changed' } });
  });
  await page.route('**/athlete/workout-drafts/27/confirm', route => {
    writes.push({ path: new URL(route.request().url()).pathname, body: route.request().postDataJSON() });
    currentDraft = null;
    return route.fulfill({ json: receipt().workout });
  });
  await page.goto('/app/workouts/8');
  await page.getByRole('button', { name: 'Edit workout blocks', exact: true }).click();
  const objective = page.getByRole('textbox', { name: 'Workout objective', exact: true });
  await objective.fill('Keep these local instructions');
  const review = page.getByRole('button', { name: 'Review these workout changes', exact: true });
  await review.click();
  await expect(page.getByRole('alert').filter({ hasText: 'The plan or workout changed' })).toBeVisible();
  await expect(review).toBeDisabled();
  expect(writes[0].body).toMatchObject({ expected_plan_revision: 3, expected_workout_revision: 2,
    structure: { objective: 'Keep these local instructions' } });

  failing = true;
  let releaseFailure: () => void = () => {};
  recoveryGate = new Promise<void>(resolve => { releaseFailure = resolve; });
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Reload current workout', exact: true }).click();
  await expect(objective).toBeDisabled();
  releaseFailure(); recoveryGate = null;
  await expect(page.getByRole('alert').filter({ hasText: 'Could not refresh this workout' })).toBeVisible();
  await expect(objective).toHaveValue('Keep these local instructions');
  await expect(review).toBeDisabled();
  expect(writes).toHaveLength(1);

  // A failed fetch must not consume the discard confirmation or lose the
  // server's current pending draft when the athlete retries successfully.
  failing = false; currentDraft = draft(27, 'Current review from another device');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Reload current workout', exact: true }).click();
  await expect(objective).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Current review from another device', exact: true })).toBeVisible();
  const confirm = page.getByRole('button', { name: 'Confirm this reviewed workout', exact: true });
  await expect(confirm).toBeEnabled();
  expect(writes).toHaveLength(1);
  await confirm.click();
  await expect(page.getByText('Workout confirmed and saved. Your calendar now uses these instructions.', { exact: true })).toBeVisible();
  expect(writes[1]).toEqual({ path: '/athlete/workout-drafts/27/confirm', body: { payload_hash: 'b'.repeat(64) } });
});

test('a route change cannot carry a dirty editor into another planned session', async ({ page }) => {
  await installApi(page, { empty: true });
  const writes: Record<string, unknown>[] = [];
  for (const id of [8, 9]) {
    await page.route(`**/athlete/planned-sessions/${id}/workout`, route => route.fulfill({ json: receipt(id) }));
  }
  await page.route('**/athlete/planned-sessions/9/workout-drafts', route => {
    const body = route.request().postDataJSON(); writes.push(body);
    return route.fulfill({ json: { ...draft(22), planned_session_id: 9, structure: body.structure } });
  });
  await page.goto('/app/workouts/8');
  await page.getByRole('button', { name: 'Edit workout blocks', exact: true }).click();
  await page.getByRole('textbox', { name: 'Workout objective', exact: true }).fill('Private first-session edits');
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('link', { name: 'Your day', exact: true }).first().click();
  await expect(page).toHaveURL(/\/app\/workouts\/8$/);
  await expect(page.getByRole('textbox', { name: 'Workout objective', exact: true })).toHaveValue('Private first-session edits');

  await changeWorkoutRoute(page, 9);
  await expect(page.getByRole('heading', { name: 'Second workout', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Workout objective', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Confirm this reviewed workout', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit workout blocks', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Workout objective', exact: true })).toHaveValue('Comfortable consistency');
  await page.getByRole('button', { name: 'Review these workout changes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Confirm this reviewed workout', exact: true })).toBeEnabled();
  expect(writes).toHaveLength(1);
  expect(JSON.stringify(writes)).not.toContain('Private first-session edits');
});

test('a late draft response stays attached to the workout that requested it', async ({ page }) => {
  await installApi(page, { empty: true });
  let release: () => void = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  const writes: string[] = [];
  for (const id of [8, 9]) {
    await page.route(`**/athlete/planned-sessions/${id}/workout`, route => route.fulfill({ json: receipt(id) }));
  }
  await page.route('**/athlete/planned-sessions/8/workout-drafts', async route => {
    writes.push(new URL(route.request().url()).pathname);
    await gate;
    await route.fulfill({ json: draft(21, 'First session pending review') });
  });
  await page.goto('/app/workouts/8');
  await page.getByRole('button', { name: 'Edit workout blocks', exact: true }).click();
  await page.getByRole('button', { name: 'Review these workout changes', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await changeWorkoutRoute(page, 9);
  await expect(page.getByRole('heading', { name: 'Second workout', exact: true })).toBeVisible();
  const finished = page.waitForResponse(response => response.url().endsWith('/planned-sessions/8/workout-drafts'));
  release(); await finished;
  await expect(page.getByRole('heading', { name: 'Second workout', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm this reviewed workout', exact: true })).toHaveCount(0);
  await expect(page.getByText('First session pending review', { exact: true })).toHaveCount(0);
  expect(writes).toEqual(['/athlete/planned-sessions/8/workout-drafts']);
});
