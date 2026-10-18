import {expect,test} from '@playwright/test';
import {installApi,today} from './fixtures';

for(const locale of ['en','it'] as const){
 test(`sport deep links remain under Training; sharing lives in settings: ${locale}`,async({page})=>{
  await installApi(page,{locale});await page.goto('/app/training');
  const sections=page.getByRole('navigation',{name:locale==='en'?'Training sections':'Sezioni allenamento',exact:true});
  const sidebar=page.locator('aside').first();
  await expect(sidebar.locator('a[href^="/app/sports/"]')).toHaveCount(0);
  await expect(sidebar.locator('a[href="/app/sharing"]')).toHaveCount(0);
  await expect(sections.getByRole('link')).toHaveCount(4);
  for(const [name,path] of [[locale==='en'?'Running':'Corsa','running'],[locale==='en'?'Cycling':'Ciclismo','cycling'],[locale==='en'?'Strength':'Forza','strength']]){
   await sections.getByRole('link',{name,exact:true}).click();await expect(page).toHaveURL(new RegExp(`/app/sports/${path}$`));
   await expect(sidebar.locator('a[href="/app/training"]')).toHaveAttribute('aria-current','page');
   await expect(sections.getByRole('link',{name,exact:true})).toHaveAttribute('aria-current','page');
  }
  await page.goto('/app/settings?tab=privacy');
  await expect(page.getByRole('tab',{name:locale==='en'?'Privacy & Sharing':'Privacy e condivisione',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('heading',{name:locale==='en'?'Share selected training information':'Condividi informazioni di allenamento selezionate'})).toBeVisible();
  await page.goto('/app/sharing');await expect(page.locator('main h1')).toBeVisible();
  await page.setViewportSize({width:390,height:844});await page.goto('/app/training');
  await sections.getByRole('link',{name:locale==='en'?'Running':'Corsa',exact:true}).click();
  await expect(sections).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(page.locator('nav').filter({has:page.locator('a[href="/app/training"]')}).last().locator('a[href="/app/training"]')).toHaveAttribute('aria-current','page');
 });
}

test('gym without a weekly template can generate, explicitly refresh, and confirm exact revision',async({page})=>{
 await installApi(page);let plan:any=null;let generation=0;
 const confirmations:any[]=[];
 await page.route(url=>url.pathname===`/gym/plan/${today}/confirm`,async route=>{
  confirmations.push(route.request().postDataJSON());
  await route.fulfill({status:confirmations.length===1?409:200,json:{detail:'Training context changed',status:'confirmed'}});
 });
 const body=()=>({date:today,plan,template:null});
 await page.route(url=>url.pathname===`/gym/plan/${today}`,route=>route.fulfill({json:body()}));
 await page.route(url=>url.pathname===`/gym/plan/${today}/generate`,async route=>{
  generation++;plan={plan_id:15,revision:generation,date:today,title:'History-aware upper body',source:'template',status:'draft',adjustment_note:'Recorded lower-body sets yesterday; approved upper-body work retained.',exercises:[{gym_day_exercise_id:7,exercise_id:2,name:'Bench press',muscle_group:'push',sets:3,reps_min:8,reps_max:8,rest_seconds:60,tempo:null,notes:'40.0 kg prescribed',position:0}],progress:{sets_done:0,sets_total:3,complete:false}};
  await route.fulfill({json:plan});
 });
 await page.goto('/app/training');await page.getByRole('button',{name:'Generate plan',exact:true}).click();
 await expect(page.getByText('History-aware upper body',{exact:true})).toBeVisible();
 await expect(page.getByRole('table')).toContainText('40.0 kg prescribed');
 await expect(page.getByRole('table')).not.toContainText('8-8');
 await page.getByRole('button',{name:'Confirm plan',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Refresh the suggestion and review it');
 await page.getByRole('button',{name:'Refresh suggestion',exact:true}).click();
 await expect.poll(()=>generation).toBe(2);
 await expect(page.getByRole('alert')).toHaveCount(0);
 await page.getByRole('button',{name:'Confirm plan',exact:true}).click();
 await expect.poll(()=>confirmations.length).toBe(2);
 expect(confirmations).toEqual([{expected_revision:1},{expected_revision:2}]);
});

 test('recorded activity links to its sport progress without prominent sharing',async({page})=>{
  await installApi(page);await page.goto('/app/activities/1');
  await expect(page.locator('main a[href^="/app/sharing"]')).toHaveCount(0);
  await page.getByRole('link',{name:'View training progress',exact:true}).click();
  await expect(page).toHaveURL(/\/app\/sports\/cycling$/);
  await expect(page.getByRole('navigation',{name:'Training sections'})).toBeVisible();
 });
