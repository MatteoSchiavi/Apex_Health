import { test, expect } from '@playwright/test';
import { installApi, overview } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  test(`daily training and Coach are reachable from the mobile bottom bar: ${locale}`, async ({ page }) => {
    await installApi(page, { locale });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/app');
    const nav = page.getByRole('navigation', { name: locale === 'en' ? 'Main navigation' : 'Navigazione principale', exact: true });
    await nav.locator('a[href="/app/training"]').click();
    await expect(page).toHaveURL(/\/app\/training$/);
    await expect(nav.locator('a[href="/app/training"]')).toHaveAttribute('aria-current', 'page');
    await nav.locator('a[href="/app/coach"]').click();
    await expect(page).toHaveURL(/\/app\/coach$/);
    await expect(nav.locator('a[href="/app/coach"]')).toHaveAttribute('aria-current', 'page');
    await page.getByRole('button', { name: locale === 'en' ? 'More' : 'Altro', exact: true }).click();
    await page.getByRole('link', { name: locale === 'en' ? 'Sleep' : 'Sonno', exact: true }).click();
    await expect(page).toHaveURL(/\/app\/sleep$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('sync failure has a direct recovery route above the daily workout', async ({ page }) => {
  await installApi(page);
  await page.route('**/dashboard/overview*', route => route.fulfill({ json: { ...overview, alerts: [{ type: 'sync_failure', severity: 'warning', message: 'Provider sync failed 36 consecutive times.' }] } }));
  await page.goto('/app');
  const action = page.getByRole('link', { name: 'Review sync status →', exact: true });
  await expect(action).toBeVisible();
  expect((await action.boundingBox())!.y).toBeLessThan((await page.getByTestId('daily-summary').boundingBox())!.y);
  await action.click();
  await expect(page).toHaveURL(/\/app\/settings\?tab=data-health$/);
  await expect(page.getByRole('tab', { name: 'Data health', exact: true })).toHaveAttribute('aria-selected', 'true');
});

test('partial sync summarizes the account and keeps feed diagnostics available on demand', async ({ page }) => {
  await installApi(page);
  await page.route('**/lab/sync-health', route => route.fulfill({ json: {
    accounts: [{ provider: 'garmin', state: 'partial', last_attempt_at: null, last_success_at: null, latest_measurement_at: null, has_successful_sync: true, data_freshness: 'fresh', stale_after_hours: 48, error_class: 'fetch_failed', failed_attempts: 3, credentials_state: 'configured', streams_failed: 1, unprocessed: 0 }],
    feeds: [{ provider: 'garmin', feed: 'sleep', state: 'available', last_attempt_at: null, last_success_at: null, latest_measurement_at: null, stale_after_hours: 48, error_class: null, failed_attempts: 0, credentials_state: 'configured', retry_state: 'idle', has_checkpoint: true }],
  } }));
  await page.goto('/app/settings?tab=data-health');
  const feed = page.getByRole('region', { name: 'garmin sleep', exact: true });
  await expect(feed).toBeHidden();
  await page.getByText('Data feed details (1)', { exact: true }).click();
  await expect(feed).toBeVisible();
  await page.getByRole('link', { name: 'Open connection and retry →', exact: true }).click();
  await expect(page).toHaveURL(/\/app\/settings\?tab=devices$/);
});
