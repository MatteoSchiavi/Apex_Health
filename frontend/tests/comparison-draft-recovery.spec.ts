import { expect, test, type Page } from '@playwright/test';
import { installApi } from './fixtures';

async function reconnect(page: Page) {
  await page.clock.fastForward(61_000);
  await page.evaluate(() => { dispatchEvent(new Event('offline')); dispatchEvent(new Event('online')); });
  await page.clock.runFor(2_000);
}
const assertion = (route: string) => ({ provider: 'garmin', context: {
  route_id: route, terrain: 'paved', indoor: true, time_convention: 'elapsed', effort_type: 'easy',
}, provenance: { asserted_at: '2026-11-02T10:00:00Z', verified: false } });

for (const locale of ['en', 'it'] as const) {
  const en = locale === 'en';
  test(`comparison draft survives failed and newer reads until explicit reload (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale, theme: en ? 'dark' : 'light' });
    await page.setViewportSize({ width: en ? 390 : 1440, height: 844 });
    await page.clock.install();
    let fail = false;
    let newer = false;
    await page.route('**/activities/1/comparison-context', route => fail
      ? route.fulfill({ status: 503, json: { detail: 'Temporary context failure' } })
      : route.fulfill({ json: { activity_id: 1, revision: (newer ? 'b' : 'a').repeat(64),
        providers: ['garmin', 'strava'], assertions: newer ? [assertion('Saved on another device')] : [],
        recorded_context_providers: [], outdoor_weather_available: false,
      } }));
    await page.goto('/app/activities/1');
    const route = page.getByLabel(en ? 'Route identity' : 'Identità del percorso', { exact: true });
    await route.fill('My unfinished route');
    await route.evaluate(element => element.setAttribute('data-original-editor', 'true'));
    fail = true;
    await reconnect(page);
    const error = page.getByTestId('read-error');
    await expect(error).toBeVisible();
    await expect(route).toHaveValue('My unfinished route');
    await expect(route).toHaveAttribute('data-original-editor', 'true');
    fail = false;
    newer = true;
    await error.getByRole('button', { name: en ? 'Retry comparison context' : 'Riprova il contesto del confronto', exact: true }).click();
    await expect(error).toHaveCount(0);
    await expect(page.getByRole('status').filter({ hasText: en ? 'Newer context is available' : 'È disponibile un contesto più recente' })).toBeVisible();
    await expect(route).toHaveValue('My unfinished route');
    await expect(route).toHaveAttribute('data-original-editor', 'true');
    await page.getByRole('button', { name: en ? 'Reload current context' : 'Ricarica il contesto attuale', exact: true }).click();
    await expect(route).toHaveValue('Saved on another device');
    expect(writes).toEqual([]);
  });

  test(`switching comparison source requires discarding the current draft (${locale})`, async ({ page }) => {
    const { writes } = await installApi(page, { locale });
    await page.route('**/activities/1/comparison-context', route => route.fulfill({ json: {
      activity_id: 1, revision: 'a'.repeat(64), providers: ['garmin', 'strava'], assertions: [],
      recorded_context_providers: [], outdoor_weather_available: false,
    } }));
    await page.goto('/app/activities/1');
    const route = page.getByLabel(en ? 'Route identity' : 'Identità del percorso', { exact: true });
    const source = page.getByRole('combobox', { name: en ? 'Recorded source' : 'Fonte della registrazione', exact: true });
    await route.fill('Keep my unsaved route');
    page.once('dialog', dialog => dialog.dismiss());
    await source.selectOption('strava');
    await expect(source).toHaveValue('garmin');
    await expect(route).toHaveValue('Keep my unsaved route');
    page.once('dialog', dialog => dialog.accept());
    await source.selectOption('strava');
    await expect(source).toHaveValue('strava');
    await expect(route).toHaveValue('');
    expect(writes).toEqual([]);
  });
}

test('profile refresh failure and retry preserve the same unsaved editor', async ({ page }) => {
  const { writes } = await installApi(page);
  await page.clock.install();
  let fail = false;
  await page.route('**/athlete/profile', route => fail
    ? route.fulfill({ status: 503, json: { detail: 'Temporary profile failure' } }) : route.fallback());
  await page.goto('/app/settings?tab=profile');
  await page.getByRole('button', { name: 'Complete later', exact: true }).click();
  const notes = page.locator("textarea[maxlength='8000']");
  await notes.fill('Keep this athlete context while the connection recovers.');
  await notes.evaluate(element => element.setAttribute('data-original-editor', 'true'));
  fail = true;
  await reconnect(page);
  const error = page.getByTestId('read-error');
  await expect(error).toBeVisible();
  await expect(notes).toHaveAttribute('data-original-editor', 'true');
  await expect(notes).toHaveValue('Keep this athlete context while the connection recovers.');
  fail = false;
  await error.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(error).toHaveCount(0);
  await expect(notes).toHaveAttribute('data-original-editor', 'true');
  await expect(notes).toHaveValue('Keep this athlete context while the connection recovers.');
  expect(writes).toEqual([]);
});
