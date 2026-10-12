import {test,expect} from '@playwright/test';
import {installApi,today} from './fixtures';
import AxeBuilder from '@axe-core/playwright';

const metric=(key:string,value:unknown=null,unit='')=>({key,value,unit,kind:'calculated',availability:value==null?'unavailable':'available',unavailable_reason:value==null?'missing_evidence':null,formula:'Recorded source calculation',formula_version:'test-v1',source_dependencies:[],prerequisites:[],limitations:[]});
const bucket={start:today,end:today,activity_count:0,distance_m:null,duration_s:null,elevation_gain_m:null,observed:{distance:0,duration:0,elevation:0},formula:'sum eligible recordings',formula_version:'test-v1',source_dependencies:[],quality:{}};

test('sport overview retains missingness, date control and accessible sport-specific state',async({page})=>{
 await installApi(page);
 await page.route('**/athlete/sports/running/overview**',route=>route.fulfill({json:{sport:'running',version:'test-v1',state:'empty',range:{start:today,end:today,timezone:'UTC'},quality:{limitations:[]},totals:bucket,weekly:[],monthly:[],recent_activities:[],best_efforts:[],power_duration:[],long_run_progression:[],aerobic_trend:metric('aerobic_trend'),consistency:metric('consistency'),adherence:metric('adherence'),goal_context:{focus:null,goal_progress:metric('goal_progress')},ftp:metric('confirmed_ftp'),body_mass:metric('body_mass'),advanced_metrics:[]}}));
 await page.goto('/app/sports/running');
 await expect(page.getByRole('heading',{name:'Running Overview',exact:true})).toBeVisible();
 await expect(page.getByText('No activities were recorded for this sport in the selected range.',{exact:true}).first()).toBeVisible();
 await expect(page.getByText('No eligible measurements for this chart. Missing values are not plotted as zero.',{exact:true}).first()).toBeVisible();
 expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze()).violations).toEqual([]);
});

test('structured workout prepares exact review before approval and preserves export boundary',async({page})=>{
 await installApi(page);
 let approved=false;const writes:any[]=[];
 const step={id:'warm',kind:'warmup',duration_s:600,distance_m:null,target:null,description:'Start comfortably',exercise:null,sets:null,reps:null,load_kg:null,repetitions:1,steps:[]};
 const structure={title:'Easy run',objective:'Consistency',steps:[step]};
 await page.route('**/athlete/planned-sessions/8/workout',route=>route.fulfill({json:{planned_session_id:8,plan_revision:approved?2:1,protected:false,editable:true,edit_block_reason:null,pending_draft:null,history:[],workout:approved?{id:1,revision:1,structure,payload_hash:'a'.repeat(64),source:'user_reviewed'}:null,session:{date:today,discipline:'running',session_type:'easy',duration_min:30,description:'Easy session'},education:[]}}));
 await page.route('**/athlete/planned-sessions/8/workout-drafts',route=>{const body=route.request().postDataJSON();writes.push(body);return route.fulfill({status:201,json:{id:9,plan_revision:1,workout_revision:0,status:'draft',payload_hash:'a'.repeat(64),structure:body.structure}});});
 await page.route('**/athlete/workout-drafts/9/confirm',route=>{writes.push(route.request().postDataJSON());approved=true;return route.fulfill({json:{id:1,revision:1,structure}});});
 await page.goto('/app/workouts/8');
 await page.getByRole('button',{name:'Edit workout blocks',exact:true}).click();
 await page.getByRole('button',{name:'Add a workout block',exact:true}).click();
 await page.getByRole('combobox',{name:'Block type',exact:true}).selectOption('warmup');
 await page.getByRole('combobox',{name:'Block ending condition',exact:true}).selectOption('duration');
 await page.getByLabel('Duration (seconds)',{exact:true}).fill('600');
 await page.getByRole('button',{name:'Review these workout changes',exact:true}).click();
 expect(writes).toHaveLength(1);
 expect(writes[0]).toMatchObject({expected_plan_revision:1,expected_workout_revision:0});
 await page.getByRole('button',{name:'Confirm this reviewed workout',exact:true}).click();
 expect(writes[1]).toEqual({payload_hash:'a'.repeat(64)});
 await expect(page.getByRole('link',{name:'Export approved workout as portable JSON',exact:true})).toHaveAttribute('href','/lab/workouts/8/export');
});
