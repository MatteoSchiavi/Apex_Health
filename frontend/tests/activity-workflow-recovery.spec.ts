import { expect, test, type Page } from '@playwright/test';
import { activity, installApi, today } from './fixtures';

// These synthetic scenarios exercise the shipped UI, not a real account.
async function recordedDay(page: Page) {
  await page.route('**/athlete/day**', route => route.fulfill({ json: {
    date: today, timezone: 'UTC', training_focus: ['cycling'], sessions: [],
    activities: [{ ...activity, planned_session_id: null, association: 'independent', candidate_session_ids: [], checkin: null }],
    legacy_gym_sessions: [], state: 'activity_recorded', totals: {}, sport_totals: {}, is_historical: false,
  } }));
  await page.route('**/activities/1/comparison-context', route => route.fulfill({ json: {
    activity_id: 1, revision: 'a'.repeat(64), providers: ['garmin'], assertions: [],
    recorded_context_providers: [], outdoor_weather_available: false,
  } }));
}

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  const note = en ? 'Optional note' : 'Nota facoltativa';
  const routeName = en ? 'Route identity' : 'Identità del percorso';
  const retry = en ? 'Retry' : 'Riprova';

  test(`activity tabs retain unfinished feedback and comparison edits (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: en ? 'dark' : 'light' });
    await page.setViewportSize({ width: en ? 1440 : 390, height: 844 });
    await recordedDay(page);
    await page.goto('/app/activities/1?feedback=1#session-feedback');
    await page.getByLabel(note, { exact: true }).fill('Keep this feedback while I inspect my laps');
    await page.getByLabel(routeName, { exact: true }).fill('Unsaved route identity');
    await page.getByRole('tab', { name: en ? 'Laps' : 'Giri', exact: true }).click();
    await expect(page.getByLabel(note, { exact: true })).toBeHidden();
    await expect(page.getByLabel(routeName, { exact: true })).toBeHidden();
    await page.getByRole('tab', { name: en ? 'Sources' : 'Fonti', exact: true }).click();
    await page.getByRole('tab', { name: en ? 'Session' : 'Sessione', exact: true }).click();
    await expect(page.getByLabel(note, { exact: true })).toHaveValue('Keep this feedback while I inspect my laps');
    await expect(page.getByLabel(routeName, { exact: true })).toHaveValue('Unsaved route identity');
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`activity load failure offers an explicit retry and return to the activity log (${locale})`, async ({ page }) => {
    await installApi(page, { locale, theme: en ? 'light' : 'dark' });
    await page.setViewportSize({ width: en ? 390 : 1440, height: 844 });
    let fails = true;
    await page.route(url => url.pathname === '/activities/1', route => fails
      ? route.fulfill({ status: 503, json: { detail: 'Temporary activity failure' } })
      : route.fulfill({ json: activity }));
    await page.goto('/app/activities/1');
    await expect(page.getByRole('button', { name: retry, exact: true })).toBeVisible();
    await expect(page.locator('main a[href="/app/activities"]')).toBeVisible();
    fails = false;
    await page.getByRole('button', { name: retry, exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(en ? 'Road Cycling' : 'Ciclismo su strada');
    await expect(page.getByTestId('activity-session-panel')).toBeVisible();
  });
}

test('failed activity refresh and retry keep the same feedback form and comparison edits', async ({ page }) => {
  const { writes } = await installApi(page);
  await page.clock.install();
  await recordedDay(page);
  let fails = false;
  await page.route(url => url.pathname === '/activities/1', route => fails
    ? route.fulfill({ status: 503, json: { detail: 'Temporary activity refresh failure' } })
    : route.fulfill({ json: { ...activity, has_streams: false } }));
  await page.goto('/app/activities/1?feedback=1#session-feedback');
  await page.getByLabel('Optional note', { exact: true }).fill('My unfinished feedback');
  await page.getByLabel('Route identity', { exact: true }).fill('My unfinished context');
  await page.getByLabel('Optional note', { exact: true }).evaluate(node => node.setAttribute('data-original-form', 'true'));
  fails = true;
  await page.clock.fastForward(61_000);
  const failed = page.waitForResponse(response => new URL(response.url()).pathname === '/activities/1' && response.status() === 503);
  await page.evaluate(() => { window.dispatchEvent(new Event('offline')); window.dispatchEvent(new Event('online')); });
  await failed;
  await page.clock.runFor(2_000);
  const notice = page.getByTestId('activity-refresh-error');
  await expect(notice).toBeVisible();
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('My unfinished feedback');
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveAttribute('data-original-form', 'true');
  await expect(page.getByLabel('Route identity', { exact: true })).toHaveValue('My unfinished context');
  fails = false;
  await notice.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(notice).toHaveCount(0);
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('My unfinished feedback');
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveAttribute('data-original-form', 'true');
  expect(writes).toEqual([]);
});

test('missing activity samples have a retry that preserves unfinished feedback', async ({ page }) => {
  const { writes } = await installApi(page);
  await recordedDay(page);
  let fails = true;
  await page.route('**/activities/1/streams', route => fails
    ? route.fulfill({ status: 503, json: { detail: 'Temporary samples failure' } })
    : route.fulfill({ json: { activity_id: 1, t: [0, 30, 60], columns: { hr: [100, 120, 110] } } }));
  await page.goto('/app/activities/1?feedback=1#session-feedback');
  await page.getByLabel('Optional note', { exact: true }).fill('Keep my sample review');
  const notice = page.getByTestId('activity-stream-error');
  await expect(notice).toBeVisible();
  fails = false;
  await notice.getByRole('button', { name: 'Retry activity samples', exact: true }).click();
  await expect(notice).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Heart Rate · bpm', exact: true })).toBeVisible();
  await expect(page.getByLabel('Optional note', { exact: true })).toHaveValue('Keep my sample review');
  expect(writes).toEqual([]);
});
