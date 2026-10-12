import { test, expect } from '@playwright/test';
import { installApi, today } from './fixtures';

for (const locale of ['en', 'it'] as const) {
  test(`strength goal shows compatible recorded estimate, explicit target and provenance (${locale})`, async ({ page }) => {
    await installApi(page, { locale });
    await page.route('**/athlete/sports/strength/overview**', route => route.fulfill({ json: {
      sport: 'strength', state: 'ready', version: 'test-v1', range: { start: today, end: today, timezone: 'UTC' },
      progression: { formula: 'Epley: recorded load × (1 + reps/30), only 1–10 reps', formula_version: 'epley-recorded-sets-v1', history_complete: true,
        limitations: [], sessions: [{ exercise: 'Barbell squat', exercise_id: 11, date: today, e1rm_kg: 87.5, sets: 2, reps: 10, volume_kg: 750, source_dependencies: ['gym_set_log:42'] }] },
      goal_context: { goal_progress: { key: 'goal_progress', value: { metric: 'exercise_estimated_1rm_kg', measurement: 87.5, target: 100, measurement_unit: 'kg', progress_pct: 87.5, exercise: 'Barbell squat', exercise_id: 11 },
        unit: 'kg', kind: 'calculated', availability: 'available', unavailable_reason: null,
        formula: 'recorded compatible measurement / explicit target * 100', formula_version: 'apex-sport-progress-v1',
        source_dependencies: ['athlete_profile:2:context.focuses.measurable_goal', 'gym_set_log:42'], prerequisites: [], limitations: ['estimated_strength_not_tested_maximum'], quality: { measurement_formula_version: 'epley-recorded-sets-v1' } } },
    } }));
    await page.goto('/app/sports/strength');
    await expect(page.getByRole('heading', { name: locale === 'en' ? 'Strength overview' : 'Panoramica forza', exact: true })).toBeVisible();
    await expect(page.getByText('Barbell squat', { exact: true })).toBeVisible();
    const target = page.locator('dl > div').filter({ has: page.locator('dt', { hasText: locale === 'en' ? /^Target$/ : /^Obiettivo$/ }) });
    await expect(target.locator('dd')).toHaveText(/^100[.,]00\s*$/);
    const progress = page.locator('dl > div').filter({ has: page.locator('dt', { hasText: locale === 'en' ? /^Target attained/ : /^Obiettivo raggiunto/ }) });
    await expect(progress.locator('dd')).toContainText(/87[.,]50/);
    await expect(page.getByText(locale === 'en' ? /Estimated strength from recorded sets/ : /Forza stimata dalle serie registrate/)).toBeVisible();
    await page.getByText(locale === 'en' ? 'Formula, source requirements and quality' : 'Formula, requisiti delle fonti e qualità', { exact: true }).first().click();
    await expect(page.getByText('gym_set_log:42', { exact: true }).first()).toBeVisible();
  });
}
