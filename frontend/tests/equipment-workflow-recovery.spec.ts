import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { installApi, today } from './fixtures';

async function equipmentFixture(page: Page, locale: 'en' | 'it') {
  await installApi(page, { locale, theme: locale === 'en' ? 'light' : 'dark' });
  const gear = { gear_id: 1, name: 'Trail shoes', gear_type: 'shoes', active: true,
    hours_since_service: 1, km_since_service: 10, usage_pct: 20, last_serviced_at: null,
    service_interval_hours: 10 as number | null, service_interval_km: 50 as number | null };
  const state = { gear, items: [gear], failedHistory: false, linked: false, defaults: [] as number[], services: [] as object[] };
  const writes: { method: string; path: string; body: Record<string, unknown> }[] = [];
  await page.route(url => url.pathname === '/gear' || url.pathname.startsWith('/gear/'), async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method !== 'GET') {
      const body = request.postData() ? request.postDataJSON() : {};
      writes.push({ method, path, body });
      if (method === 'POST' && path === '/gear') state.items.push({ ...gear, ...body, gear_id: 2 });
      if (method === 'PATCH' && path === '/gear/1') Object.assign(gear, body);
      if (method === 'PUT' && path === '/gear/1/activities/2') state.linked = true;
      if (method === 'PUT' && path === '/gear/1/defaults/1') state.defaults = [1];
      if (method === 'POST' && path === '/gear/1/service') state.services.push({ id: 1, performed_at: today + 'T08:00:00Z', service_type: 'inspection', notes: 'Service recorded' });
      return route.fulfill({ json: { gear_id: path === '/gear' ? 2 : 1 } });
    }
    if (path === '/gear') return route.fulfill({ json: state.items });
    if (state.failedHistory) return route.fulfill({ status: 503, json: { detail: 'Temporary history failure' } });
    return route.fulfill({ json: { gear, lifetime: { activity_count: state.linked ? 1 : 0, hours: 1, km: 10, missing_distance_count: 0 },
      activities: state.linked ? [{ id: 2, date: today, discipline: 'running', duration_s: 1800, distance_m: 5000 }] : [],
      services: state.services, default_discipline_ids: state.defaults, discipline_choices: [{ id: 1, name: 'running' }], pagination: { total: state.linked ? 1 : 0 },
    } });
  });
  await page.route('**/activities?limit=100', route => route.fulfill({ json: {
    items: [{ id: 2, local_date: today, discipline: 'running', duration_s: 1800 }],
  } }));
  return { state, writes };
}

