import { expect, test } from '@playwright/test';
import { activity, installApi, overview, today } from './fixtures';

const recorded = { ...activity, id: 31, discipline: 'running', duration_s: 2400, distance_m: 6000, planned_session_id: null, association: 'independent', candidate_session_ids: [], checkin: null, comparison: null };
const day = (overrides = {}) => ({ date: today, timezone: 'UTC', training_focus: ['running', 'gym'], sessions: [], activities: [], legacy_gym_sessions: [], state: 'no_plan', totals: {}, sport_totals: {}, is_historical: false, planning_context: { state: 'profile_ready', profile_state: 'ready' }, ...overrides });

for (const width of [1440, 390]) for (const [locale, theme] of [['en', 'dark'], ['it', 'light']] as const) {
  test(`Today focuses the next planned session beside supporting evidence at ${width}px ${locale} ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const { writes } = await installApi(page, { locale, theme });
    let dayReads = 0;
    await page.route('**/athlete/day**', route => {
      dayReads++;
      return route.fulfill({ json: day({
        activities: [recorded],
        sessions: [{ id: 10, plan_id: 1, plan_revision: 3, plan_title: 'Autumn plan', discipline: 'strength', start_time: '18:00', session_type: 'Evening strength', duration_min: 55, distance_m: null, status: 'planned', protected: true, workout_protected: true, plan_protected: false, activity_id: null, checkin: null }],
        totals: { duration_s: { value: 2400, unit: 's', available_sessions: 1, total_sessions: 1 } },
      }) });
    });
    await page.route('**/dashboard/overview*', route => route.fulfill({ json: { ...overview, recent_activities: [1, 2, 3, 4].map(id => ({ ...activity, id })) } }));
    await page.goto('/app');
    const summary = page.getByTestId('daily-summary');
    await expect(summary).toContainText('Evening strength');
    await expect(summary).toContainText('55:00');
    await expect(summary.getByRole('link')).toHaveAttribute('href', '/app/workouts/10');
    const primary = (await summary.getByRole('link').boundingBox())!;
    expect(primary.y + primary.height).toBeLessThan(844);
    const hero = (await page.getByTestId('today-hero').boundingBox())!;
    const evidence = (await page.getByRole('complementary', { name: locale === 'en' ? 'Daily evidence' : 'Dati del giorno' }).boundingBox())!;
    if (width === 390) expect(hero.y + hero.height).toBeLessThan(evidence.y);
    else {
      expect(hero.x + hero.width).toBeLessThan(evidence.x);
      expect(hero.width / evidence.width).toBeGreaterThan(1.8);
    }
    await expect(page.getByTestId('overview-history')).not.toHaveAttribute('open', '');
    await expect(page.locator('#training-load')).toHaveCount(0);
    await expect(page.getByTestId('today-recent-context').locator('a[href^="/app/activities/"]')).toHaveCount(3);
    await expect(page.getByTestId('overview-setup').locator('summary')).toContainText(locale === 'en' ? /\d of 3 complete/ : /\d di 3 completati/);
    expect(dayReads).toBe(1);
    expect(writes.filter(write => /protection|association|checkin|\/lab\//.test(write.path))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator('main')).not.toContainText('redesign.overview.');
    await page.screenshot({ path: testInfo.outputPath(`today-${locale}-${theme}-${width}-full.png`), fullPage: true });
    await page.screenshot({ path: testInfo.outputPath(`today-${locale}-${theme}-${width}-viewport.png`) });
  });
}

test('a completed single activity offers its missing feedback as the primary action', async ({ page }) => {
  const { writes } = await installApi(page);
  await page.route('**/athlete/day**', route => route.fulfill({ json: day({ activities: [recorded] }) }));
  await page.goto('/app');
  const summary = page.getByTestId('daily-summary');
  await expect(summary).toContainText('Completed');
  await expect(summary.getByRole('link')).toHaveAttribute('href', '/app/activities/31?feedback=1#session-feedback');
  await expect(summary.getByRole('link')).toContainText('Add feedback');
  await expect(page.locator('a[href="/app/activities/31?feedback=1#session-feedback"]')).toHaveCount(1);
  expect(writes.filter(write => /checkin/.test(write.path))).toEqual([]);
});

test('load shortcut opens history and mounts a correctly sized chart on the selected snapshot', async ({ page }) => {
  await installApi(page);
  const requests: URL[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname === '/metrics/acute_load') requests.push(url);
  });
  await page.goto(`/app?date=${today}`);
  await expect(page.getByTestId('daily-summary')).toBeVisible();
  expect(requests).toHaveLength(0);
  await page.locator('a[href="#training-load"]').click();
  await expect(page.getByTestId('overview-history')).toHaveAttribute('open', '');
  const load = page.locator('#training-load');
  await expect(load).toBeInViewport();
  await expect(load.locator('canvas')).toBeVisible();
  expect((await load.locator('canvas').boundingBox())!.width).toBeGreaterThan(200);
  expect(requests.some(url => url.searchParams.get('days') === '28' && url.searchParams.get('end') === today)).toBe(true);
});

test('setup stays in a compact strip and its steps and dismissal are keyboard accessible', async ({ page }) => {
  await installApi(page, { empty: true });
  await page.goto('/app');
  const setup = page.getByTestId('overview-setup');
  await expect(setup).not.toHaveAttribute('open', '');
  await expect(setup.locator('summary')).toContainText('0 of 3 complete');
  await expect(setup.getByRole('link')).toHaveCount(0); // Hidden links are excluded from the accessible tree.
  await setup.locator('summary').focus();
  await setup.locator('summary').press('Enter');
  await expect(setup.getByRole('link')).toHaveCount(3);
  await setup.getByRole('button', { name: 'Dismiss setup checklist' }).click();
  await expect(setup).toHaveCount(0);
  await page.reload();
  await expect(setup).toHaveCount(0);
});
