import { expect, test } from '@playwright/test';
import { installApi, today } from './fixtures';

for (const [state, message, href] of [
  ['profile_ready', 'Your athlete profile is ready. You do not have an active training plan yet.', '/app/lab?tab=documents'],
  ['profile_incomplete', 'Your athlete profile is saved. Add any details that would help you plan.', '/app/settings?tab=profile'],
  ['plan_draft', 'Your training plan draft is ready to review. It has not been activated.', '/app/lab?tab=documents#document-7'],
  ['active_rest_day', 'You have an active plan. No workout is scheduled for this day.', null],
] as const) {
  test(`Today distinguishes ${state} without a workout`, async ({page}) => {
    await installApi(page, {empty:true});
    await page.route('**/athlete/day**', route => route.fulfill({json:{
      date:today,timezone:'UTC',training_focus:['running'],sessions:[],activities:[],legacy_gym_sessions:[],state:'no_plan',totals:{},sport_totals:{},
      planning_context:{state,profile_state:state==='profile_incomplete'?'incomplete':'ready',profile_revision:1,
        active_plan_id:state==='active_rest_day'?1:null,draft_id:state==='plan_draft'?3:null,draft_document_id:state==='plan_draft'?7:null},
    }}));
    await page.goto('/app');
    const panel=page.locator('.panel').filter({has:page.getByText('Your day',{exact:true})});
    await expect(panel.getByText(message,{exact:true})).toBeVisible();
    if(href) await expect(panel.locator(`a[href="${href}"]`)).toBeVisible();
    else await expect(panel.locator('a[href="/app/settings?tab=profile"]')).toHaveCount(0);
    await expect(panel.getByText('Add context or review an existing plan when useful. Apex will not invent a workout from missing information.',{exact:true})).toHaveCount(0);
  });
}

test('recorded activities come before planned workouts and distances stay within their sport',async({page})=>{
  await installApi(page,{empty:true});
  const total=(value:number,unit:string)=>({value,unit,available_sessions:1,total_sessions:1});
  const activity=(id:number,discipline:string,duration_s:number,distance_m:number)=>({id,discipline,start_time:today+'T08:00:00Z',duration_s,distance_m,
    planned_session_id:null,association:'independent',candidate_session_ids:[],checkin:null,comparison:null});
  await page.route('**/athlete/day**',route=>route.fulfill({json:{date:today,timezone:'UTC',training_focus:['running','cycling'],state:'multiple_sessions',legacy_gym_sessions:[],
    sessions:[{id:10,plan_id:1,plan_revision:1,discipline:'strength',date:today,start_time:'18:00',duration_min:30,description:'Gym later',status:'planned',protected:false,workout_protected:false,plan_protected:false,activity_id:null,checkin:null}],
    activities:[activity(1,'running',3600,10000),activity(2,'road_cycling',7200,40000)],totals:{duration_s:total(10800,'s')},
    sport_totals:{running:{duration_s:total(3600,'s'),distance_m:total(10000,'m')},cycling:{duration_s:total(7200,'s'),distance_m:total(40000,'m')}}}}));
  await page.goto('/app');
  const panel=page.locator('.panel').filter({has:page.getByText('Your day',{exact:true})});
  await panel.getByTestId('daily-details').locator('summary').first().click();
  await expect(panel.getByRole('region',{name:'Recorded activities',exact:true})).toBeVisible();
  const labels=await panel.locator('section[aria-label]').evaluateAll(elements=>elements.map(e=>e.getAttribute('aria-label')));
  expect(labels.indexOf('Recorded activities')).toBeLessThan(labels.indexOf('Planned sessions'));
  const sports=panel.getByRole('region',{name:'Recorded totals by sport'});
  await expect(sports).toContainText('10.0 km');
  await expect(sports).toContainText('40.0 km');
  await expect(sports).not.toContainText('50.0 km');
});
