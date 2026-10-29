import { expect, test, type Page } from '@playwright/test';
import { installApi, overview, today } from './fixtures';

const total = (value: number | null, unit: string, count = 1) => ({ value, unit, available_sessions: value == null ? 0 : count, total_sessions: count });
const planned = (overrides = {}) => ({ id: 10, plan_id: 1, plan_revision: 3, plan_title: 'Autumn plan', discipline: 'running', start_time: '18:00', session_type: 'Easy run', duration_min: 40, distance_m: 6000, description: 'Full session prescription stays in details', status: 'planned', protected: true, workout_protected: true, plan_protected: false, activity_id: null, checkin: null, ...overrides });
const recorded = (id = 1, discipline = 'running', overrides = {}) => ({ id, discipline, start_time: today + 'T08:00:00Z', duration_s: 2400, distance_m: 6000, planned_session_id: null, association: 'unplanned', candidate_session_ids: [], checkin: null, comparison: null, ...overrides });
const day = (overrides = {}) => ({ date: today, timezone: 'UTC', training_focus: ['running', 'gym'], sessions: [], activities: [], legacy_gym_sessions: [], state: 'no_plan', totals: {}, sport_totals: {}, is_historical: false, ...overrides });
async function seedDay(page: Page, data: ReturnType<typeof day>) {
  await page.route('**/athlete/day**', route => route.fulfill({ json: data }));
}
async function openDay(page: Page, url = '/app') {
  await page.goto(url);
  await expect(page.getByTestId('daily-summary')).toBeVisible({ timeout: 15000 });
}
const daily = (page: Page) => page.locator('.panel').filter({ has: page.getByRole('heading', { name: 'Your day', exact: true }) });

