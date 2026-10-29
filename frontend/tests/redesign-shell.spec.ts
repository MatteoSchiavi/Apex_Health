import { test, expect } from '@playwright/test';
import { installApi } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  test(`workspace groups secondary tools and reveals the current route: ${locale}`, async ({ page }) => {
    const { writes } = await installApi(page, { locale });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/app');
    const sidebar = page.locator('aside.shell-sidebar');
    const tools = sidebar.getByRole('button', { name: locale === 'en' ? 'Tools & more' : 'Strumenti e altro', exact: true });
    await expect(tools).toHaveAttribute('aria-expanded', 'false');
    await expect(sidebar.locator('a[href="/app/sleep"]')).toHaveCount(0);
    await expect(sidebar.getByRole('link', { name: locale === 'en' ? 'Today' : 'Oggi', exact: true })).toHaveAttribute('aria-current', 'page');
    await expect(sidebar.getByRole('link', { name: locale === 'en' ? 'Health' : 'Salute', exact: true })).toBeVisible();
    await tools.click();
    await sidebar.locator('a[href="/app/sleep"]').click();
    await expect(page).toHaveURL(/\/app\/sleep$/);
    await page.reload();
    await expect(tools).toHaveAttribute('aria-expanded', 'true');
    await expect(sidebar.locator('a[href="/app/sleep"]')).toHaveAttribute('aria-current', 'page');
    expect(writes).toHaveLength(0);
  });
}

test('mobile More traps keyboard focus, closes with Escape and restores its trigger', async ({ page }) => {
  await installApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app');
  const more = page.getByRole('button', { name: 'More', exact: true });
  await more.click();
  const dialog = page.getByRole('dialog', { name: 'More', exact: true });
  const first = dialog.getByRole('link').first();
  const last = dialog.getByRole('button', { name: 'Sign out', exact: true });
  await expect(first).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(last).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(first).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(more).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

for (const theme of ['dark', 'light'] as const) {
  test(`daily workflow keeps Apex's original visual identity in ${theme} mode`, async ({ page }) => {
    await installApi(page, { theme });
    await page.goto('/app');
    await expect(page.locator('body')).toHaveCSS('background-color', theme === 'dark' ? 'rgb(16, 16, 16)' : 'rgb(245, 244, 240)');
    await expect(page.getByTestId('today-hero').locator('.panel')).toHaveCSS('border-radius', '0px');
    const primary = page.getByTestId('daily-summary').getByRole('link');
    await expect(primary).toHaveCSS('background-color', theme === 'dark' ? 'rgb(242, 241, 237)' : 'rgb(36, 36, 32)');
    await expect(primary).toHaveCSS('border-radius', '2px');
    await expect(page.locator('aside.shell-sidebar')).toHaveCSS('width', '224px');
  });
}
