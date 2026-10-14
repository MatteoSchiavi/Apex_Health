import {test,expect} from '@playwright/test';
import {installApi,today} from './fixtures';

test('journal saves correct activity, preserves optional feedback and tracks later unsaved edits',async({page})=>{
  await installApi(page,{empty:true});
  let checkin:any=null;
  const writes:any[]=[];
  await page.route('**/athlete/day**',route=>route.fulfill({json:{date:today,timezone:'UTC',training_focus:['running'],state:'one_session',legacy_gym_sessions:[],sessions:[],totals:{},
    activities:[{id:4,discipline:'running',start_time:today+'T08:00:00Z',duration_s:1800,distance_m:4000,planned_session_id:null,association:'independent',candidate_session_ids:[],comparison:null,checkin}]}}));
  await page.route('**/athlete/checkins',async route=>{const body=route.request().postDataJSON();writes.push(body);checkin={...body,id:1,activity_id:4,planned_session_id:null,revision:(checkin?.revision??0)+1};await route.fulfill({json:checkin});});
  await page.goto('/app');
  await page.getByTestId('daily-details').locator('summary').first().click();
  await page.locator('summary').filter({hasText:'Quick post-session check-in'}).click();
  await page.getByLabel('Perceived fatigue', {exact:true}).fill('7');
  await page.getByLabel('Soreness', {exact:true}).fill('3');
  await page.getByLabel('Workout quality', {exact:true}).fill('8');
  await page.getByLabel('Reason for modification', {exact:true}).fill('Shortened for work');
  await page.getByLabel('Terrain and environmental notes', {exact:true}).fill('Warm and hilly');
  await page.getByRole('button',{name:'Save check-in',exact:true}).click();
  expect(writes[0]).toMatchObject({activity_id:4,fatigue:7,soreness:3,workout_quality:8,modification_reason:'Shortened for work',terrain_notes:'Warm and hilly'});
  await expect(page.getByRole('status').filter({hasText:/^Saved$/})).toBeVisible();
  await page.getByLabel('Perceived fatigue',{exact:true}).fill('6');
  await expect(page.getByRole('status').filter({hasText:/^Saved$/})).toHaveCount(0);
  await expect(page.getByRole('status').filter({hasText:'Unsaved'})).toBeVisible();
});
