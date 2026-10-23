import { expect, test, type Page } from '@playwright/test';
import { installApi, today } from './fixtures';

const exercise = (id: number, sets: number, reps: number) => ({
  gym_day_exercise_id: id, exercise_id: id, name: id === 7 ? 'Bench press' : 'Bodyweight squat',
  muscle_group: id === 7 ? 'push' : 'legs', movement_pattern: 'test', position: id,
  sets, reps_min: reps, reps_max: reps, rest_seconds: 60, notes: null, sets_done: 0, complete: false,
});
const planFor = (date: string, status = 'confirmed') => ({ plan_id: 15, revision: 1, date,
  title: 'Full strength session', status, source: 'template', adjustment_note: null,
  exercises: [exercise(7, 2, 8), exercise(8, 1, 12)], progress: { sets_done: 0, sets_total: 3, complete: false },
});
const dayFor = (date: string, gymStatus?: string) => ({ date, timezone: 'UTC', training_focus: ['gym'],
  is_historical: date < today, sessions: [], activities: [], legacy_gym_sessions: gymStatus
    ? [{ gym_day_plan_id: 15, title: 'Full strength session', status: gymStatus }] : [], totals: {}, sport_totals: {}, state: 'no_plan',
});
const gym = (page: Page) => page.locator('#gym-session');

test('generate, confirm and finish refresh Your day; saved sets wait for refreshed progress and reset weight for a new exercise', async ({ page }) => {
  await installApi(page, { empty: true });
  let plan: ReturnType<typeof planFor> | null = null;
  let dayReads = 0;
  let releaseRead: (() => void) | undefined;
  let readGate: Promise<void> | undefined;
  const logs: any[] = [];
  await page.route(url => url.pathname === '/athlete/day', route => {
    dayReads++;
    return route.fulfill({ json: dayFor(today, plan?.status === 'draft' ? undefined : plan?.status === 'done' ? 'completed' : plan?.status) });
  });
  await page.route(url => url.pathname === `/gym/plan/${today}`, async route => {
    if (readGate) await readGate;
    await route.fulfill({ json: { date: today, plan, template: null } });
  });
  await page.route(url => url.pathname === `/gym/plan/${today}/generate`, route => {
    plan = planFor(today, 'draft');
    return route.fulfill({ json: plan });
  });
  await page.route(url => url.pathname === `/gym/plan/${today}/confirm`, route => {
    expect(route.request().postDataJSON()).toEqual({ expected_revision: 1 });
    plan!.status = 'confirmed';
    return route.fulfill({ json: { status: 'confirmed' } });
  });
  await page.route('**/gym/session/15/log', async route => {
    const payload = route.request().postDataJSON(); logs.push(payload);
    const row = plan!.exercises.find(row => row.gym_day_exercise_id === payload.gym_day_exercise_id)!;
    row.sets_done++; row.complete = row.sets_done === row.sets;
    plan!.progress.sets_done++;
    plan!.progress.complete = plan!.progress.sets_done === 3;
    plan!.status = plan!.progress.complete ? 'done' : 'active';
    if (logs.length === 1) readGate = new Promise<void>(resolve => { releaseRead = resolve; });
    await route.fulfill({ json: { rest_seconds: logs.length === 1 ? null : 60, next: { done: plan!.progress.complete } } });
  });
  await page.goto('/app/training');
  await expect(page.getByTestId('daily-summary')).toBeVisible();
  const initialReads = dayReads;
  await gym(page).getByRole('button', { name: 'Generate plan', exact: true }).click();
  await expect(gym(page).getByRole('button', { name: 'Confirm plan', exact: true })).toBeEnabled();
  await expect.poll(() => dayReads).toBeGreaterThan(initialReads);
  const generatedReads = dayReads;
  await gym(page).getByRole('button', { name: 'Confirm plan', exact: true }).click();
  await expect(page.getByTestId('daily-summary')).toContainText('Planned');
  await expect.poll(() => dayReads).toBeGreaterThan(generatedReads);
  const reps = gym(page).getByRole('spinbutton', { name: 'Reps', exact: true });
  const weight = gym(page).getByRole('spinbutton', { name: 'Weight (kg)', exact: true });
  await expect(reps).toHaveValue('8');
  await weight.fill('40');
  await reps.press('Enter');
  await expect(gym(page).getByRole('button', { name: 'Saving set…', exact: true })).toBeDisabled();
  await expect(reps).toBeDisabled();
  expect(logs).toHaveLength(1);
  releaseRead!(); readGate = undefined;
  await expect(gym(page).getByRole('button', { name: 'Log set', exact: true })).toBeEnabled();
  await expect(page.getByTestId('daily-summary')).toContainText('In progress');
  await expect(gym(page).getByRole('timer')).toHaveCount(0);
  await expect(reps).toHaveValue('8');
  await expect(weight).toHaveValue('40');
  await gym(page).getByRole('button', { name: 'Log set', exact: true }).click();
  await expect(reps).toHaveValue('12');
  await expect(weight).toHaveValue('');
  await expect(gym(page).getByRole('timer')).toBeVisible();
  await gym(page).getByRole('button', { name: 'Skip rest', exact: true }).click();
  await expect(gym(page).getByRole('timer')).toHaveCount(0);
  await gym(page).getByRole('button', { name: 'Log set', exact: true }).click();
  await expect(gym(page).getByRole('status')).toContainText('Workout complete');
  await expect(page.getByTestId('daily-summary')).toContainText('Completed');
  await expect(gym(page).getByRole('button', { name: 'Log set', exact: true })).toHaveCount(0);
  expect(logs).toEqual([
    { gym_day_exercise_id: 7, set_number: 1, reps_done: 8, weight_kg: 40 },
    { gym_day_exercise_id: 7, set_number: 2, reps_done: 8, weight_kg: 40 },
    { gym_day_exercise_id: 8, set_number: 1, reps_done: 12, weight_kg: null },
  ]);
});

