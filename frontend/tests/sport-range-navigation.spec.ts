import { expect, test, type Page } from '@playwright/test';
import { installApi } from './fixtures';

const missing = (key: string) => ({ key, value: null, unit: '', kind: 'calculated', availability: 'unavailable',
  unavailable_reason: 'missing_evidence', formula: 'Recorded source calculation', formula_version: 'test',
  source_dependencies: [], prerequisites: [], limitations: [] });
async function sportData(page: Page, sport: string) {
  await page.route(`**/athlete/sports/${sport}/overview**`, route => {
    const params = new URL(route.request().url()).searchParams;
    const range = { start: params.get('start'), end: params.get('end'), timezone: 'UTC' };
    const goal_context = { focus: null, goal_progress: missing('goal_progress') };
    if (sport === 'strength') return route.fulfill({ json: {
      sport, state: 'empty', range, goal_context,
      progression: { formula: 'Recorded sets', formula_version: 'test', history_complete: true, sessions: [], limitations: [] },
    } });
    return route.fulfill({ json: {
      sport, state: 'empty', version: 'test', range, goal_context, quality: { limitations: [] },
      totals: { activity_count: 0, distance_m: null, duration_s: null, elevation_gain_m: null, observed: {},
        formula: 'Recorded totals', formula_version: 'test', source_dependencies: [] },
      weekly: [], monthly: [], recent_activities: [], best_efforts: [], power_duration: [], long_run_progression: [],
      aerobic_trend: missing('aerobic_trend'), consistency: missing('consistency'), adherence: missing('adherence'),
      ftp: missing('confirmed_ftp'), body_mass: missing('body_mass'), advanced_metrics: [],
    } });
  });
}

for (const sport of ['running', 'cycling', 'strength']) {
  test(`${sport} preserves applied dates through activity navigation, Back and reload`, async ({ page }) => {
    const { writes } = await installApi(page);
    await sportData(page, sport);
    await page.goto(`/app/sports/${sport}`);
    const dates = page.locator('input[type="date"]');
    await dates.nth(0).fill('2026-01-01');
    await dates.nth(1).fill('2026-06-30');
    await page.getByRole('button', { name: 'Show this date range', exact: true }).click();
    await expect(page).toHaveURL(/start=2026-01-01&end=2026-06-30/);
    await expect(page.getByRole('status').filter({ hasText: 'Showing results for' })).toHaveText('Showing results for 2026-01-01 – 2026-06-30.');
    await page.locator('aside a[href="/app/activities"]').click();
    await expect(page).toHaveURL(/\/app\/activities$/);
    await page.goBack();
    await expect(dates.nth(0)).toHaveValue('2026-01-01');
    await expect(dates.nth(1)).toHaveValue('2026-06-30');
    await page.reload();
    await expect(dates.nth(0)).toHaveValue('2026-01-01');
    await expect(dates.nth(1)).toHaveValue('2026-06-30');
    if (sport === 'running') {
      await sportData(page, 'cycling');
      await page.locator('main nav a[href^="/app/sports/cycling"]').click();
      await expect(page).toHaveURL(/\/sports\/cycling\?start=2026-01-01&end=2026-06-30$/);
      await expect(dates.nth(0)).toHaveValue('2026-01-01');
      await expect(dates.nth(1)).toHaveValue('2026-06-30');
    }
    expect(writes).toEqual([]);
  });
}

test('invalid dates in sport links are explained before using the default range', async ({ page }) => {
  await installApi(page, { locale: 'it', theme: 'dark' });
  await page.setViewportSize({ width: 390, height: 844 });
  await sportData(page, 'strength');
  await page.goto('/app/sports/strength?start=2026-02-30&end=2026-03-15');
  await expect(page.getByRole('alert')).toContainText('Le date di questo collegamento non sono valide');
  await expect(page.locator('input[type="date"]').first()).not.toHaveValue('2026-02-30');
  await expect(page.getByRole('status').filter({ hasText: 'Risultati mostrati' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
