import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { installApi, today } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const labels = JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url), 'utf8'));
  test(`feedback locks an in-flight report, retains failure and preserves the original page across navigation (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: locale === 'en' ? 'light' : 'dark' });
    let finish: () => void = () => {};
    let waiting = false;
    await page.route('**/api/feedback', async route => {
      waiting = true;
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ status: 503, json: { detail: 'Synthetic feedback failure' } });
    });
    await page.goto('/app');
    await page.getByRole('button', { name: labels.feedback.button, exact: true }).click();
    const dialog = page.getByRole('dialog');
    const message = dialog.getByRole('textbox', { name: labels.feedback.message, exact: true });
    await dialog.getByRole('combobox').selectOption('idea');
    await message.fill('A useful idea for the overview');
    await dialog.getByRole('button', { name: labels.feedback.submit, exact: true }).click();
    await expect.poll(() => waiting).toBe(true);
    await expect(message).toBeDisabled();
    await expect(dialog.getByRole('button', { name: labels.feedback.cancel, exact: true })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeVisible();
    await expect(dialog).toBeFocused();
    finish();
    await expect(dialog.getByRole('alert')).toBeVisible();
    await expect(message).toHaveValue('A useful idea for the overview');
    await dialog.getByRole('button', { name: labels.feedback.cancel, exact: true }).click();
    // Use the router so the application retains the deliberately unsent draft.
    await page.locator('a[href="/app/activities"]').first().click();
    await expect(page).toHaveURL(/\/app\/activities$/);
    await page.getByRole('button', { name: labels.feedback.button, exact: true }).click();
    await expect(dialog.getByText(labels.feedback.page.replace('{{page}}', '/app'), { exact: true })).toBeVisible();
    await expect(message).toHaveValue('A useful idea for the overview');
    await expect(dialog.getByText(labels.feedback.draft_page, { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: labels.feedback.current_page, exact: true }).click();
    await expect(message).toHaveValue('');
    await expect(dialog.getByRole('combobox')).toHaveValue('bug');
    await expect(dialog.getByText(labels.feedback.page.replace('{{page}}', '/app/activities'), { exact: true })).toBeVisible();
    expect(writes.filter(write => write.path === '/api/feedback')).toHaveLength(0);
  });

  test(`calendar distinguishes unavailable sources from an empty day and retries without discarding loaded items (${locale})`, async ({ page }) => {
    await installApi(page, { locale, theme: locale === 'en' ? 'dark' : 'light' });
    await page.setViewportSize({ width: locale === 'en' ? 1440 : 390, height: 844 });
    let waiting = false;
    let finish: () => void = () => {};
    let failed = true;
    let requests = 0;
    await page.route('**/activities?**', async route => {
      const url = new URL(route.request().url());
      if (!url.searchParams.has('offset')) return route.fallback();
      requests++;
      if (requests === 1) {
        waiting = true;
        await new Promise<void>(resolve => { finish = resolve; });
      }
      return failed ? route.fulfill({ status: 503, json: { detail: 'Synthetic calendar failure' } })
        : route.fulfill({ json: { items: [{ id: 2, local_date: today, discipline: 'running', duration_s: 1800 }], total: 1 } });
    });
    await page.goto('/app/calendar');
    await expect.poll(() => waiting).toBe(true);
    await page.getByRole('button', { name: today, exact: true }).click();
    await expect(page.getByText(labels.navigation.no_calendar_items, { exact: true })).toHaveCount(0);
    await expect(page.getByText(labels.calendarRecovery.loading_day, { exact: true })).toBeVisible();
    finish();
    const retry = page.getByRole('button', { name: labels.calendarRecovery.retry, exact: true });
    await expect(retry).toBeVisible();
    await expect(page.getByText(labels.calendarRecovery.unavailable_day, { exact: true })).toBeVisible();
    failed = false;
    await retry.click();
    await expect(page.locator('a[href="/app/activities/2"]')).toHaveCount(2);
    await expect(retry).toHaveCount(0);
    await expect(page.getByText(labels.calendarRecovery.partial, { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: today.slice(0, 8) + '28', exact: true }).click();
    await expect(page.getByText(labels.navigation.no_calendar_items, { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(locale === 'en' ? 1440 : 390);
  });
}
