import { expect, test, type Page } from '@playwright/test';
import { installApi, overview, today } from './fixtures';

const plannedDay = {
  date: today, timezone: 'UTC', training_focus: ['running'], sessions: [{
    id: 10, plan_id: 1, plan_revision: 3, plan_title: 'Autumn plan', discipline: 'running',
    start_time: '18:00', session_type: 'Easy run', duration_min: 40, distance_m: 6000,
    description: null, status: 'planned', protected: false, workout_protected: false,
    plan_protected: false, activity_id: null, checkin: null,
  }], activities: [], legacy_gym_sessions: [], state: 'planned', totals: {}, sport_totals: {}, is_historical: false,
};

async function editDayFeedback(page: Page, note: string) {
  await page.getByTestId('daily-details').locator('summary').first().click();
  await page.getByText('Quick post-session check-in', { exact: true }).click();
  await page.getByLabel('Optional note', { exact: true }).fill(note);
}

const overviewResponse = (page: Page, status: number) => page.waitForResponse(response =>
  new URL(response.url()).pathname === '/dashboard/overview' && response.status() === status,
);

test('initial overview failure keeps the actual day action usable and retry preserves day feedback', async ({ page }) => {
  const { writes } = await installApi(page);
  let failOverview = true;
  await page.route('**/athlete/day**', route => route.fulfill({ json: plannedDay }));
  await page.route('**/dashboard/overview*', route => failOverview
    ? route.fulfill({ status: 503, json: { detail: 'Temporary health data failure' } })
    : route.fulfill({ json: overview }));
  await page.goto('/app');
  const summary = page.getByTestId('daily-summary');
  await expect(summary).toContainText('Easy run');
  await expect(summary.getByRole('link')).toHaveAttribute('href', '/app/workouts/10');
  const healthError = page.getByTestId('overview-health-error');
  await expect(healthError).toContainText('Health data is unavailable. Your day is still available.');
  await expect(page.getByTestId('score-value')).toHaveCount(0);
  await expect(page.getByTestId('overview-health-empty')).toHaveCount(0);
  await editDayFeedback(page, 'Keep my edits while health values load');
  expect(writes.filter(write => write.path === '/athlete/checkins')).toEqual([]);
  failOverview = false;
  const retried = overviewResponse(page, 200);
  await healthError.getByRole('button', { name: 'Retry', exact: true }).click();
  await retried;
  await expect(healthError).toHaveCount(0);
  await expect(page.getByTestId('score-value').first()).toHaveText('82/100');
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('Keep my edits while health values load');
  await expect(page.getByRole('button', { name: 'Save check-in', exact: true })).toBeEnabled();
  expect(writes.filter(write => write.path === '/athlete/checkins')).toEqual([]);
});

test('background overview failure retains last health values and dirty feedback through retry without saving', async ({ page }) => {
  const { writes } = await installApi(page);
  await page.clock.install();
  let failOverview = false;
  await page.route('**/athlete/day**', route => route.fulfill({ json: plannedDay }));
  await page.route('**/dashboard/overview*', route => failOverview
    ? route.fulfill({ status: 503, json: { detail: 'Temporary health refresh failure' } })
    : route.fulfill({ json: overview }));
  await page.goto('/app');
  await expect(page.getByTestId('score-value').first()).toHaveText('82/100');
  await editDayFeedback(page, 'Keep these observations until I choose to save');
  failOverview = true;
  const failedRefresh = overviewResponse(page, 503);
  await page.clock.fastForward(300_001);
  await failedRefresh;
  const failedRetry = overviewResponse(page, 503);
  await page.clock.runFor(2_000);
  await failedRetry;
  await page.clock.runFor(1);
  const healthError = page.getByTestId('overview-health-error');
  await expect(healthError).toContainText('Health data could not be refreshed. Showing the last loaded values.');
  await expect(page.getByTestId('overview-health-empty')).toHaveCount(0);
  await expect(page.getByTestId('score-value').first()).toHaveText('82/100');
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('Keep these observations until I choose to save');
  expect(writes.filter(write => write.path === '/athlete/checkins')).toEqual([]);
  failOverview = false;
  const retried = overviewResponse(page, 200);
  await healthError.getByRole('button', { name: 'Retry', exact: true }).click();
  await retried;
  await expect(healthError).toHaveCount(0);
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('Keep these observations until I choose to save');
  await expect(page.getByRole('button', { name: 'Save check-in', exact: true })).toBeEnabled();
  expect(writes.filter(write => write.path === '/athlete/checkins')).toEqual([]);
});
