import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { installApi, today } from './fixtures';

const recorded = ['Today: resting HR 48 bpm; Body Battery 55 /100', 'Past week: comparable recordings are available.', "Next: review today's workout."];
for (const locale of ['en','it'] as const) for (const theme of ['light','dark'] as const) {
  const en=locale==='en';
  test(`a pending check-in can read the saved AI result without generating again (${locale}/${theme})`,async({page})=>{
    const fixture=await installApi(page,{locale,theme});
    await page.setViewportSize({width:theme==='dark'?390:1440,height:900});
    let opens=0,reads=0;
    await page.route('**/dashboard/check-in',route=>{
      if(route.request().method()==='POST') {
        opens++;return route.fulfill({json:{status:'ready',mode:'recorded',reason:'pending',date:today,slot:'morning',attempted_at:today+'T08:15:00Z',lines:recorded}});
      }
      reads++;return route.fulfill({json:{status:'ready',mode:'ai',date:today,slot:'morning',generated_at:today+'T08:15:00Z',lines:['AI check-in completed.',"The week's coverage is incomplete.",'Review the next workout.']}});
    });
    await page.goto('/app');
    const card=page.getByTestId('today-checkin');
    await expect(card).toContainText(en?'AI summary is finishing':'riepilogo IA in preparazione');
    await card.getByText(en?'Why recorded data?':'Perché vedo i dati registrati?',{exact:true}).click();
    await expect(card).toContainText(en?'AI attempt:':'Tentativo IA:');
    await card.getByRole('button',{name:en?'Check saved summary':'Controlla riepilogo salvato',exact:true}).click();
    await expect(card).toContainText('AI check-in completed.');
    expect(opens).toBe(1);expect(reads).toBe(1);expect(fixture.writes).toEqual([]);
    const lines=page.getByTestId('checkin-lines');
    expect(await lines.evaluate(el=>el.getBoundingClientRect().height)).toBeLessThanOrEqual(73);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  });
}

for(const locale of ['en','it'] as const) test(`a cached validation failure explains its cause and preserves recordings after read failure (${locale})`,async({page})=>{
  const en=locale==='en';
  await installApi(page,{locale,theme:en?'light':'dark'});
  let opens=0,reads=0;
  await page.route('**/dashboard/check-in',route=>{
    if(route.request().method()==='GET') {reads++;return route.fulfill({status:503,json:{detail:'Synthetic read failure'}});}
    opens++;return route.fulfill({json:{status:'ready',mode:'recorded',reason:'grounding',detail:'UNCITED_NUMERIC_TEXT',date:today,slot:'morning',attempted_at:today+'T08:15:00Z',lines:recorded}});
  });
  await page.goto('/app');
  const card=page.getByTestId('today-checkin');
  await card.getByText(en?'Why recorded data?':'Perché vedo i dati registrati?',{exact:true}).click();
  await expect(card).toContainText('UNCITED_NUMERIC_TEXT');
  await expect(card).toContainText(en?'could not be verified':'Non è stato possibile verificare');
  await card.getByRole('button',{name:en?'Check saved summary':'Controlla riepilogo salvato',exact:true}).click();
  await expect(card.getByRole('status')).toContainText(en?'Could not check':'Impossibile controllare');
  await expect(card).toContainText(recorded[0]);
  expect(opens).toBe(1);expect(reads).toBe(1);
});

test('a used AI budget is distinguished from a provider failure without another generation request',async({page})=>{
  await installApi(page);
  let requests=0;
  await page.route('**/dashboard/check-in',route=>{requests++;return route.fulfill({json:{status:'ready',mode:'recorded',reason:'budget',date:today,slot:'morning',attempted_at:today+'T08:15:00Z',lines:recorded}});});
  await page.goto('/app');
  const card=page.getByTestId('today-checkin');
  await expect(card).toContainText('Daily AI budget reached');
  await card.getByText('Why recorded data?',{exact:true}).click();
  await expect(card).toContainText('daily account or conversation AI budget');
  expect(requests).toBe(1);
});
