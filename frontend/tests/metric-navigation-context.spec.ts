import { expect, test } from '@playwright/test';
import { installApi } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  test(`health details retain the selected period and return to the original search (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: en ? 'light' : 'dark' });
    await page.setViewportSize({ width: en ? 1440 : 390, height: 844 });
    const search = en ? 'resting' : 'riposo';
    await page.goto('/app/biometrics?tab=health&group=signals&days=7');
    const find = page.getByRole('textbox', { name: en ? 'Find a metric…' : 'Cerca una metrica…', exact: true });
    await find.fill(search);
    await expect(page).toHaveURL(new RegExp(`q=${search}`));
    const result = page.locator('a.metric-row[href^="/app/biometrics/resting_hr"]');
    await expect(result).toHaveAttribute('href', '/app/biometrics/resting_hr?days=7');
    if (en) await expect(page.getByTestId('metric-list-header')).toBeVisible();
    else await expect(page.getByTestId('metric-list-header')).toBeHidden();
    await result.click();
    await expect(page).toHaveURL(/\/biometrics\/resting_hr\?days=7$/);
    await expect(page.getByRole('button', { name: en ? '7 days' : '7 giorni', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: en ? '4 weeks' : '4 settimane', exact: true }).click();
    await expect(page).toHaveURL(/days=28$/);
    await page.locator('main a[href^="/app/biometrics?"]').click();
    await expect(find).toHaveValue(search);
    await expect(page.getByRole('button', { name: en ? '7 days' : '7 giorni', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await expect(find).toHaveValue(search);
    await expect(result).toBeVisible();
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
