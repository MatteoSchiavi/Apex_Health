import {test,expect} from '@playwright/test';
import {installApi,today} from './fixtures';

for(const locale of ['en','it'] as const){
 test(`education shows nested prescription and block-specific alternatives: ${locale}`,async({page})=>{
  await installApi(page,{locale});let draft=false;
  const base={distance_m:null,target:null,description:'',exercise:null,sets:null,reps:null,load_kg:null,repetitions:1,steps:[]};
  const effort={...base,id:'effort',kind:'interval',duration_s:120,target:{kind:'power_w',lower:180,upper:200}};
  const recovery={...base,id:'rest',kind:'recovery',duration_s:60};
  const repeat={...base,id:'repeat',kind:'repeat',duration_s:null,repetitions:4,steps:[effort,recovery]};
  const structure={title:'Repeated efforts',objective:'Control',steps:[repeat]};
  const education=[repeat,effort,recovery].map((row,index)=>({...row,steps:[],number:index===0?'1':`1.${index}`,parent_id:index?'repeat':null,objective:locale==='it'?'Pratica controllata':'Controlled practice',execution:locale==='it'?'Segui la prescrizione registrata.':'Follow the recorded prescription.',common_mistake:index===2?(locale==='it'?'Saltare il recupero prescritto.':'Skipping prescribed recovery.'):(locale==='it'?'Partire troppo forte.':'Starting too hard.'),conservative_alternative:index===2?(locale==='it'?'Rendi il recupero più facile.':'Make recovery easier.'):(locale==='it'?'Riduci lo sforzo.':'Reduce effort.'),limitation:locale==='it'?'Indicazioni generali; il piano salvato non cambia.':'Generic guidance; the saved plan does not change.'}));
  await page.route('**/athlete/planned-sessions/8/workout',route=>route.fulfill({json:{planned_session_id:8,plan_revision:1,protected:false,editable:true,edit_block_reason:null,pending_draft:draft?{id:9,plan_revision:1,workout_revision:1,status:'draft',payload_hash:'a'.repeat(64),structure}:null,workout:{id:1,revision:1,structure},session:{date:today,discipline:'running',session_type:'interval',duration_min:15,description:null},education}}));
  await page.goto('/app/workouts/8');
  const card=page.locator('.panel').filter({has:page.getByRole('heading',{name:locale==='it'?'Come eseguire questo allenamento':'How to perform this workout',exact:true})});
  await expect(card.getByText(locale==='it'?'Potenza (watt): 180–200':'Power (watts): 180–200',{exact:true})).toBeVisible();
  await expect(card.getByRole('heading',{name:/1\.2\./})).toBeVisible();
  const recoverySection=card.locator('section').last();
  await recoverySection.locator('summary').click();
  await expect(recoverySection.getByText(locale==='it'?'Saltare il recupero prescritto.':'Skipping prescribed recovery.',{exact:true})).toBeVisible();
  await expect(recoverySection.getByText(locale==='it'?'Rendi il recupero più facile.':'Make recovery easier.',{exact:true})).toBeVisible();
  await expect(recoverySection.getByText(locale==='it'?'Nessun obiettivo di intensità prescritto':'No intensity target prescribed',{exact:true})).toBeVisible();
  draft=true;await page.reload();
  await expect(page.getByRole('button',{name:locale==='it'?'Conferma questo allenamento rivisto':'Confirm this reviewed workout',exact:true})).toBeVisible();
  await expect(card).toHaveCount(0);
 });

 test(`equipment comparison presents measured links, minimum evidence and missing state: ${locale}`,async({page})=>{
  await installApi(page,{locale});let available=true;
  const gear={gear_id:1,name:'Old shoes',gear_type:'shoes',active:true,hours_since_service:1,km_since_service:10,usage_pct:20,last_serviced_at:null,service_interval_hours:null,service_interval_km:50};
  const other={...gear,gear_id:2,name:'New shoes'};
  const record={date:today,distance_m:10000,time_s:3600,speed_m_s:2.78,avg_hr_bpm:120,avg_power_w:null};
  await page.route('**/gear**',route=>{
   const req=route.request(),path=new URL(req.url()).pathname;
   if(req.resourceType()==='document')return route.fallback();
   if(path==='/gear')return route.fulfill({json:[gear,other,{...gear,gear_id:3,name:'Bike',gear_type:'bike'}]});
   if(path.endsWith('/comparison'))return route.fulfill({json:{status:available?'available':'unavailable',pairs:available?[{selected:{...record,activity_id:11},other:{...record,activity_id:12},speed_difference_pct:1.2,context:{source:'garmin',route_id:'loop',terrain:'paved',time_convention:'elapsed',effort_type:'easy'}}]:[],eligible_counts:{selected:1,other:1},shared_activity_count:0,minimum_pairs_for_summary:2,summaries:[],history_scope:{truncated:false,activity_limit_per_gear:500,selected_total:1,other_total:1}}});
   return route.fulfill({json:{gear:path.includes('/2/')?other:gear,lifetime:{activity_count:1,hours:1,km:10,missing_distance_count:0},activities:[],services:[],default_discipline_ids:[],discipline_choices:[],pagination:{total:0}}});
  });
  await page.goto('/app/gear');
  await page.locator('summary').filter({hasText:locale==='it'?'Storico attività e manutenzione':'Activity and maintenance history'}).first().click();
  const select=page.getByRole('combobox',{name:locale==='it'?'Altra attrezzatura dello stesso tipo':'Other equipment of the same type',exact:true});
  await expect(select.locator('option',{hasText:'Bike'})).toHaveCount(0);
  await select.selectOption('2');
  await expect(page.getByRole('link',{name:today,exact:true}).first()).toHaveAttribute('href','/app/activities/11');
  await expect(page.getByText('2.78 m/s · 120 bpm',{exact:true}).first()).toBeVisible();
  await expect(page.getByText(locale==='it'?'Coppie insufficienti nello stesso contesto per un riepilogo; le singole registrazioni sono mostrate sopra.':'Too few matched pairs in one context for a summary; individual recordings are shown above.',{exact:true})).toBeVisible();
  available=false;await select.selectOption('');await select.selectOption('2');
  // A reload clears the query cache so the unavailable response is exercised.
  await page.reload();await page.locator('summary').filter({hasText:locale==='it'?'Storico attività e manutenzione':'Activity and maintenance history'}).first().click();
  await page.getByRole('combobox',{name:locale==='it'?'Altra attrezzatura dello stesso tipo':'Other equipment of the same type',exact:true}).selectOption('2');
  await expect(page.getByText(locale==='it'?'Nessuna registrazione compatibile con misure e contesto esplicito richiesti. Aggiungi il contesto reale dal dettaglio dell’attività; i dati mancanti restano indisponibili.':'No compatible recordings with the required measurements and explicit context. Add actual context from the activity detail; missing facts remain unavailable.',{exact:true})).toBeVisible();
 });
}
