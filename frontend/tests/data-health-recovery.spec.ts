import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { installApi, today } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  const labels = JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url), 'utf8'));
  test(`evidence selection ignores late reads and never carries a note to another observation (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: locale === 'en' ? 'light' : 'dark' });
    let releaseFirst: () => void = () => {};
    let firstRead = true;
    let waiting = false;
    await page.route('**/lab/evidence/*', async route => {
      const id = Number(new URL(route.request().url()).pathname.split('/').at(-1));
      if (id === 1 && firstRead) {
        firstRead = false; waiting = true;
        await new Promise<void>(resolve => { releaseFirst = resolve; });
      }
      return route.fulfill({ json: { id: `observation:${id}:1`, marker: `Evidence record ${id}`, origin: 'garmin', local_date: today } });
    });
    await page.setViewportSize({ width: locale === 'en' ? 1440 : 390, height: 844 });
    await page.goto('/app/settings?tab=data-health');
    const sources = page.getByRole('button', { name: 'garmin ↗', exact: true });
    await sources.nth(0).click();
    await expect.poll(() => waiting).toBe(true);
    await sources.nth(1).click();
    const panel = page.getByRole('region', { name: labels.dataRecovery.selected_evidence });
    await expect(panel.getByText('Evidence record 2', { exact: true })).toBeVisible();
    releaseFirst();
    await expect(panel.getByText('Evidence record 1', { exact: true })).toHaveCount(0);
    const reason = panel.getByLabel(labels.lab.reason, { exact: true });
    await reason.fill('Only the second measurement is suspect');
    page.once('dialog', dialog => dialog.dismiss());
    await sources.nth(0).click();
    await expect(reason).toHaveValue('Only the second measurement is suspect');
    await panel.getByRole('button', { name: labels.lab.annotate, exact: true }).click();
    await expect(panel.getByRole('status')).toHaveText(labels.dataRecovery.annotation_saved);
    expect(writes.filter(write => write.path === '/lab/entries').map(write => write.body.entry)).toEqual([
      { kind: 'observation_annotation', date: today, observation_id: 2, exclude_from_analysis: true, notes: 'Only the second measurement is suspect' },
    ]);
    await reason.fill('An unsubmitted second draft');
    page.once('dialog', dialog => dialog.accept());
    await sources.nth(0).click();
    await expect(panel.getByText('Evidence record 1', { exact: true })).toBeVisible();
    await expect(panel.getByLabel(labels.lab.reason, { exact: true })).toHaveValue('');
    await expect(panel.getByRole('status')).toHaveCount(0);
  });

  test(`annotation failure retains its target and text; mismatched evidence requires retry (${locale})`, async ({ page }) => {
    await installApi(page, { locale });
    let mismatch = true;
    await page.route('**/lab/evidence/1', route => route.fulfill({ json: { id: mismatch ? 'observation:99:1' : 'observation:1:1', marker: 'Correct evidence' } }));
    let waiting = false;
    let finish: () => void = () => {};
    await page.route('**/lab/entries', async route => {
      if (route.request().method() !== 'POST') return route.fallback();
      waiting = true;
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ status: 503, json: { detail: 'Synthetic annotation failure' } });
    });
    await page.goto('/app/settings?tab=data-health');
    const sources = page.getByRole('button', { name: 'garmin ↗', exact: true });
    await sources.first().click();
    const panel = page.getByRole('region', { name: labels.dataRecovery.selected_evidence });
    await expect(panel.getByRole('button', { name: labels.dataRecovery.retry_evidence })).toBeVisible();
    await expect(panel.getByLabel(labels.lab.reason, { exact: true })).toHaveCount(0);
    mismatch = false;
    await panel.getByRole('button', { name: labels.dataRecovery.retry_evidence }).click();
    await panel.getByLabel(labels.lab.reason, { exact: true }).fill('Keep this failed annotation');
    await panel.getByRole('button', { name: labels.lab.annotate, exact: true }).click();
    await expect.poll(() => waiting).toBe(true);
    await expect(panel.getByLabel(labels.lab.reason, { exact: true })).toBeDisabled();
    await expect(panel.getByRole('button', { name: labels.common.close, exact: true })).toBeDisabled();
    await expect(sources.nth(1)).toBeDisabled();
    finish();
    await expect(panel.getByRole('alert')).toBeVisible();
    await expect(panel.getByLabel(labels.lab.reason, { exact: true })).toHaveValue('Keep this failed annotation');
    await expect(panel.getByText('Correct evidence', { exact: true })).toBeVisible();
  });

  test(`source deletion stays bound to its reviewed source and changing upload format clears the real file (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale });
    let waiting = false;
    let finish: () => void = () => {};
    await page.route('**/lab/sources/garmin/deletion-preview', async route => {
      waiting = true;
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ json: { payload_hash: 'garmin-reviewed-hash', counts: { observations: 4 }, scope: 'Synthetic Garmin deletion scope' } });
    });
    await page.goto('/app/settings?tab=data-health');
    const privacy = page.locator('.panel').filter({ has: page.getByText(labels.lab.privacy, { exact: true }) });
    const source = privacy.getByRole('combobox', { name: labels.lab.source, exact: true });
    await privacy.getByRole('button', { name: labels.lab.preview_deletion, exact: true }).click();
    await expect.poll(() => waiting).toBe(true);
    await expect(source).toBeDisabled();
    finish();
    await expect(privacy.getByText('Synthetic Garmin deletion scope', { exact: true })).toBeVisible();
    await privacy.getByRole('button', { name: labels.lab.erase_source, exact: true }).click();
    await expect.poll(() => writes.filter(write => write.path.endsWith('/delete'))).toEqual([
      { path: '/lab/sources/garmin/delete', body: { payload_hash: 'garmin-reviewed-hash' } },
    ]);
    await expect(privacy.getByText('Synthetic Garmin deletion scope', { exact: true })).toHaveCount(0);
    await source.selectOption('manual');
    await expect(privacy.getByRole('button', { name: labels.lab.erase_source, exact: true })).toHaveCount(0);
    const file = page.getByLabel(labels.lab.file, { exact: true });
    await file.setInputFiles({ name: 'measurements.csv', mimeType: 'text/csv', buffer: Buffer.from('date,value\n2026-11-01,60') });
    expect(await file.evaluate((element: HTMLInputElement) => element.files?.length)).toBe(1);
    await page.getByLabel(labels.lab.format).selectOption('fit');
    expect(await file.evaluate((element: HTMLInputElement) => element.files?.length)).toBe(0);
    await expect(page.getByText('measurements.csv', { exact: true })).toHaveCount(0);
    expect(writes.some(write => write.path.startsWith('/imports/'))).toBe(false);
  });
}
