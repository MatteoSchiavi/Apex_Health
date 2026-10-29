import { expect, test } from '@playwright/test';
import { activity, installApi, today } from './fixtures';

const selectedDate = '2026-10-26';
const saved = {
  id: 90, activity_id: 31, planned_session_id: null, revision: 2,
  status: 'completed', rpe: 7, pain: false, felt_unwell: false,
  note: 'Already saved', fatigue: null, soreness: null, workout_quality: null,
  modification_reason: '', terrain_notes: '',
};

for (const locale of ['en', 'it'] as const) {
  test(`${locale} daily feedback links open and save only their selected activity at mobile width`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApi(page, { locale, empty: true });
    await page.route('**/me', route => route.fulfill({ json: {
      id: 1, user_id: 1, email: 'athlete@example.com', name: 'Alex Morgan', role: 'owner',
      locale, timezone: 'America/Los_Angeles', units: 'metric', theme: 'light', ai_access_tier: 'full',
    } }));
    const dayRequests: string[] = [];
    let omitSelected = false;
    const writes: { path: string; body: Record<string, unknown> }[] = [];
    const activities = [
      { ...activity, id: 31, local_date: selectedDate, start_time: '2026-10-27T06:00:00Z', checkin: saved },
      { ...activity, id: 32, local_date: selectedDate, start_time: '2026-10-27T06:30:00Z', discipline: 'running', checkin: null },
    ];
    await page.route('**/athlete/day**', route => {
      const url = new URL(route.request().url());
      dayRequests.push(url.searchParams.get('date') ?? '');
      return route.fulfill({ json: {
        date: selectedDate, timezone: 'America/Los_Angeles', training_focus: ['running'],
        sessions: [], activities: activities.filter(item => !omitSelected || item.id !== 32).map(({ laps, ...item }) => ({
          ...item, duration_s: 1800, distance_m: 4000, planned_session_id: null,
          association: 'independent', candidate_session_ids: [], comparison: null,
        })),
        legacy_gym_sessions: [], state: 'activity_recorded', totals: {}, sport_totals: {}, is_historical: true,
      } });
    });
    await page.route(url => /^\/activities\/(31|32)$/.test(url.pathname), route => {
      const id = Number(new URL(route.request().url()).pathname.split('/').pop());
      const item = activities.find(candidate => candidate.id === id)!;
      return route.fulfill({ json: { ...item, laps: [], has_streams: false, stream_types: [], data_completeness: 'partial' } });
    });
    await page.route('**/athlete/checkins', route => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      writes.push({ path: new URL(route.request().url()).pathname, body });
      return route.fulfill({ json: { ...body, id: 91, activity_id: 32, planned_session_id: null, revision: 1 } });
    });

    await page.goto(`/app?date=${selectedDate}`);
    const summary = page.getByTestId('daily-summary');
    await expect(summary).toBeVisible();
    const dayActions = page.getByRole('navigation', { name: locale === 'en' ? 'Day actions' : 'Azioni del giorno', exact: true });
    const reviewLink = dayActions.locator('a[href="/app/activities/31?feedback=1#session-feedback"]');
    const addLink = dayActions.locator('a[href="/app/activities/32?feedback=1#session-feedback"]');
    await expect(reviewLink).toBeVisible();
    await expect(addLink).toBeVisible();
    const scores = page.getByRole('region', { name: locale === 'en' ? 'Daily readiness, recovery, strain and sleep' : 'Prontezza, recupero, sforzo e sonno giornalieri' });
    await expect(scores).toBeVisible();
    const heroBox = (await page.getByTestId('today-hero').boundingBox())!;
    const scoresBox = (await scores.boundingBox())!;
    expect(heroBox.y + heroBox.height).toBeLessThan(scoresBox.y);
    const primaryBox = (await summary.getByRole('link').boundingBox())!;
    expect(primaryBox.y + primaryBox.height).toBeLessThan(844);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await addLink.click();
    await expect(page).toHaveURL(/\/app\/activities\/32\?feedback=1#session-feedback$/);
    const checkin = page.locator('[data-testid="daily-details"] details').first();
    await expect(checkin).toHaveAttribute('open', '');
    expect(writes).toEqual([]);
    expect(dayRequests).toContain(selectedDate);

    const noteLabel = locale === 'en' ? 'Optional note' : 'Nota facoltativa';
    await expect(page.getByLabel(noteLabel, {exact:true})).toHaveCount(1);
    await page.getByLabel(noteLabel, { exact: true }).fill('Feedback for activity 32');
    await page.getByRole('button', { name: locale === 'en' ? 'Save check-in' : 'Salva il riscontro', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: locale === 'en' ? /^Saved$/ : /^Salvato$/ })).toBeVisible();
    expect(writes).toHaveLength(1);
    expect(writes[0].body).toMatchObject({ activity_id: 32, note: 'Feedback for activity 32' });
    expect(writes[0].body).not.toHaveProperty('planned_session_id');

    await page.goto('/app/activities/31');
    const ordinaryDetails = page.locator('[data-testid="daily-details"] details').first();
    await expect(ordinaryDetails).not.toHaveAttribute('open', '');
    await page.goto('/app/activities/31?feedback=1#session-feedback');
    await expect(page.locator('[data-testid="daily-details"] details').first()).toHaveAttribute('open', '');
    await expect(page.getByLabel(noteLabel, {exact:true})).toHaveValue('Already saved');
    expect(writes).toHaveLength(1);

    omitSelected = true;
    await page.goto('/app/activities/32?feedback=1#session-feedback');
    await expect(page.getByRole('status').filter({hasText: locale === 'en' ? 'Feedback is unavailable' : 'Il riscontro non è disponibile'})).toBeVisible();
    await expect(page.getByLabel(noteLabel, {exact:true})).toHaveCount(0);
    expect(writes).toHaveLength(1);
    omitSelected = false;
    await page.getByRole('button', {name: locale === 'en' ? 'Retry' : 'Riprova', exact:true}).click();
    await expect(page.getByLabel(noteLabel, {exact:true})).toBeVisible();
    await expect(page.getByLabel(noteLabel, {exact:true})).toHaveValue('');
    expect(writes).toHaveLength(1);
  });
}
