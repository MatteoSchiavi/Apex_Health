import { test, expect } from '@playwright/test';
import { installApi, today } from './fixtures';

for (const locale of ['en', 'it'] as const) for (const theme of ['light', 'dark'] as const) {
  test(`sport analysis recovers and labels its actual range (${locale}, ${theme})`, async ({ page }) => {
    await page.setViewportSize(theme === 'dark' ? { width: 390, height: 844 } : { width: 1280, height: 900 });
    await installApi(page, { locale, theme });
    let failing = true;
    await page.route('**/athlete/sports/strength/overview**', route => failing
      ? route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
      : route.fulfill({ json: {
        sport: 'strength', state: 'empty', range: { start: today, end: today, timezone: 'UTC' },
        progression: { formula: 'Recorded sets', formula_version: 'test', history_complete: true, sessions: [], limitations: [] },
        goal_context: { goal_progress: { key: 'goal_progress', value: null, unit: '', kind: 'calculated', availability: 'unavailable', unavailable_reason: 'missing_evidence', source_dependencies: [], prerequisites: [], limitations: [] } },
      } }));
    await page.goto('/app/sports/strength');
    const retry = page.getByRole('button', { name: locale === 'en' ? 'Retry' : 'Riprova', exact: true });
    await expect(retry).toBeVisible();
    failing = false;
    await retry.click();
    const range = page.getByRole('status').filter({ hasText: locale === 'en' ? 'Showing results for' : 'Risultati mostrati dal' });
    await expect(range).toContainText(today);
    await expect(retry).toHaveCount(0);
    await page.locator('input[type="date"]').first().fill('2025-01-01');
    await expect(range).toContainText(today);
    await expect(range).not.toContainText('2025-01-01');
  });
}
