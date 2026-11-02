import { expect, test } from '@playwright/test';
import { installApi } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  test(`activity period survives detail navigation, Back and reload (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: en ? 'light' : 'dark' });
    await page.setViewportSize({ width: en ? 1440 : 390, height: 844 });
    await page.goto('/app/activities');
    const period = page.getByRole('button', { name: en ? '30 days' : '30 giorni', exact: true });
    await period.click();
    await expect(page).toHaveURL(/\/activities\?days=30$/);
    await page.locator('main tbody a[href="/app/activities/1"]').first().click();
    await expect(page).toHaveURL(/\/activities\/1$/);
    await page.goBack();
    await expect(period).toHaveAttribute('aria-pressed', 'true');
    await page.reload();
    await expect(period).toHaveAttribute('aria-pressed', 'true');
    expect(writes).toEqual([]);
  });
}
