import {test,expect} from '@playwright/test';
import {installApi,today} from './fixtures';
test('equipment history supports explicit links and configurable defaults',async({page})=>{
 await installApi(page);const writes:string[]=[];
 const gear={gear_id:1,name:'Trail shoes',gear_type:'shoes',active:true,hours_since_service:1,km_since_service:10,usage_pct:20,last_serviced_at:null,service_interval_hours:null,service_interval_km:50};
 await page.route('**/gear**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  if(req.resourceType()==='document')return route.fallback();
  if(req.method()!=='GET'){writes.push(req.method()+' '+path);return route.fulfill({json:{}});}
  if(path==='/gear')return route.fulfill({json:[gear]});
  return route.fulfill({json:{gear,lifetime:{activity_count:1,hours:1,km:10,missing_distance_count:0},activities:[],services:[{id:1,performed_at:today+'T07:00:00Z',service_type:'inspection',notes:'Laces replaced'}],default_discipline_ids:[],discipline_choices:[{id:1,name:'running'}],pagination:{total:0}}});
 });
 await page.route('**/activities?limit=100',route=>route.fulfill({json:{items:[{id:2,local_date:today,discipline:'running',duration_s:1800}]}}));
 await page.goto('/app/gear');await page.locator('summary').filter({hasText:'Activity and maintenance history'}).click();
 await expect(page.getByText('Laces replaced',{exact:true})).toBeVisible();
 await page.getByRole('combobox',{name:'Add an activity to this equipment',exact:true}).selectOption('2');
 await page.getByRole('button',{name:'Confirm equipment association',exact:true}).click();
 expect(writes).toContain('PUT /gear/1/activities/2');
 await page.getByRole('combobox',{name:'Sport for this equipment',exact:true}).selectOption('1');
 await page.getByRole('button',{name:'Set as default for this sport',exact:true}).click();
 expect(writes).toContain('PUT /gear/1/defaults/1');
});
