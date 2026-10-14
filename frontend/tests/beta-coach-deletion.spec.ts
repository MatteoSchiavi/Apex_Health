import { expect, test, type Page } from '@playwright/test';
import { installApi } from './fixtures';

// Synthetic records only: no live athlete mutations or paid provider calls.
async function fixture(page: Page, options: { locale?: 'en' | 'it'; failDelete?: boolean; missingActive?: boolean } = {}) {
  await installApi(page, { locale: options.locale ?? 'en' });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('coach-fixture-initialized')) {
      localStorage.setItem('apex.chat.1.active', '5');
      sessionStorage.setItem('coach-fixture-initialized', '1');
    }
    document.cookie = 'csrf_token=browser-fixture-token; path=/';
  });
  let rows = [5, 6].map(id => ({ id, title: id === 5 ? 'Current recovery' : 'Previous training',
    started_at: '2026-10-08T10:00:00Z', last_activity_at: '2026-10-08T10:00:00Z', message_count: 2 }));
  const requests = { deletes: [] as number[], posts: 0, csrf: '' };
  await page.route(url => /^\/coach\/chats(?:\/\d+)?$/.test(url.pathname), async route => {
    const request = route.request();
    const id = Number(new URL(request.url()).pathname.split('/').at(-1));
    if (request.method() === 'DELETE') {
      requests.deletes.push(id);
      requests.csrf = request.headers()['x-csrf-token'];
      if (options.failDelete) return route.fulfill({ status: 503, json: { detail: 'Fixture unavailable' } });
      rows = rows.filter(row => row.id !== id);
      return route.fulfill({ status: 204 });
    }
    if (request.method() === 'POST') {
      requests.posts++;
      return route.fulfill({ status: 502, json: { detail: 'Synthetic Coach unavailable; please retry.' } });
    }
    if (!Number.isFinite(id)) return route.fulfill({ json: rows });
    const row = rows.find(row => row.id === id);
    if (!row || (options.missingActive && id === 5)) return route.fulfill({ status: 404, json: { detail: 'chat not found' } });
    return route.fulfill({ json: { ...row, messages: [
      { id: id * 10, role: 'user', content: `Question for ${row.title}`, referenced_data: null },
      { id: id * 10 + 1, role: 'assistant', content: `Recorded answer for ${row.title}`, referenced_data: null },
    ] } });
  });
  return requests;
}
async function openDelete(page: Page, title: string, locale: 'en' | 'it' = 'en') {
  const history = page.getByRole('button', { name: locale === 'it' ? /Conversazioni passate/ : /Past conversations/ });
  if (await history.isVisible()) await history.click();
  await page.getByRole('button', { name: locale === 'it' ? `Azioni della conversazione ${title}` : `Conversation actions for ${title}`, exact: true }).click();
  await page.getByRole('button', { name: locale === 'it' ? 'Elimina conversazione' : 'Delete conversation', exact: true }).click();
  return page.getByRole('dialog');
}
for (const locale of ['en', 'it'] as const) test(`inactive deletion preserves active messages and survives reload (${locale})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const requests = await fixture(page, { locale });
  await page.goto('/app/coach');
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toBeVisible();
  const dialog = await openDelete(page, 'Previous training', locale);
  await expect(dialog).toContainText('Previous training');
  await page.screenshot({ path: testInfo.outputPath(`coach-confirm-${locale}.png`), fullPage: true });
  await expect(dialog.getByRole('button', { name: locale === 'it' ? 'Annulla' : 'Cancel', exact: true })).toBeFocused();
  await dialog.getByRole('button', { name: locale === 'it' ? 'Elimina conversazione' : 'Delete conversation', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: /Previous training/ })).toHaveCount(0);
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Previous training');
  expect(requests.deletes).toEqual([6]);
  expect(requests.csrf).toBe('browser-fixture-token');
  await page.reload();
  await expect(page.getByRole('button', { name: /Previous training/ })).toHaveCount(0);
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('apex.chat.1.active'))).toBe('5');
});
test('mobile active deletion clears messages and persisted selection, preserves unrelated conversation', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto('/app/coach');
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toBeVisible();
  const dialog = await openDelete(page, 'Current recovery');
  await page.screenshot({ path: testInfo.outputPath('coach-confirm-mobile.png'), fullPage: true });
  await dialog.getByRole('button', { name: 'Delete conversation', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Current recovery/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Previous training/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('apex.chat.1.active'))).toBeNull();
  await page.screenshot({ path: testInfo.outputPath('coach-after-mobile-delete.png'), fullPage: true });
  await page.reload();
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: /Past conversations/ }).click();
  await page.getByRole('button', { name: /^Previous training/ }).click();
  await expect(page.getByText('Recorded answer for Previous training', { exact: true })).toBeVisible();
});
test('keyboard disclosure, focus trap, cancel and Escape send no delete request', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const requests = await fixture(page);
  await page.goto('/app/coach');
  const actions = page.getByRole('button', { name: 'Conversation actions for Previous training', exact: true });
  await actions.focus();
  await page.keyboard.press('Enter');
  await expect(actions).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true });
  await expect(cancel).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'Delete conversation', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(cancel).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(actions).toBeFocused();
  await openDelete(page, 'Previous training');
  await cancel.click();
  await expect(dialog).not.toBeVisible();
  expect(requests.deletes).toEqual([]);
  await expect(page.getByRole('button', { name: /^Previous training/ })).toBeVisible();
});
test('failed deletion remains truthful and retains session and messages after cancel', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await fixture(page, { failDelete: true });
  await page.goto('/app/coach');
  const dialog = await openDelete(page, 'Current recovery');
  await dialog.getByRole('button', { name: 'Delete conversation', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('It is still in your history');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByText('Recorded answer for Current recovery', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Current recovery/ })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('apex.chat.1.active'))).toBe('5');
  await expect(page.getByRole('status')).toHaveCount(0);
});
test('unavailable conversation blocks Enter; failed new message preserves draft', async ({ page }) => {
  const requests = await fixture(page, { missingActive: true });
  await page.goto('/app/coach');
  await expect(page.getByText('This conversation is no longer available. Choose another conversation or start a new one.', { exact: true })).toBeVisible();
  const input = page.getByRole('textbox');
  await input.fill('How should I adjust training after yesterday’s strength session?');
  await input.press('Enter');
  expect(requests.posts).toBe(0);
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  await input.press('Enter');
  await expect(page.getByText('Synthetic Coach unavailable; please retry.', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('How should I adjust training after yesterday’s strength session?');
  expect(requests.posts).toBe(1);
});

for (const locale of ['en','it'] as const) test(`disabled AI consent stays compact and voluntary on mobile (${locale})`,async({page})=>{
 const {writes}=await installApi(page,{locale,aiConsent:false});
 await page.setViewportSize({width:390,height:844});await page.goto('/app/coach');
 const title=page.locator('main h1');await expect(title).toBeVisible();
 expect((await title.boundingBox())!.y).toBeGreaterThanOrEqual(0);
 expect((await title.boundingBox())!.y).toBeLessThan(250);
 const details=page.locator('main details').filter({has:page.locator('summary').filter({hasText:locale==='en'?'AI access and consent details':'Dettagli di accesso e consenso IA'})});
 await expect(details).not.toHaveAttribute('open','');
 const history=page.getByRole('button',{name:locale==='en'?/Past conversations/:/Conversazioni passate/});
 await expect(history).toBeVisible();expect((await history.boundingBox())!.y).toBeLessThan(600);
 await details.locator('summary').first().click();
 await expect(details.getByRole('checkbox')).not.toBeChecked();
 await expect(details.getByRole('button',{name:locale==='en'?'Give voluntary AI consent':"Esprimi il consenso volontario all'IA",exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:locale==='en'?'Send':'Invia',exact:true})).toBeDisabled();
 expect(writes.some(w=>w.path.includes('/coach/chats')||w.path.includes('/consent'))).toBe(false);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
