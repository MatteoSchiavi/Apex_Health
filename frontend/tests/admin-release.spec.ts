import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { installApi } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const labels = JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url), 'utf8'));
  test(`admin footer reports the running release, links its exact commit and refreshes after an update (${locale})`, async ({ page }) => {
    await installApi(page, { locale, theme: locale === 'en' ? 'light' : 'dark' });
    await page.setViewportSize({ width: locale === 'en' ? 1440 : 390, height: 844 });
    let commit = 'a'.repeat(40);
    let failed = false;
    await page.route('**/version', route => failed
      ? route.fulfill({ status: 503, json: { detail: 'Synthetic version failure' } })
      : route.fulfill({ json: { version: '0.1.0', stage: 'beta', commit } }));
    await page.goto('/admin');
    const footer = page.locator('footer').filter({ has: page.getByText(labels.adminRelease.version + ' 0.1.0 · beta', { exact: true }) });
    await expect(footer).toHaveAttribute('aria-label', labels.adminRelease.title);
    const link = footer.getByRole('link');
    await expect(link).toHaveText(commit);
    await expect(link).toHaveAttribute('href', `https://github.com/MatteoSchiavi/Apex_Health/commit/${commit}`);
    commit = 'b'.repeat(40);
    await footer.getByRole('button', { name: labels.adminRelease.refresh }).click();
    await expect(link).toHaveText(commit);
    failed = true;
    await footer.getByRole('button', { name: labels.adminRelease.refresh }).click();
    await expect(footer.getByRole('status')).toHaveText(labels.adminRelease.stale);
    await expect(link).toHaveText(commit);
    failed = false;
    commit = 'development';
    await footer.getByRole('button', { name: labels.adminRelease.refresh }).click();
    await expect(footer.locator('code')).toHaveText('development');
    await expect(footer.getByRole('link')).toHaveCount(0);
    await expect(footer.getByRole('status')).toHaveCount(0);
    await footer.scrollIntoViewIfNeeded();
    expect(await footer.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  });
}
