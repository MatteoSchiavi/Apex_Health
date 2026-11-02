import { expect, test } from '@playwright/test';
import { installApi } from './fixtures';

test('explicit profile reload cannot treat cached data after a failed read as successful', async ({ page }) => {
  await installApi(page);
  let failedRead = false;
  let updated = false;
  let delay = false;
  let waiting = false;
  let finish: () => void = () => {};
  await page.route('**/athlete/profile', async route => {
    if (route.request().method() === 'PUT') {
      updated = true;
      return route.fulfill({ status: 409, json: { detail: 'Profile changed' } });
    }
    if (failedRead) return route.fulfill({ status: 503, json: { detail: 'Read unavailable' } });
    if (delay) { waiting = true; await new Promise<void>(resolve => { finish = resolve; }); }
    return route.fulfill({ json: { training_focus: ['running'], revision: updated ? 2 : 1,
      context: { onboarding_step: 5, athlete_notes: updated ? 'Latest saved context' : 'Original saved context' },
    } });
  });
  await page.goto('/app/settings?tab=profile');
  const notes = page.locator("textarea[maxlength='8000']");
  await expect(notes).toHaveValue('Original saved context');
  await notes.fill('Keep my unsaved correction');
  await notes.evaluate(element => element.setAttribute('data-original-editor', 'true'));
  const save = page.getByRole('button', { name: 'Save athlete context', exact: true });
  await save.click();
  await expect(page.getByRole('alert')).toContainText('This record changed');
  failedRead = true;
  const reload = page.getByRole('button', { name: 'Reload current context', exact: true });
  page.once('dialog', dialog => dialog.accept());
  await reload.click();
  await expect(page.getByTestId('read-error')).toBeVisible();
  await expect(notes).toBeEnabled();
  await expect(notes).toHaveValue('Keep my unsaved correction');
  await expect(notes).toHaveAttribute('data-original-editor', 'true');
  await expect(reload).toBeVisible();
  failedRead = false;
  delay = true;
  page.once('dialog', dialog => dialog.accept());
  await reload.click();
  await expect(notes).toBeDisabled();
  await expect(save).toBeDisabled();
  await expect(reload).toBeDisabled();
  await expect.poll(() => waiting).toBe(true);
  finish();
  await expect(notes).toBeEnabled();
  await expect(notes).toHaveValue('Latest saved context');
  await expect(page.getByTestId('read-error')).toHaveCount(0);
});