test('historical gym links retain the selected date and offer no generate, confirm, logging or feedback writes', async ({ page }) => {
  const { writes } = await installApi(page, { empty: true });
  const past = '2024-03-05';
  const reads: string[] = [];
  await page.route(url => url.pathname === '/athlete/day', route => route.fulfill({ json: dayFor(past, 'confirmed') }));
  await page.route(url => /^\/gym\/plan\/\d{4}-\d{2}-\d{2}$/.test(url.pathname), route => {
    const date = new URL(route.request().url()).pathname.split('/').pop()!; reads.push(date);
    return route.fulfill({ json: { date, plan: planFor(date), template: null } });
  });
  await page.goto(`/app?date=${past}`);
  const link = page.getByTestId('daily-summary').getByRole('link');
  await expect(link).toHaveAttribute('href', `/app/training?date=${past}#gym-session`);
  await link.click();
  await expect(page.getByLabel('Training date', { exact: true })).toHaveValue(past);
  await expect(gym(page)).toContainText('You are viewing another day');
  await expect(gym(page).getByRole('table')).toBeVisible();
  await expect(gym(page).getByRole('button')).toHaveCount(0);
  await expect(gym(page).getByRole('spinbutton')).toHaveCount(0);
  await expect(gym(page).getByRole('textbox')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Upcoming events', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`date=${past}.*tab=calendar`));
  await page.getByRole('tab', { name: 'Selected day', exact: true }).click();
  await expect(page.getByLabel('Training date', { exact: true })).toHaveValue(past);
  expect(reads.every(date => date === past)).toBe(true);
  expect(writes).toHaveLength(0);
});

test('rest countdown uses elapsed time and does not restart after a suspended browser resumes', async ({ page }) => {
  await installApi(page);
  await page.clock.install();
  const plan = planFor(today);
  await page.route(url => url.pathname === `/gym/plan/${today}`, route => route.fulfill({ json: { date: today, plan, template: null } }));
  await page.route('**/gym/session/15/log', route => {
    plan.exercises[0].sets_done = 1; plan.progress.sets_done = 1;
    return route.fulfill({ json: { rest_seconds: 60, next: { done: false } } });
  });
  await page.goto('/app/training');
  await gym(page).getByRole('button', { name: 'Log set', exact: true }).click();
  await expect(gym(page).getByRole('timer')).toHaveText('1:00');
  await page.clock.fastForward(45_000);
  await expect(gym(page).getByRole('timer')).toHaveText('0:15');
  await page.clock.fastForward(20_000);
  await expect(gym(page).getByRole('timer')).toHaveCount(0);
});

test('a timed hold uses seconds through logging and completion without inventing repetitions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installApi(page, { empty: true });
  const plan = { ...planFor(today), exercises: [{ ...exercise(9, 1, 30), name: 'Plank', reps_min: null,
    reps_max: null, duration_min_s: 30, duration_max_s: 60 }], progress: { sets_done: 0, sets_total: 1, complete: false } };
  await page.route(url => url.pathname === `/gym/plan/${today}`, route => route.fulfill({ json: { date: today, plan, template: null } }));
  let saved: unknown;
  await page.route('**/gym/session/15/log', route => {
    saved = route.request().postDataJSON();
    plan.exercises[0].sets_done = 1; plan.exercises[0].complete = true;
    plan.progress = { sets_done: 1, sets_total: 1, complete: true }; plan.status = 'done';
    return route.fulfill({ json: { rest_seconds: null, next: { done: true } } });
  });
  await page.goto('/app/training');
  const seconds = gym(page).getByRole('spinbutton', { name: 'Duration (seconds)', exact: true });
  await expect(seconds).toHaveValue('30');
  await expect(gym(page)).toContainText('30–60 s');
  await expect(page.getByTestId('gym-exercise-list')).toContainText('30–60 s');
  await expect(page.getByTestId('gym-exercise-list')).toContainText('60s');
  expect(await page.getByTestId('gym-exercise-list').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await seconds.fill('45');
  await gym(page).getByRole('button', { name: 'Log set', exact: true }).click();
  await expect(gym(page).getByRole('status')).toContainText('Workout complete');
  expect(saved).toEqual({ gym_day_exercise_id: 9, set_number: 1, duration_s: 45, weight_kg: null });
});

test('a resumed legacy workout fills the missing set instead of submitting an already saved number', async ({ page }) => {
  await installApi(page, { empty: true });
  const plan = { ...planFor(today, 'active'), exercises: [{ ...exercise(7, 2, 8), sets_done: 1, next_set_number: 1 as number | null }],
    progress: { sets_done: 1, sets_total: 2, complete: false } };
  await page.route(url => url.pathname === `/gym/plan/${today}`, route => route.fulfill({ json: { date: today, plan, template: null } }));
  const logs: unknown[] = [];
  await page.route('**/gym/session/15/log', route => {
    const body = route.request().postDataJSON(); logs.push(body);
    if (body.set_number !== 1) return route.fulfill({ status: 409, json: { detail: 'Set 2 is already saved' } });
    plan.exercises[0] = { ...plan.exercises[0], sets_done: 2, complete: true, next_set_number: null };
    plan.progress = { sets_done: 2, sets_total: 2, complete: true }; plan.status = 'done';
    return route.fulfill({ json: { rest_seconds: null, next: { done: true } } });
  });
  await page.goto('/app/training');
  await gym(page).getByRole('button', { name: 'Log set', exact: true }).click();
  await expect(gym(page).getByRole('status')).toContainText('Workout complete');
  await expect(gym(page).getByRole('button', { name: 'Log set', exact: true })).toHaveCount(0);
  expect(logs).toEqual([{ gym_day_exercise_id: 7, set_number: 1, reps_done: 8, weight_kg: null }]);
});
