import {test,expect} from '@playwright/test';
import {installApi} from './fixtures';

test('sharing displays an exact preview before issuing a private link and revokes it',async({page})=>{
 await installApi(page);
 const calls:string[]=[];let grants:any[]=[];
 await page.route('**/athlete/shares**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;calls.push(req.method()+' '+path);
  if(path.endsWith('/resources'))return route.fulfill({json:{items:[{id:4,date:'2026-10-12',discipline:'running',duration_min:30}],has_more:false}});
  if(req.method()==='GET')return route.fulfill({json:grants});
  if(req.method()==='DELETE'){grants=[{...grants[0],state:'revoked'}];return route.fulfill({status:204});}
  const body=req.postDataJSON();
  expect(body.selection.include_feedback).toBe(false);
  expect(body.selection.fields).toEqual(['date','discipline','duration_s','distance_m']);
  if(path.endsWith('/preview'))return route.fulfill({json:{snapshot:{type:'activity',items:[{date:'2026-10-12',discipline:'running',duration_s:1800,distance_m:4000}]},payload_hash:'a'.repeat(64),expires_in_days:7,rights:'view'}});
  expect(body.preview_hash).toBe('a'.repeat(64));
  grants=[{id:1,type:'activity',state:'active',expires_at:'2026-10-19T12:00:00Z',created_at:'2026-10-12T12:00:00Z'}];
  return route.fulfill({status:201,json:{token:'A'.repeat(43),grant:grants[0]}});
 });
 await page.goto('/app/sharing?type=activity&id=4');
 await page.getByRole('button',{name:'Review sharing preview',exact:true}).click();
 await expect(page.getByText('4000',{exact:true})).toBeVisible();
 expect(calls.filter(x=>x==='POST /athlete/shares')).toHaveLength(0);
 await page.getByRole('button',{name:'Create this read-only sharing link',exact:true}).click();
 await expect(page.getByLabel('Private sharing link',{exact:true})).toHaveValue(/\/share#A{43}$/);
 await page.getByRole('button',{name:'Revoke this link',exact:true}).click();
 await expect(page.getByLabel('Private sharing link',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Revoke this link',exact:true})).toBeDisabled();
});

test('public sharing transmits the capability only through a header, with no writes',async({page})=>{
 const requests:any[]=[];
 await page.route('**/sharing/view**',route=>{requests.push(route.request());return route.fulfill({json:{snapshot:{type:'activity',items:[{discipline:'running',distance_m:4000}]},expires_at:'2026-10-19T12:00:00Z',rights:'view'}});});
 await page.goto('/share#'+'A'.repeat(43));
 await expect(page.getByText('4000',{exact:true})).toBeVisible();
 expect(requests).toHaveLength(1);
 expect(new URL(requests[0].url()).search).toBe('');
 expect(requests[0].headers()['x-apex-share']).toBe('A'.repeat(43));
 expect(requests[0].method()).toBe('GET');
 await expect(page.getByRole('button',{name:'Create this read-only sharing link'})).toHaveCount(0);
});