for (const locale of ['en', 'it'] as const) {
  const labels = JSON.parse(readFileSync(new URL(`../src/locales/${locale}.json`, import.meta.url), 'utf8'));
  test(`equipment links, defaults and service preserve reminder edits and only patch the edited field (${locale})`, async ({ page }) => {
    const { state, writes } = await equipmentFixture(page, locale);
    await page.clock.install();
    await page.setViewportSize({ width: locale === 'en' ? 1440 : 390, height: 844 });
    await page.goto('/app/gear');
    const card = page.locator('.panel').filter({ has: page.getByText('Trail shoes', { exact: true }) });
    const history = card.locator('details').first();
    await history.locator('summary').first().click();
    const km = history.getByLabel(labels.lab.interval_km, { exact: true });
    const hours = history.getByLabel(labels.lab.interval_hours, { exact: true });
    await expect(km).toHaveValue('50');
    await km.fill('100');
    await km.evaluate(element => element.setAttribute('data-original-editor', 'true'));
    await history.getByRole('combobox', { name: labels.equipment.link_activity, exact: true }).selectOption('2');
    await history.getByRole('button', { name: labels.equipment.link, exact: true }).click();
    await expect(history.getByRole('status')).toHaveText(labels.gearRecovery.association_saved);
    await expect(km).toHaveValue('100');
    await history.getByRole('combobox', { name: labels.equipment.default_sport, exact: true }).selectOption('1');
    await history.getByRole('button', { name: labels.equipment.set_default, exact: true }).click();
    await expect(history.getByRole('status')).toHaveText(labels.gearRecovery.defaults_saved);
    await expect(km).toHaveValue('100');
    await card.getByRole('button', { name: labels.lab.record_service, exact: true }).click();
    await expect(history.getByText('Service recorded', { exact: true })).toBeVisible();
    await expect(km).toHaveValue('100');
    state.gear.service_interval_hours = 20;
    await page.clock.fastForward(61_000);
    await page.evaluate(() => { dispatchEvent(new Event('offline')); dispatchEvent(new Event('online')); });
    await page.clock.runFor(2_000);
    await expect(hours).toHaveValue('20');
    await expect(km).toHaveValue('100');
    await expect(km).toHaveAttribute('data-original-editor', 'true');
    await history.getByRole('button', { name: labels.equipment.save_reminders, exact: true }).click();
    await expect(history.getByRole('status')).toHaveText(labels.gearRecovery.reminders_saved);
    expect(writes.filter(write => write.method === 'PATCH')).toEqual([{ method: 'PATCH', path: '/gear/1', body: { service_interval_km: 100 } }]);
    expect(state.gear.service_interval_hours).toBe(20);
  });

  test(`equipment creation locks the submitted fields, keeps failed text and resets only after success (${locale})`, async ({ page }) => {
    const { state, writes } = await equipmentFixture(page, locale);
    let attempts = 0;
    let waiting = false;
    let finish: () => void = () => {};
    await page.route('**/gear', async route => {
      if (route.request().method() !== 'POST') return route.fallback();
      attempts++;
      if (attempts > 1) return route.fallback();
      waiting = true;
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ status: 503, json: { detail: 'Temporary create failure' } });
    });
    await page.goto('/app/gear');
    const card = page.locator('.panel').filter({ has: page.getByText(labels.lab.add_gear, { exact: true }) });
    const name = card.getByLabel(labels.lab.title, { exact: true });
    await name.fill('   ');
    const save = card.getByRole('button', { name: labels.lab.save, exact: true });
    await save.click();
    await expect(card.getByRole('alert')).toHaveText(labels.gearRecovery.name_required);
    expect(attempts).toBe(0);
    await name.fill('  New trail shoes  ');
    const hours = card.getByLabel(labels.lab.interval_hours, { exact: true });
    await hours.fill('0.5');
    await save.click();
    await expect.poll(() => waiting).toBe(true);
    await expect(name).toBeDisabled();
    await expect(hours).toBeDisabled();
    finish();
    await expect(card.getByRole('alert')).toBeVisible();
    await expect(name).toHaveValue('  New trail shoes  ');
    await save.dblclick();
    await expect(card.getByRole('status')).toHaveText(labels.gearRecovery.added);
    await expect(name).toHaveValue('');
    expect(attempts).toBe(2);
    expect(writes.filter(write => write.path === '/gear')).toHaveLength(1);
    expect(state.items).toHaveLength(2);
    expect(state.items[1]).toMatchObject({ name: 'New trail shoes', service_interval_hours: 0.5 });
    await name.fill('Unsubmitted next item');
    const existing = page.locator('.panel').filter({ has: page.getByText('Trail shoes', { exact: true }) });
    await existing.getByRole('button', { name: labels.lab.record_service, exact: true }).click();
    await expect(name).toHaveValue('Unsubmitted next item');
    await expect(card.getByRole('status')).toHaveCount(0);
  });

  test(`retired equipment can be reactivated without losing its history (${locale})`, async ({ page }) => {
    const { state, writes } = await equipmentFixture(page, locale);
    await page.goto('/app/gear');
    const card = page.locator('.panel').filter({ has: page.getByText('Trail shoes', { exact: true }) });
    await card.getByRole('button', { name: labels.lab.retire, exact: true }).click();
    await expect(card.getByRole('button', { name: labels.lab.record_service, exact: true })).toBeDisabled();
    await card.getByRole('button', { name: labels.gearRecovery.reactivate, exact: true }).click();
    await expect(card.getByRole('button', { name: labels.lab.record_service, exact: true })).toBeEnabled();
    expect(state.gear.active).toBe(true);
    expect(writes.map(write => write.body)).toEqual([{ active: false }, { active: true }]);
  });
}
