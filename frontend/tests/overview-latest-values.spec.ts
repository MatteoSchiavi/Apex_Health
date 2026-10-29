import {expect,test,type Page} from '@playwright/test';
import {installApi,overview,today} from './fixtures';
const shiftDay=(day:string,offset:number)=>new Date(Date.parse(day+'T12:00:00Z')+offset*86400000).toISOString().slice(0,10);
const yesterday=shiftDay(today,-1);
const keys=['readiness','recovery','strain','provider_sleep_score'];
const openHistory = async(page:Page) => { await page.getByTestId('overview-history').locator('summary').click(); };
const emptyScores={readiness:{value:null,delta_7d:null},recovery:{value:null,delta_7d:null},strain:{value:null,delta_7d:null},sleep_score:{value:null,delta_7d:null}};
const trend=(metric:string,points:{date:string,value:number|null}[],unit='/100')=>({metric,label:metric,unit,start_date:shiftDay(today,-89),end_date:today,points,stats:{}});
async function missingToday(page:Page,options:{locale?:'en'|'it',empty?:boolean}={}){
 await installApi(page,{locale:options.locale,empty:options.empty});
 await page.route(url=>url.pathname==='/dashboard/overview',route=>route.fulfill({json:{...overview,date:today,anchor_is_today:true,...emptyScores,hrv_ms:null,acute_load:42,chronic_load:40,acwr:1.05}}));
 const values=[82,78,0,84];
 for(const [i,key] of keys.entries())await page.route(url=>url.pathname===`/metrics/${key}`,route=>route.fulfill({json:trend(key,[{date:yesterday,value:values[i]},{date:today,value:null}])}));
 await page.route(url=>url.pathname==='/metrics/hrv_ms',route=>route.fulfill({json:trend('hrv_ms',[{date:yesterday,value:65},{date:today,value:null}],'ms')}));
}
for(const [width,locale] of [[1440,'en'],[390,'it']] as const){
 test(`new local day retains dated latest scores and overnight HRV (${width}, ${locale})`,async({page})=>{
  await page.setViewportSize({width,height:1000});await missingToday(page,{locale});
  const dayRequests:string[]=[];page.on('request',r=>{if(new URL(r.url()).pathname==='/athlete/day')dayRequests.push(new URL(r.url()).searchParams.get('date')??'latest');});
  await page.goto('/app');await expect(page.getByTestId('score-value')).toHaveText(['82/100','78/100','0/100','84/100']);
  const label=locale==='en'?'Latest':'Ultimo';
  const scores=page.getByRole('region',{name:locale==='en'?'Daily readiness, recovery, strain and sleep':'Prontezza, recupero, sforzo e sonno giornalieri'});
  await expect(scores.getByText(`${label} · ${yesterday}`,{exact:true})).toHaveCount(4);
  await openHistory(page);
  const hrv=page.locator('a[href="/app/biometrics/hrv_ms"]').locator('..');await expect(hrv).toContainText('65');await expect(hrv).toContainText(`${label} · ${yesterday}`);
  expect(dayRequests).not.toContain(yesterday);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect((await scores.boundingBox())!.height).toBeLessThan(360);
  await scores.locator('a[href="/app/biometrics/readiness"]').click();await expect(page.locator('main')).toContainText('82.0');await expect(page.locator('main')).toContainText(yesterday);
 });
}
test('explicit date keeps missing scores and HRV missing instead of borrowing a previous day',async({page})=>{
 await missingToday(page);const scoreCalls:string[]=[];
 page.on('request',r=>{const p=new URL(r.url()).pathname;if(keys.some(k=>p===`/metrics/${k}`))scoreCalls.push(p);});
 await page.goto(`/app?date=${today}`);await expect(page.getByTestId('score-value')).toHaveText(['—','—','—','—']);
 await expect(page.getByText(`Latest · ${yesterday}`,{exact:true})).toHaveCount(0);
 await openHistory(page);
 const hrv=page.locator('a[href="/app/biometrics/hrv_ms"]').locator('..');await expect(hrv).not.toContainText('65');expect(scoreCalls).toEqual([]);
});
test('current values including zero win over older measurements',async({page})=>{
 await missingToday(page);await page.route(url=>url.pathname==='/dashboard/overview',route=>route.fulfill({json:{...overview,readiness:{value:0,delta_7d:null},hrv_ms:0}}));
 const calls:string[]=[];page.on('request',r=>{if(new URL(r.url()).pathname==='/metrics/readiness')calls.push(r.url());});
 await page.goto('/app');await expect(page.getByTestId('score-value').first()).toHaveText('0/100');
 await expect(page.getByRole('region',{name:'Daily readiness, recovery, strain and sleep'}).locator('a').first()).not.toContainText('Latest ·');expect(calls).toEqual([]);
});
test('missing history and API failure never invent score values',async({page})=>{
 await missingToday(page);await page.route(url=>url.pathname==='/metrics/readiness',route=>route.fulfill({status:503,json:{detail:'Fixture unavailable'}}));
 for(const key of keys.slice(1))await page.route(url=>url.pathname===`/metrics/${key}`,route=>route.fulfill({json:trend(key,[])}));
 await page.goto('/app');await expect(page.getByRole('region',{name:'Daily readiness, recovery, strain and sleep'}).locator('a').first()).toContainText('Latest score could not be loaded',{timeout:15000});
 await expect(page.getByTestId('score-value')).toHaveText(['—','—','—','—']);
});
test('overnight HRV outside the visible chart window stays visible with its real date',async({page})=>{
 await missingToday(page);const old=shiftDay(today,-20);
 await page.route(url=>url.pathname==='/metrics/hrv_ms',route=>route.fulfill({json:trend('hrv_ms',new URL(route.request().url()).searchParams.get('days')==='90'?[{date:old,value:61}]:[],'ms')}));
 await page.goto('/app');await openHistory(page);const hrv=page.locator('a[href="/app/biometrics/hrv_ms"]').locator('..');await expect(hrv).toContainText('61');await expect(hrv).toContainText(`Latest · ${old}`);
});
test('latest load uses one dated dashboard snapshot and its source units without changing today',async({page})=>{
 await missingToday(page);
 await page.route(url=>url.pathname==='/dashboard/overview',route=>route.fulfill({json:new URL(route.request().url()).searchParams.get('date')===yesterday?{...overview,date:yesterday,acute_load:123,chronic_load:100,acwr:1.23,load_metadata:{unit:'Garmin load',source:'garmin'}}:{...overview,...emptyScores,acute_load:null,chronic_load:null,acwr:null,load_metadata:null}}));
 await page.route(url=>url.pathname==='/metrics/acute_load',route=>route.fulfill({json:trend('acute_load',[{date:yesterday,value:123}],'load points')}));
 await page.goto('/app');await expect(page.locator('a[href="#training-load"]')).toContainText('123.0 Garmin load');await expect(page.locator('a[href="#training-load"]')).toContainText(yesterday);
 await page.locator('a[href="#training-load"]').click();
 await expect(page.locator('#training-load')).toContainText('100.0');await expect(page.locator('#training-load')).toContainText('1.23');
});