for (const width of [1440, 390]) {
  test(`daily focus and supporting evidence retain load scope and respiration at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await installApi(page, { theme: 'dark' });
    await page.route('**/dashboard/overview*', route => route.fulfill({ json: { ...overview, load_metadata: { unit: 'Garmin load', source: 'garmin', acute_window_days: 7, chronic_window_days: 28 } } }));
    await page.route('**/metrics/respiration?**', route => route.fulfill({ json: { metric: 'respiration', unit: 'br/min', start_date: today, end_date: today, points: [{ date: today, value: 14.2 }], stats: { latest: 14.2 } } }));
    await seedDay(page, day({ activities: [recorded()], totals: { duration_s: total(2400, 's'), distance_m: total(6000, 'm'), calories: total(480, 'kcal') } }));
    const consoleErrors: string[] = [];
    page.on('pageerror', error => consoleErrors.push(error.message));
    await openDay(page);
    const scores = page.getByRole('region', { name: 'Daily readiness, recovery, strain and sleep' });
    for (const [key, value] of [['readiness', '82'], ['recovery', '78'], ['strain', '42'], ['provider_sleep_score', '84']]) {
      const card = scores.locator(`a[href="/app/biometrics/${key}"]`);
      await expect(card).toBeVisible();
      await expect(card.getByTestId('score-value')).toHaveText(`${value}/100`);
    }
    expect((await scores.boundingBox())!.height).toBeLessThan(330);
    const heroBox = (await page.getByTestId('today-hero').boundingBox())!;
    const evidenceBox = (await page.getByRole('complementary', { name: 'Daily evidence' }).boundingBox())!;
    if (width === 390) expect(heroBox.y + heroBox.height).toBeLessThan(evidenceBox.y);
    else {
      expect(heroBox.x + heroBox.width).toBeLessThan(evidenceBox.x);
      expect(heroBox.width / evidenceBox.width).toBeGreaterThan(1.8);
      expect(Math.abs(heroBox.y - evidenceBox.y)).toBeLessThan(2);
    }
    const primary = daily(page).getByTestId('daily-summary').getByRole('link');
    expect((await primary.boundingBox())!.y + (await primary.boundingBox())!.height).toBeLessThan(1000);
    await expect(page.locator('a[href="#training-load"]')).toContainText('7-day daily average');
    await expect(page.locator('a[href="#training-load"]')).toContainText('62.0 Garmin load');
    await expect(page.getByText(/Recorded load over the past 7 days/)).toHaveCount(0);
    await expect(page.getByTestId('overview-history')).not.toHaveAttribute('open', '');
    await page.locator('a[href="#training-load"]').click();
    await expect(page.getByTestId('overview-history')).toHaveAttribute('open', '');
    const load = page.locator('#training-load');
    await expect(load).toContainText('28-day daily average');
    await expect(load).toContainText('Garmin load');
    await expect(load.getByRole('button', { name: 'Long term · 28d' })).toBeVisible();
    const respiration = page.locator('a[href="/app/biometrics/respiration"]').locator('..');
    await expect(respiration).toContainText('14.2');
    await expect(respiration).toContainText('br/min');
    await expect(daily(page).getByRole('button', { name: 'Keep independent' })).not.toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(consoleErrors).toEqual([]);
    if (process.env.APEX_UI_SCREENSHOTS === '1') {
      await page.screenshot({ path: `/workspace/apex-cloud/beta-private/fixture-after-overview-${width}.png`, fullPage: true });
      await page.screenshot({ path: `/workspace/apex-cloud/beta-private/fixture-after-overview-viewport-${width}.png` });
    }
  });
}

test('missing scores remain visible with no fabricated zero even when all overview data is empty', async ({ page }) => {
  await installApi(page, { empty: true });
  await openDay(page);
  const scores = page.getByRole('region', { name: 'Daily readiness, recovery, strain and sleep' });
  await expect(scores.locator('a')).toHaveCount(4);
  await expect(scores.getByText('No score for this day', { exact: true })).toHaveCount(4);
  await expect(scores.getByTestId('score-value')).toHaveText(['—', '—', '—', '—']);
  await expect(page.getByTestId('overview-history')).not.toHaveAttribute('open', '');
  await page.locator('a[href="#training-load"]').click();
  await expect(page.locator('#training-load')).toBeVisible();
});

test('planned session has one primary action; protection and check-in remain in keyboard accessible details', async ({ page }) => {
  const { writes } = await installApi(page);
  await seedDay(page, day({ sessions: [planned()] }));
  await openDay(page);
  const panel = daily(page);
  const summary = panel.getByTestId('daily-summary');
  await expect(summary).toContainText('Planned');
  await expect(summary).toContainText('Easy run');
  await expect(summary).toContainText('40:00');
  await expect(summary.getByRole('link')).toHaveCount(1);
  await expect(summary.getByRole('link')).toHaveAttribute('href', '/app/workouts/10');
  await expect(panel.getByRole('button', { name: 'Remove workout protection', exact: true })).not.toBeVisible();
  const details = panel.getByTestId('daily-details');
  await details.locator('summary').first().focus();
  await details.locator('summary').first().press('Enter');
  await expect(details.getByText('Full session prescription stays in details', { exact: false })).toBeVisible();
  await expect(details.getByRole('button', { name: 'Remove workout protection', exact: true })).toBeVisible();
  await expect(details.getByText('Quick post-session check-in', { exact: true })).toBeVisible();
  expect(writes.filter(write => /protection|association|session-checkin/.test(write.path))).toEqual([]);
});

test('recorded activity leaves its unconfirmed planned session outstanding and association accessible', async ({ page }) => {
  await installApi(page);
  await seedDay(page, day({ activities: [recorded(1, 'running', { association: 'needs_confirmation', candidate_session_ids: [10] })], sessions: [planned()], totals: { duration_s: total(2400, 's'), distance_m: total(6000, 'm') } }));
  await openDay(page);
  const panel = daily(page);
  await expect(panel.getByTestId('daily-summary')).toContainText('In progress');
  await expect(panel.getByTestId('daily-summary')).toContainText('1 planned session remaining');
  await panel.getByTestId('daily-details').locator('summary').first().click();
  await expect(panel.getByRole('button', { name: 'Keep independent', exact: true })).toBeVisible();
  await expect(panel.getByRole('combobox')).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Confirm association', exact: true })).toBeDisabled();
  await panel.getByRole('combobox').selectOption('10');
  await expect(panel.getByRole('button', { name: 'Confirm association', exact: true })).toBeEnabled();
});

test('completed historical multisport summary never invents combined distance or edits a plan', async ({ page }) => {
  await installApi(page);
  const past = '2026-09-25';
  await seedDay(page, day({ date: past, is_historical: true, activities: [recorded(), recorded(2, 'road_cycling', { duration_s: 3600, distance_m: 40000 })], totals: { duration_s: total(6000, 's', 2) }, sport_totals: { running: { duration_s: total(2400, 's'), distance_m: total(6000, 'm') }, cycling: { duration_s: total(3600, 's'), distance_m: total(40000, 'm') } } }));
  await openDay(page, '/app?date=' + past);
  const summary = daily(page).getByTestId('daily-summary');
  await expect(summary).toContainText('Completed');
  await expect(summary).toContainText('2 activities recorded');
  await expect(summary).toContainText('History');
  await expect(summary).not.toContainText('46.0');
  await expect(summary.getByRole('list', { name: 'Session summary' }).getByRole('listitem')).toHaveCount(2);
  await daily(page).getByTestId('daily-details').locator('summary').first().click();
  const sports = daily(page).getByRole('region', { name: 'Recorded totals by sport' });
  await expect(sports).toContainText('6.0 km');
  await expect(sports).toContainText('40.0 km');
});

for (const historical of [false, true]) {
  test(`${historical ? 'historical empty day' : 'confirmed rest day'} does not invent planned training`, async ({ page }) => {
    await installApi(page, { empty: true });
    await seedDay(page, day({ is_historical: historical, planning_context: { state: historical ? 'no_profile' : 'active_rest_day', active_plan_id: historical ? null : 1 } }));
    await openDay(page);
    const summary = daily(page).getByTestId('daily-summary');
    await expect(summary).toContainText(historical ? 'No session scheduled' : 'Rest day');
    await expect(summary.getByRole('link')).toHaveCount(0);
    await expect(summary).not.toContainText('Completed');
  });
}

for (const [status, expected] of [['partial', 'In progress'], ['skipped', 'Skipped'], ['completed', 'Completed']] as const) {
  test(`self-reported ${status} retains its real status without recorded activity`, async ({ page }) => {
    await installApi(page);
    await seedDay(page, day({ sessions: [planned({ status })] }));
    await openDay(page);
    await expect(daily(page).getByTestId('daily-summary')).toContainText(expected);
    await expect(daily(page).getByTestId('daily-summary')).toContainText('Planned duration');
  });
}

test('Italian compact summary and missing score states are translated', async ({ page }) => {
  await installApi(page, { locale: 'it', empty: true });
  await seedDay(page, day({ sessions: [planned()] }));
  await openDay(page);
  await expect(page.getByTestId('daily-summary')).toContainText('Pianificato');
  await expect(page.getByTestId('daily-details').locator('summary').first()).toHaveText('Vedi dettagli');
  await expect(page.getByText('Nessun punteggio per questo giorno', { exact: true })).toHaveCount(4);
  await expect(page.locator('main')).not.toContainText('betaDaily.');
});

for (const [status, expected] of [['completed', 'Completed'], ['active', 'In progress']] as const) {
  test(`existing gym session ${status} is included in the day's real state`, async ({ page }) => {
    await installApi(page);
    await seedDay(page, day({ activities: status === 'active' ? [recorded()] : [], legacy_gym_sessions: [{ gym_day_plan_id: 8, title: 'Upper body', status }] }));
    await openDay(page);
    const summary = daily(page).getByTestId('daily-summary');
    await expect(summary).toContainText(expected);
    if (status === 'active') {
      await expect(summary).toContainText('1 planned session remaining');
      await expect(summary.getByRole('link')).toHaveAttribute('href', `/app/training?date=${today}#gym-session`);
    } else await expect(summary).toContainText('Upper body');
  });
}
