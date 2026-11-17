import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { activity, installApi, today } from './fixtures';
import { validatedCoachContext } from '../src/features/coach/coachContext';

for (const locale of ['en','it'] as const) for (const theme of ['light','dark'] as const) {
  const en = locale === 'en';
  test(`existing plan → adapt → reviewed question preserves baseline and draft (${locale}/${theme})`, async ({page}) => {
    const fixture=await installApi(page,{locale,theme,empty:true});
    await page.setViewportSize({width:theme==='dark'?390:1440,height:900});
    await page.addInitScript(() => localStorage.setItem('apex.chat.1.draft','Keep my existing question'));
    const sessions = [
      {id:11,date:today,session_type:'Completed run',duration_min:40,editable:false,block_reason:'completed_or_skipped'},
      {id:12,date:today,session_type:'Protected intervals',duration_min:40,editable:false,block_reason:'protected'},
      {id:13,date:today,session_type:'Upcoming easy run',duration_min:40,editable:true,block_reason:null},
    ];
    await page.route('**/athlete/plans?*',route=>route.fulfill({json:{date:today,today,plans:[{id:3,title:'Existing baseline',revision:4,start_date:today,end_date:today,protected:false,can_adapt:true,sessions}]}}));
    await page.goto('/app/training?tab=planning');
    await expect(page.getByRole('heading',{name:'Existing baseline',exact:true})).toBeVisible();
    await expect(page.getByRole('link',{name:/Completed run/})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    await page.getByRole('link',{name:en?'Adjust upcoming loads ↗':'Adatta i prossimi carichi ↗',exact:true}).click();
    const composer=page.getByRole('textbox');
    await expect(composer).toHaveValue('Keep my existing question');
    await page.getByRole('button',{name:en?'Review question':'Rivedi domanda',exact:true}).click();
    await expect(composer).toHaveValue('Keep my existing question');
    await page.getByRole('button',{name:en?'Replace with prepared question':'Sostituisci con la domanda preparata',exact:true}).click();
    const prompt=await composer.inputValue();
    expect(prompt).toContain('#3'); expect(prompt).toContain('changes_propose');
    expect(prompt).toContain(en?'do not create a replacement plan':'non creare un piano sostitutivo');
    expect(fixture.writes).toEqual([]);
    await page.getByRole('link',{name:en?'Return to plan':'Torna al piano',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Existing baseline',exact:true})).toBeVisible();
  });
}

test('activity analysis is prepared explicitly and list return retains range and sport',async({page})=>{
  const fixture=await installApi(page);
  await page.goto('/app/activities?days=30&sport=road_cycling');
  await page.locator('main tbody a[href="/app/activities/1"]').first().click();
  const back=page.getByRole('link',{name:'All Activities',exact:true});
  await expect(back).toHaveAttribute('href','/app/activities?days=30&sport=road_cycling');
  await back.click();
  await expect(page).toHaveURL(/days=30&sport=road_cycling$/);
  await page.locator('main tbody a[href="/app/activities/1"]').first().click();
  await page.getByRole('link',{name:'Analyse with Coach ↗',exact:true}).click();
  await expect(page.getByRole('textbox')).toHaveValue('');
  await page.getByRole('button',{name:'Review question',exact:true}).click();
  expect(await page.getByRole('textbox').inputValue()).toContain('activity #1');
  expect(fixture.writes).toEqual([]);
});

test('workout guide reads approved steps without recording completion',async({page})=>{
  const fixture=await installApi(page,{empty:true});
  const step=(id:string,kind:string)=>({id,kind,duration_s:300,distance_m:null,target:null,description:id,exercise:null,sets:null,reps:null,load_kg:null,repetitions:1,steps:[]});
  await page.route('**/athlete/planned-sessions/8/workout',route=>route.fulfill({json:{planned_session_id:8,plan_revision:1,protected:true,editable:false,edit_block_reason:'protected',workout:{id:1,revision:1,payload_hash:'a'.repeat(64),source:'manual',structure:{title:'Approved workout',objective:'Easy movement',steps:[step('Warm up','warmup'),step('Cool down','cooldown')]},duration_total_s:600},session:{date:today,discipline:'running',session_type:'Easy run',duration_min:10,description:''},education:[]}}));
  await page.goto('/app/workouts/8');
  await page.getByRole('button',{name:'Start workout',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Step 1 of 2',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Next step',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Step 2 of 2',exact:true})).toBeFocused();
  await page.getByRole('button',{name:'Review and record result',exact:true}).click();
  await expect(page.locator('#workout-completion')).toBeFocused();
  expect(fixture.writes).toEqual([]);
  await page.getByRole('button',{name:'Close workout guide',exact:true}).click();
  await expect(page.getByRole('button',{name:'Start workout',exact:true})).toBeFocused();
});

test('recorded fallback is clearly labelled and stays within three lines without extra requests',async({page})=>{
  const fixture=await installApi(page);
  await page.route('**/dashboard/check-in',route=>route.fulfill({json:{status:'ready',mode:'recorded',reason:'provider',date:today,slot:'morning',lines:['Today: resting HR 52 bpm','Past week: not enough comparable readings for a trend.',"Next: review today’s workout."]}}));
  await page.goto('/app');
  await expect(page.getByTestId('today-checkin')).toContainText('Recorded data · AI summary unavailable');
  await expect(page.getByTestId('checkin-lines')).toBeVisible();
  await page.getByRole('link',{name:'Activities',exact:true}).first().click();
  await page.goBack();
  expect(fixture.writes).toEqual([]);
});

test('coach rejects ambiguous and foreign workflow identifiers',()=>{
  expect(validatedCoachContext({coachContext:{userId:1,date:today,planId:3,activityId:1}},1)).toBeNull();
  expect(validatedCoachContext({coachContext:{userId:2,date:today,planId:3}},1)).toBeNull();
  expect(validatedCoachContext({coachContext:{userId:1,date:today,activityId:-1}},1)).toBeNull();
});


test('activity Coach context uses the account day when the provider local date differs',async({page})=>{
  await installApi(page);
  await page.route('**/activities/1',route=>route.request().isNavigationRequest()?route.fallback():route.fulfill({json:{...activity,local_date:'2000-01-01'}}));
  await page.goto('/app/activities/1');
  await page.getByRole('link',{name:'Analyse with Coach ↗',exact:true}).click();
  expect(await page.evaluate(()=>history.state.usr.coachContext)).toEqual({userId:1,date:today,activityId:1});
  await expect(page.getByRole('button',{name:'Review question',exact:true})).toBeEnabled();
});


test('a failed plan read offers recovery without implying that the existing plan must be recreated',async({page})=>{
  const fixture=await installApi(page,{empty:true});
  let fail=true;
  await page.route('**/athlete/plans?*',route=>fail?route.fulfill({status:503,json:{detail:'Synthetic read failure'}}):route.fulfill({json:{date:today,today,plans:[]}}));
  await page.goto('/app/training?tab=planning');
  const recovery=page.locator('.panel').filter({hasText:'Your current plan could not be loaded.'});
  await expect(recovery).toBeVisible();
  await expect(page.getByRole('button',{name:'Prepare import review',exact:true})).toHaveCount(0);
  fail=false;
  await recovery.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(recovery).toHaveCount(0);
  expect(fixture.writes).toEqual([]);
});

for (const current of [false,true]) test(`guided workout uses only current approved instructions; pending review does not replace them (${current})`,async({page})=>{
  const fixture=await installApi(page,{empty:true});
  const step={id:'approved',kind:'easy',duration_s:1200,distance_m:null,target:null,description:'Approved easy block',exercise:null,sets:null,reps:null,load_kg:null,repetitions:1,steps:[]};
  const approved={title:'Approved workout',objective:'',steps:[step]};
  await page.route('**/athlete/planned-sessions/8/workout',route=>route.fulfill({json:{planned_session_id:8,plan_revision:2,protected:false,editable:true,edit_block_reason:null,instructions_current:current,workout:{id:1,revision:1,payload_hash:'a'.repeat(64),source:'manual',structure:approved,duration_total_s:1200},pending_draft:{id:2,plan_revision:2,workout_revision:1,payload_hash:'b'.repeat(64),structure:{...approved,title:'Unapproved proposed workout',steps:[{...step,id:'proposed',description:'Unapproved block'}]},duration_total_s:1200},session:{date:today,discipline:'running',session_type:'Easy run',duration_min:20,description:''},education:[]}}));
  await page.goto('/app/workouts/8');
  if (!current) {
    await expect(page.getByText(/Your workout target changed after these instructions were approved/)).toBeVisible();
    await expect(page.getByRole('button',{name:'Start workout',exact:true})).toHaveCount(0);
  } else {
    await page.getByRole('button',{name:'Start workout',exact:true}).click();
    const guide=page.locator('.panel').filter({has:page.getByRole('heading',{name:'Follow approved instructions',exact:true})});
    await expect(guide).toContainText('Approved easy block');
    await expect(guide).not.toContainText('Unapproved block');
  }
  expect(fixture.writes).toEqual([]);
});
