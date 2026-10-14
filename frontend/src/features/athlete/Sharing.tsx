import {useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {Link,useSearchParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {api,ApiError} from '../../app/api';
import {Badge,Button,Card,Empty,Input,Loading,Select} from '../../components/kit';

type Snapshot={type:string;title?:string;items?:Record<string,unknown>[];[key:string]:unknown};
type Preview={snapshot:Snapshot;payload_hash:string;expires_in_days:number;rights:string};
type Grant={id:number;expires_at:string;state:string;type:string;created_at:string};
const allowed:Record<string,string[]>={activity:['date','discipline','duration_s','distance_m','elevation_gain_m','avg_hr','max_hr','avg_power','np_power'],workout:['date','discipline','duration_min','distance_m','session_type','start_time','description','intensity_targets','steps'],plan:['title','starts_on','ends_on','session_count','sessions','session_instructions','intensity_targets','steps'],progress:['volume','consistency','adherence','goal_progress']};
const defaults:Record<string,string[]>={activity:['date','discipline','duration_s','distance_m'],workout:['date','discipline','duration_min','distance_m'],plan:['title','starts_on','ends_on','session_count'],progress:['volume','consistency']};
const feedback=['feedback_status','rpe','fatigue','soreness','workout_quality','feedback_note','modification_reason','terrain_notes'];
function SharedValue({value,label}:{value:unknown;label?:string}){
 const {t}=useTranslation();
 if(value===null||value===undefined)return <span className="text-muted">{t('sharing.unavailable')}</span>;
 if(typeof value!=='object')return <span className="break-words">{String(value)}</span>;
 if(Array.isArray(value))return <ul className="space-y-3">{value.map((item,i)=><li className="border-l border-hairline pl-3" key={i}><SharedValue value={item}/></li>)}</ul>;
 return <dl className="space-y-2">{Object.entries(value as Record<string,unknown>).filter(([key])=>key!=='version').map(([key,item])=><div key={key}><dt className="text-[12px] text-muted">{t('sharing.field_'+key,{defaultValue:key.replaceAll('_',' ')})}</dt><dd className="mt-1 text-[14px]"><SharedValue value={item} label={label}/></dd></div>)}</dl>;
}
function SnapshotView({snapshot}:{snapshot:Snapshot}){return <div className="space-y-4"><SharedValue value={snapshot}/></div>}
export default function Sharing({embedded=false}:{embedded?:boolean}={}){
 const {t}=useTranslation();const qc=useQueryClient();const [params]=useSearchParams();
 const initial=params.get('type');const initialType=initial&&allowed[initial]?initial:'activity';
 const [type,setType]=useState(initialType);const [ids,setIds]=useState(params.get('id')??'');const [fields,setFields]=useState(defaults[initialType]);
 const [includeFeedback,setIncludeFeedback]=useState(false);const [sport,setSport]=useState(params.get('sport')==='cycling'?'cycling':'running');const [start,setStart]=useState(params.get('start')??'');const [end,setEnd]=useState(params.get('end')??'');const [expiry,setExpiry]=useState('7');
 const [review,setReview]=useState<Preview|null>(null);const [link,setLink]=useState('');
 const selector=type==='progress'?{type,sport,starts_on:start,ends_on:end,fields,include_feedback:false}:{type,resource_ids:ids.split(/[ ,]+/).filter(Boolean).map(Number),fields,include_feedback:includeFeedback};
 const request={selection:selector,expires_in_days:Number(expiry)};
 const reset=()=>{setReview(null);setLink('');};
 const [offset,setOffset]=useState(0);
 const resources=useQuery({queryKey:['share-resources',type,offset],queryFn:()=>api.get<{items:{id:number;date:string;title?:string;discipline?:string;duration_min?:number}[];has_more:boolean}>(`/athlete/shares/resources?type=${type}&offset=${offset}`),enabled:type!=='progress'});
 const grants=useQuery({queryKey:['shares'],queryFn:()=>api.get<Grant[]>('/athlete/shares')});
 const preview=useMutation({mutationFn:()=>api.post<Preview>('/athlete/shares/preview',request),onSuccess:setReview});
 const create=useMutation({mutationFn:()=>api.post<{token:string;grant:Grant}>('/athlete/shares',{...request,preview_hash:review?.payload_hash}),onSuccess:data=>{setLink(location.origin+'/share#'+data.token);setReview(null);qc.invalidateQueries({queryKey:['shares']});}});
 const revoke=useMutation({mutationFn:(id:number)=>api.delete('/athlete/shares/'+id),onSuccess:()=>{setLink('');qc.invalidateQueries({queryKey:['shares']});}});
 const pending=preview.isPending||create.isPending;
 const toggle=(field:string)=>{reset();setFields(f=>f.includes(field)?f.filter(x=>x!==field):[...f,field]);};
 return <div className="mx-auto max-w-4xl space-y-6">{embedded ? <h2 className="section-label">{t('sharing.title')}</h2> : <h1 className="page-title">{t('sharing.title')}</h1>}<p className="text-muted">{t('sharing.privacy')}</p><Card><form className="space-y-4" onSubmit={e=>{e.preventDefault();preview.mutate();}}><fieldset disabled={pending} className="space-y-4">
  <Select label={t('sharing.type')} value={type} onChange={value=>{reset();setType(value);setIds('');setOffset(0);setFields(defaults[value]);setIncludeFeedback(false);}} options={Object.keys(allowed).map(value=>({value,label:t('sharing.type_'+value)}))}/>
  {type==='progress'?<div className="grid gap-3 sm:grid-cols-3"><Select label={t('sharing.sport')} value={sport} onChange={value=>{reset();setSport(value);}} options={['running','cycling'].map(value=>({value,label:t('athlete.focus_'+value)}))}/><Input label={t('sharing.starts_on')} type="date" value={start} onChange={value=>{reset();setStart(value);}}/><Input label={t('sharing.ends_on')} type="date" value={end} onChange={value=>{reset();setEnd(value);}}/></div>:<fieldset className="space-y-3"><legend className="mb-3 font-medium">{t('sharing.choose_records')}</legend>{resources.isLoading?<Loading/>:resources.isError?<p role="alert">{t('sharing.load_error')}</p>:resources.data?.items.map(item=><label key={item.id} className="flex items-center gap-3 text-[13px]"><input type="checkbox" checked={ids.split(',').includes(String(item.id))} onChange={e=>{reset();const chosen=ids.split(',').filter(Boolean).filter(id=>id!==String(item.id));if(e.target.checked)chosen.push(String(item.id));setIds(chosen.join(','));}}/>{item.date} · {item.title??item.discipline??t('sharing.type_'+type)}{item.duration_min!=null?` · ${item.duration_min} min`:''}</label>)}<div className="flex gap-3">{offset>0&&<Button variant="ghost" onClick={()=>setOffset(Math.max(0,offset-100))}>{t('common.prev_day',{defaultValue:'Previous'})}</Button>}{resources.data?.has_more&&<Button variant="ghost" onClick={()=>setOffset(offset+100)}>{t('sharing.more_records')}</Button>}</div>{!resources.isLoading&&!resources.isError&&!resources.data?.items.length&&<p>{t('sharing.no_records')}</p>}</fieldset>}
  <fieldset className="grid gap-2 sm:grid-cols-2"><legend className="mb-3 text-[14px] font-medium">{t('sharing.fields')}</legend>{allowed[type].map(field=><label key={field} className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={fields.includes(field)} onChange={()=>toggle(field)}/>{t('sharing.field_'+field,{defaultValue:field.replaceAll('_',' ')})}</label>)}</fieldset>
  {type!=='progress'&&<><label className="flex items-center gap-2"><input type="checkbox" checked={includeFeedback} onChange={e=>{reset();setIncludeFeedback(e.target.checked);if(!e.target.checked)setFields(f=>f.filter(x=>!feedback.includes(x)));}}/>{t('sharing.feedback_optin')}</label>{includeFeedback&&<fieldset className="grid gap-2 sm:grid-cols-2"><legend>{t('sharing.feedback_fields')}</legend>{feedback.map(field=><label key={field} className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={fields.includes(field)} onChange={()=>toggle(field)}/>{t('sharing.field_'+field,{defaultValue:field.replaceAll('_',' ')})}</label>)}</fieldset>}</>}
  <Input label={t('sharing.expiry')} type="number" min={1} max={30} value={expiry} onChange={value=>{reset();setExpiry(value);}}/><Button type="submit" disabled={!fields.length||pending||(type!=='progress'&&!ids)}>{t('sharing.preview')}</Button>
 </fieldset></form>{preview.isError&&<p role="alert" className="mt-3 text-alertText">{preview.error instanceof ApiError?preview.error.message:t('common.error')}</p>}</Card>
 {review&&<Card><h2 className="mb-4 font-medium">{t('sharing.review')}</h2><SnapshotView snapshot={review.snapshot}/><p className="my-4 text-[13px] text-muted">{t('sharing.privacy')}</p><Button disabled={pending} onClick={()=>create.mutate()}>{t('sharing.create')}</Button>{create.isError&&<p role="alert" className="mt-3 text-alertText">{t('sharing.changed')}</p>}</Card>}
 {link&&<Card><p role="status">{t('sharing.created')}</p><Input label={t('sharing.private_link')} value={link} onChange={()=>{}}/><p className="mt-2 text-[12px] text-muted">{t('sharing.link_once')}</p></Card>}
 <Card><h2 className="mb-4 font-medium">{t('sharing.grants')}</h2>{grants.isLoading?<Loading/>:grants.isError?<p role="alert">{t('sharing.load_error')}</p>:!grants.data?.length?<Empty>{t('sharing.no_grants')}</Empty>:<ul className="space-y-4">{grants.data.map(grant=><li className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3" key={grant.id}><span>#{grant.id} · {t('sharing.type_'+grant.type)} · {new Date(grant.expires_at).toLocaleString()} <Badge>{t('sharing.status_'+grant.state,{defaultValue:grant.state})}</Badge></span><Button variant="ghost" disabled={revoke.isPending||grant.state!=='active'} onClick={()=>revoke.mutate(grant.id)}>{t('sharing.revoke')}</Button></li>)}</ul>}{revoke.isError&&<p role="alert">{t('sharing.revoke_error')}</p>}</Card>
 </div>;
}
export function PublicSharedView(){
 const {t}=useTranslation();const [viewKey]=useState(()=>crypto.randomUUID());const [token]=useState(()=>window.location.hash.slice(1));
 const view=useQuery({queryKey:['public-share',viewKey],queryFn:()=>api.getWithHeaders<{snapshot:Snapshot;expires_at:string}>('/sharing/view',{'X-Apex-Share':token}),enabled:/^[A-Za-z0-9_-]{40,100}$/.test(token),retry:false,staleTime:0,gcTime:0});
 return <main className="mx-auto max-w-3xl p-6"><h1 className="page-title">{t('sharing.shared_title')}</h1><p className="my-4 text-muted">{t('sharing.read_only')}</p>{view.isLoading?<Loading/>:view.isError||!view.data?<p role="alert">{t('sharing.view_unavailable')}</p>:<Card><SnapshotView snapshot={view.data.snapshot}/><p className="mt-4 text-[12px] text-muted">{t('sharing.expires_at')}: {new Date(view.data.expires_at).toLocaleString()}</p></Card>}<Link to="/" className="text-link mt-6 inline-block">Apex Health</Link></main>;
}
