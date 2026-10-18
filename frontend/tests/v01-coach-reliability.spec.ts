import { expect, test, type Page, type Route } from '@playwright/test';
import { installApi } from './fixtures';

// All requests use synthetic records. No live data or AI provider is involved.
async function coachFixture(page: Page, locale: 'en' | 'it' = 'en') {
  const fixture = await installApi(page, { locale });
  const posts: { route: Route; body: { text: string; session_id?: number } }[] = [];
  let saved = false;
  const row = {
    id: 7, title: 'Training question', message_count: 2,
    started_at: '2026-10-17T10:00:00Z', last_activity_at: '2026-10-17T10:00:00Z',
  };
  const detail = () => ({ ...row, messages: [
    { id: 1, role: 'user', content: posts.at(-1)?.body.text ?? '', referenced_data: null },
    { id: 2, role: 'assistant', content: 'Synthetic reply: review the plan before changing it.', referenced_data: { model: 'synthetic-model', drafts: [{ id: 41 }] } },
  ] });
  await page.route(url => /^\/coach\/chats(?:\/\d+)?$/.test(url.pathname), async route => {
    if (route.request().method() === 'POST') {
      posts.push({ route, body: route.request().postDataJSON() });
      return;
    }
    if (route.request().method() === 'DELETE') {
      saved = false;
      return route.fulfill({ status: 204 });
    }
    if (new URL(route.request().url()).pathname === '/coach/chats')
      return route.fulfill({ json: saved ? [row] : [] });
    return route.fulfill({ json: detail() });
  });
  return {
    posts, writes: fixture.writes,
    save: () => { saved = true; },
    succeed: async (index: number) => {
      saved = true;
      await posts[index].route.fulfill({ json: detail() });
    },
    fail: (index: number) => posts[index].route.fulfill({ status: 502, json: { detail: 'Synthetic provider unavailable.' } }),
  };
}

for (const locale of ['en', 'it'] as const) test(`failed question and retry preserve the next draft (${locale})`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const fixture = await coachFixture(page, locale);
  await page.goto('/app/coach');
  const composer = page.getByRole('textbox');
  const first = 'Help me review tomorrow’s running session.';
  const followup = 'Also consider my available training time on Sunday.';
  await composer.fill(first);
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(1);
  await composer.fill(followup);
  await composer.press('Enter');
  expect(fixture.posts).toHaveLength(1);
  await fixture.fail(0);
  await expect(page.getByRole('alert')).toHaveText('Synthetic provider unavailable.');
  await expect(composer).toHaveValue(followup);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('apex.chat.1.draft'))).toBe(followup);
  await page.screenshot({ path: testInfo.outputPath(`coach-recovery-${locale}.png`), fullPage: true });
  await page.getByText(locale === 'en' ? 'Question without a reply' : 'Domanda senza risposta', { exact: true }).click();
  await expect(page.getByText(first, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: locale === 'en' ? 'Retry this question' : 'Riprova questa domanda', exact: true }).click();
  await expect.poll(() => fixture.posts.length).toBe(2);
  expect(fixture.posts.map(post => post.body)).toEqual([{ text: first }, { text: first }]);
  await expect(composer).toHaveValue(followup);
  await fixture.succeed(1);
  await expect(page.getByText('Synthetic reply: review the plan before changing it.', { exact: true })).toBeVisible();
  await expect(composer).toHaveValue(followup);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByText('synthetic-model', { exact: false })).not.toBeVisible();
  await page.getByText(locale === 'en' ? 'Reply details' : 'Dettagli della risposta', { exact: true }).click();
  await expect(page.getByText('synthetic-model', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(composer).toHaveValue(followup);
  await expect(page.getByText('Synthetic reply: review the plan before changing it.', { exact: true })).toBeVisible();
});

test('long-running request reports elapsed waiting, keeps drafts editable and requires separate proposal approval', async ({ page }) => {
  await page.clock.install();
  const fixture = await coachFixture(page);
  await page.goto('/app/coach');
  const composer = page.getByRole('textbox');
  await composer.fill('Review my training week.');
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(1);
  await expect(page.getByRole('status')).toHaveText('Waiting for Coach’s reply…');
  await expect(page.getByRole('button', { name: 'New conversation', exact: true })).toBeDisabled();
  await expect(composer).toBeEnabled();
  await page.clock.fastForward(31_000);
  await expect(page.getByRole('status')).toHaveText('Coach has not returned a reply yet.');
  await expect(page.getByText('Waiting time: 0:31', { exact: true })).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  await page.getByRole('button', { name: 'Review proposals', exact: true }).click();
  await expect(page).toHaveURL(/tab=changes/);
  await expect(page.getByRole('status')).toHaveText('Coach has not returned a reply yet.');
  await expect(page.getByText('Training proposals need your review and approval before they change your plan.', { exact: true })).toBeVisible();
  expect(fixture.writes.filter(write => write.path.includes('/approve'))).toEqual([]);
  await page.getByRole('button', { name: 'Conversation', exact: true }).click();
  await fixture.succeed(0);
  await expect(page.getByRole('status')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Review proposals', exact: true })).toHaveAttribute('href', '/app/coach?tab=changes');
  await page.getByRole('link', { name: 'Review proposals', exact: true }).click();
  expect(fixture.writes.filter(write => write.path.includes('/approve'))).toEqual([]);
  await expect(page.getByRole('link', { name: 'Your plan', exact: true })).toHaveAttribute('href', '/app/training?tab=planning');
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  await expect(page).toHaveURL(/tab=analysis/);
  await expect(composer).toBeVisible();
});

test('history refresh recovers a reply without retrying the question', async ({ page }) => {
  const fixture = await coachFixture(page);
  await page.goto('/app/coach');
  const composer = page.getByRole('textbox');
  await composer.fill('Please review this training week.');
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(1);
  await fixture.fail(0);
  await expect(composer).toHaveValue('Please review this training week.');
  fixture.save();
  await page.getByRole('button', { name: 'Refresh conversation history', exact: true }).click();
  await page.getByRole('button', { name: /^Training question/ }).click();
  expect(fixture.posts).toHaveLength(1);
  await expect(composer).toHaveValue('Please review this training week.');
  await expect(page.getByText('Synthetic reply: review the plan before changing it.', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('deleting an active failed conversation clears its retry target and keeps the draft', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const fixture = await coachFixture(page);
  await page.goto('/app/coach');
  const composer = page.getByRole('textbox');
  await composer.fill('First question.');
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(1);
  await fixture.succeed(0);
  await expect(page.getByText('Synthetic reply: review the plan before changing it.', { exact: true })).toBeVisible();
  await composer.fill('Keep this follow-up question.');
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(2);
  await fixture.fail(1);
  await expect(page.getByRole('button', { name: 'Retry this question', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Conversation actions for Training question', exact: true }).click();
  await page.getByRole('button', { name: 'Delete conversation', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete conversation', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry this question', exact: true })).toHaveCount(0);
  await expect(composer).toHaveValue('Keep this follow-up question.');
  await composer.press('Enter');
  await expect.poll(() => fixture.posts.length).toBe(3);
  expect(fixture.posts[2].body).toEqual({ text: 'Keep this follow-up question.' });
  await fixture.fail(2);
});
