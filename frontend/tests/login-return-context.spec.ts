import { expect, test, type Page } from '@playwright/test';
import { account, installApi, today } from './fixtures';

async function signIn(page: Page, locale: 'en' | 'it' = 'en') {
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill('athlete@example.com');
  await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
  await page.getByRole('button', { name: locale === 'en' ? 'Sign in' : 'Accedi', exact: true }).click();
}

for (const locale of ['en', 'it'] as const) {
  test(`sign-in restores the requested activity day and section (${locale})`, async ({ page }) => {
    await installApi(page, { locale });
    await page.addInitScript(locale => localStorage.setItem('apex.locale', locale), locale);
    let signedIn = false;
    await page.route('**/me', route => signedIn
      ? route.fulfill({ json: { ...account, locale } })
      : route.fulfill({ status: 401, json: { detail: 'Session expired' } }));
    await page.route('**/auth/login', route => { signedIn = true; return route.fallback(); });
    const destination = `/app/activities?date=${today}#history`;
    await page.goto(destination);
    await expect(page).toHaveURL(/\/login$/);
    await signIn(page, locale);
    await expect(page).toHaveURL(new RegExp(`/app/activities\\?date=${today}#history$`));
    await expect(page.getByRole('status').filter({ hasText: today })).toBeVisible();
  });
}

for (const from of ['https://example.com/app/training', '/app/../admin']) {
  test(`sign-in rejects a return target outside the athlete workspace: ${from}`, async ({ page }) => {
    await installApi(page);
    await page.goto('/login');
    await page.evaluate(from => {
      history.replaceState({ usr: { from }, key: 'return-test' }, '', '/login');
      dispatchEvent(new PopStateEvent('popstate'));
    }, from);
    await signIn(page);
    await expect(page).toHaveURL(/\/app$/);
  });
}
