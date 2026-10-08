import { expect, test } from '@playwright/test';
import { installApi } from './fixtures';

for (const locale of ['en','it'] as const) test(`coach displays checked values separately and excludes invalid receipts (${locale})`, async ({ page }) => {
  await installApi(page, { locale });
  await page.addInitScript(() => localStorage.setItem('apex.chat.1.active', '5'));
  await page.route(url => url.pathname === '/coach/chats/5', route => route.fulfill({ json: {
    id:5,title:'Recovery',started_at:'2026-10-08T10:00:00Z',last_activity_at:'2026-10-08T10:00:00Z',message_count:3,
    messages:[
      {id:1,role:'user',content:'How is my recovery trending?',referenced_data:null},
      {id:2,role:'assistant',content:'Recorded resting heart rate is available; longer context is needed.',referenced_data:{grounding:{status:'structured',verified_claims:[{metric:'resting_hr',value:52,unit:'bpm'}]}}},
      {id:3,role:'assistant',content:'Measured claims could not be verified.',referenced_data:{grounding:{status:'invalid',verified_claims:[{metric:'resting_hr',value:999,unit:'bpm'}]}}},
    ],
  } }));
  await page.goto('/app/coach');
  const label = locale === 'it' ? 'Evidenze verificate' : 'Checked evidence';
  await expect(page.getByText(label, { exact:true })).toHaveCount(1);
  await page.getByText(label, { exact:true }).click();
  await expect(page.getByText('52 bpm', { exact:true })).toBeVisible();
  await expect(page.getByText('999 bpm', { exact:true })).toHaveCount(0);
  await expect(page.getByText(locale === 'it' ? 'Frequenza cardiaca a riposo' : 'Resting heart rate', { exact:true })).toBeVisible();
});
