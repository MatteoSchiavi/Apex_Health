import { expect, test, type Page } from '@playwright/test';
import { account, activity, installApi, night, today } from './fixtures';

const previous = new Date(Date.parse(today + 'T12:00:00Z') - 86400000).toISOString().slice(0, 10);
const failure = { status: 503, json: { detail: 'Temporary synthetic read failure' } };
const metric = { metric: 'resting_hr', label: 'Resting heart rate', unit: 'bpm', start_date: today, end_date: today,
  points: [{ date: today, value: 52 }], stats: { count: 1, mean: 52, min: 52, max: 52 } };
async function reconnect(page: Page) {
  await page.clock.fastForward(61_000);
  await page.evaluate(() => { dispatchEvent(new Event('offline')); dispatchEvent(new Event('online')); });
  await page.clock.runFor(2_000);
}

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  const retry = en ? 'Retry' : 'Riprova';
  const options = { locale, theme: en ? 'light' as const : 'dark' as const };
  test(`calendar day can expand to recent activities and browser Back restores the day (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, options);
    await page.setViewportSize({ width: en ? 1280 : 390, height: 844 });
    const reads: URL[] = [];
    await page.route(url => url.pathname === '/activities', route => {
      reads.push(new URL(route.request().url()));
      return route.fulfill({ json: { items: [activity], total: 1, offset: 0, limit: 50 } });
    });
    await page.goto(`/app/activities?date=${previous}`);
    await expect(page.getByRole('status').filter({ hasText: previous })).toBeVisible();
    await expect.poll(() => reads.at(-1)?.searchParams.get('start')).toBe(previous);
    const period = page.getByRole('button', { name: en ? '30 days' : '30 giorni', exact: true });
    await expect(period).toHaveAttribute('aria-pressed', 'false');
    await period.click();
    await expect(page).not.toHaveURL(/date=/);
    await expect(period).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => reads.at(-1)?.searchParams.get('end')).toBe(today);
    expect(reads.at(-1)?.searchParams.get('start')).not.toBe(previous);
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`date=${previous}`));
    await expect(page.getByRole('status').filter({ hasText: previous })).toBeVisible();
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`metric read failure retains navigation and permits a different range (${locale})`, async ({ page }) => {
    await installApi(page, options);
    await page.route(url => url.pathname === '/metrics/resting_hr', route =>
      new URL(route.request().url()).searchParams.get('days') === '28'
        ? route.fulfill({ json: metric }) : route.fulfill(failure));
    await page.goto('/app/biometrics/resting_hr');
    await expect(page.getByTestId('read-error').getByRole('button', { name: retry, exact: true })).toBeVisible();
    await expect(page.locator('main a[href="/app/biometrics"]')).toBeVisible();
    await page.getByRole('button', { name: en ? '4 weeks' : '4 settimane', exact: true }).click();
    await expect(page.locator('.hero-number')).toHaveText('52.0');
    await expect(page.getByTestId('read-error')).toHaveCount(0);
  });

  test(`sleep detail read failure retains date navigation (${locale})`, async ({ page }) => {
    await installApi(page, options);
    await page.route(url => url.pathname === `/sleep/${today}`, route => route.fulfill(failure));
    await page.route(url => url.pathname === `/sleep/${previous}`, route => route.fulfill({ json: {
      date: previous, session: { ...night, local_date: previous }, biometrics: {}, hrv_readings: [],
    } }));
    await page.goto(`/app/sleep/${today}`);
    await expect(page.getByTestId('read-error').getByRole('button', { name: retry, exact: true })).toBeVisible();
    await expect(page.locator('main a[href="/app/sleep"]')).toBeVisible();
    await page.getByRole('button', { name: en ? 'Previous day' : 'Giorno precedente', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/sleep/${previous}$`));
    await expect(page.locator('.hero-number')).toHaveText('84');
    await expect(page.getByTestId('read-error')).toHaveCount(0);
  });

  test(`sleep timeline retries independently of the night's measurements (${locale})`, async ({ page }) => {
    await installApi(page, options);
    let fails = true;
    await page.route(url => url.pathname === `/sleep/${today}/stages`, route => fails ? route.fulfill(failure) : route.fulfill({ json: {
      date: today, source: 'garmin', segments: [{ stage: 'deep', t_start: today + 'T00:00:00Z', t_end: today + 'T01:00:00Z' }],
    } }));
    await page.goto(`/app/sleep/${today}`);
    const error = page.getByTestId('read-error');
    await expect(error).toBeVisible();
    await expect(page.locator('.hero-number')).toHaveText('84');
    fails = false;
    await error.getByRole('button', { name: en ? 'Retry sleep stages' : 'Riprova le fasi del sonno', exact: true }).click();
    await expect(error).toHaveCount(0);
    await expect(page.getByLabel(en ? 'Architecture' : 'Architettura')).toBeVisible();
    await expect(page.locator('.hero-number')).toHaveText('84');
  });
}

test('invalid sleep dates have an escape without requesting a normalized or malformed night', async ({ page }) => {
  await installApi(page);
  const reads: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/sleep/')) reads.push(request.url()); });
  for (const value of ['not-a-date', '2026-02-30']) {
    await page.goto(`/app/sleep/${value}`);
    await expect(page.getByRole('alert')).toContainText('This date is invalid');
    await expect(page.getByRole('button', { name: 'Previous day', exact: true })).toBeDisabled();
    await expect(page.locator('main a[href="/app/sleep"]')).toBeVisible();
  }
  expect(reads).toEqual([]);
});

test('sleep history requests the athlete local day across UTC midnight', async ({ page }) => {
  await installApi(page);
  await page.clock.setFixedTime(new Date('2026-11-02T23:30:00Z'));
  await page.route('**/me', route => route.fulfill({ json: { ...account, timezone: 'Europe/Rome' } }));
  const response = page.waitForRequest(request => new URL(request.url()).pathname === '/sleep');
  await page.goto('/app/sleep');
  const url = new URL((await response).url());
  expect(url.searchParams.get('end')).toBe('2026-11-03');
  expect(url.searchParams.get('start')).toBe('2026-09-23');
});

test('failed metric refresh keeps the opened evidence and shows a stale notice until retry', async ({ page }) => {
  await installApi(page);
  await page.clock.install();
  let fails = false;
  await page.route(url => url.pathname === '/metrics/resting_hr', route => fails ? route.fulfill(failure) : route.fulfill({ json: metric }));
  await page.goto('/app/biometrics/resting_hr');
  const evidence = page.getByText('Understand this metric', { exact: true });
  await evidence.click();
  fails = true;
  await reconnect(page);
  const error = page.getByTestId('read-error');
  await expect(error).toContainText('The last loaded results remain visible');
  await expect(evidence).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.hero-number')).toHaveText('52.0');
  fails = false;
  await error.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(error).toHaveCount(0);
  await expect(evidence).toHaveAttribute('aria-expanded', 'true');
});
