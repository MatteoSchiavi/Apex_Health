import { expect, test } from '@playwright/test';
import { activity, installApi } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  test(`sport calculation references open the recorded activity and preserve raw provenance (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: en ? 'dark' : 'light' });
    await page.setViewportSize({ width: en ? 390 : 1440, height: 844 });
    await page.route(url => /^\/activities\/(1|2)$/.test(url.pathname), route => route.fulfill({ json: {
      ...activity, id: Number(new URL(route.request().url()).pathname.split('/').at(-1)), discipline: 'running', has_streams: false,
    } }));
    await page.route('**/activities/1/endurance', route => route.fulfill({ json: { sport: 'running', metrics: [{
      key: 'critical_speed', value: { activity_ids: [2, -1], speed_m_s: 3.5 }, unit: 'm/s', kind: 'calculated', availability: 'available',
      unavailable_reason: null, formula: 'Recorded protocol fit', formula_version: 'synthetic-v1',
      source_dependencies: ['activity:2:source_metrics.garmin.protocol', 'unrecognized:42', 'activity:9007199254740993:unsafe'],
      prerequisites: [], limitations: [],
    }] } }));
    await page.goto('/app/activities/1');
    const calculation = page.getByRole('heading', {
      name: en ? 'Estimated critical speed' : 'Velocità critica stimata', exact: true,
    }).locator('..').locator('..');
    const link = calculation.getByRole('link', { name: en ? 'View recorded activity 2' : 'Vedi attività registrata 2', exact: true });
    await expect(link).toHaveCount(1);
    await calculation.getByText(en ? 'Formula, source requirements and quality' : 'Formula, requisiti delle fonti e qualità', { exact: true }).click();
    await expect(calculation.getByText('activity:2:source_metrics.garmin.protocol', { exact: true })).toBeVisible();
    await expect(calculation.getByText('unrecognized:42', { exact: true })).toBeVisible();
    await expect(link).toHaveCount(2);
    await expect(calculation.locator('a[href="/app/activities/-1"]')).toHaveCount(0);
    await expect(calculation.locator('a[href*="900719925474099"]')).toHaveCount(0);
    await link.last().click();
    await expect(page).toHaveURL(/\/app\/activities\/2$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(en ? 'Running' : 'Corsa');
    expect(writes).toEqual([]);
  });
}
