import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { Badge, Button, Input, Select } from "../../components/kit";
import type { AthleteDay, Checkin } from "./types";
import { useUi } from "../../app/stores/ui";

type Form = {status:string;rpe:string;pain:string;unwell:string;note:string;fatigue:string;soreness:string;workout_quality:string;modification_reason:string;terrain_notes:string};
const formOf=(c?:Checkin|null):Form=>({status:c?.status??"completed",rpe:String(c?.rpe??""),pain:c?.pain==null?"":c.pain?"yes":"no",unwell:c?.felt_unwell==null?"":c.felt_unwell?"yes":"no",note:c?.note??"",fatigue:String(c?.fatigue??""),soreness:String(c?.soreness??""),workout_quality:String(c?.workout_quality??""),modification_reason:c?.modification_reason??"",terrain_notes:c?.terrain_notes??""});
export function SessionCheckin({ activityId, plannedSessionId, checkin, defaultOpen=false }: { activityId?: number; plannedSessionId?: number; checkin?: Checkin | null; defaultOpen?: boolean }) {
  const { t } = useTranslation();
  const qc=useQueryClient();
  const uid=useUi(state=>state.me?.user_id);
  const [form,setForm]=useState(()=>formOf(checkin));
  const [saved,setSaved]=useState(()=>JSON.stringify(formOf(checkin)));
  const [revision,setRevision]=useState(checkin?.revision??0);
  const dirty=JSON.stringify(form)!==saved;
  const dirtyRef=useRef(dirty);dirtyRef.current=dirty;
  const set=(key:keyof Form,value:string)=>setForm(f=>({...f,[key]:value}));
  const number=(value:string)=>value===""?null:Number(value);
  const save=useMutation({mutationFn:(submitted:Form)=>api.put<Checkin>("/athlete/checkins",{
    activity_id:activityId,planned_session_id:plannedSessionId,expected_revision:revision,status:submitted.status,
    rpe:submitted.status==="skipped"?null:number(submitted.rpe),pain:submitted.pain===""?null:submitted.pain==="yes",felt_unwell:submitted.unwell===""?null:submitted.unwell==="yes",
    fatigue:number(submitted.fatigue),soreness:number(submitted.soreness),workout_quality:submitted.status==="skipped"?null:number(submitted.workout_quality),
    note:submitted.note,modification_reason:submitted.modification_reason,terrain_notes:submitted.terrain_notes,
  }),onSuccess:receipt=>{const next=formOf(receipt);setForm(next);setSaved(JSON.stringify(next));setRevision(receipt.revision);for(const key of ["athlete-day","endurance","lab","athlete-sport-overview","structured-workout"])qc.invalidateQueries({queryKey:[key]});}});
  const [review,setReview]=useState<{current:Checkin|null}|null>(null);
  const refresh=useMutation({mutationFn:async()=>{
    const entry=qc.getQueriesData<AthleteDay>({queryKey:["athlete-day",uid],type:"active"}).find(([,day])=>
      activityId?day?.activities.some(item=>item.id===activityId):day?.sessions.some(item=>item.id===plannedSessionId));
    if(!entry?.[1])throw new Error("Check-in is no longer available in the current day");
    // Fetch separately so a failed refresh cannot replace the parent day view
    // with its error state and unmount this unsaved form.
    const day=await api.get<AthleteDay>("/athlete/day?date="+encodeURIComponent(entry[1].date));
    const row=activityId?day.activities.find(item=>item.id===activityId):day.sessions.find(item=>item.id===plannedSessionId);
    if(day.date!==entry[1].date||!row)throw new Error("Check-in is no longer available in the current day");
    qc.setQueryData(entry[0],day);
    return {current:row.checkin??null};
  },onSuccess:setReview});
  const conflict=save.error instanceof ApiError&&save.error.status===409;
  useEffect(()=>{if(!dirtyRef.current&&!conflict&&!refresh.isPending&&!review){const next=formOf(checkin);setForm(next);setSaved(JSON.stringify(next));setRevision(checkin?.revision??0);}},[checkin?.revision,activityId,plannedSessionId,conflict,refresh.isPending,review]);
  function acceptReview(keepEdits:boolean){
    if(!review)return;
    const current=formOf(review.current);
    if(!keepEdits)setForm(current);
    setSaved(JSON.stringify(current));setRevision(review.current?.revision??0);
    setReview(null);save.reset();refresh.reset();
  }
  const label=(key:keyof Form)=>t("athlete."+(({status:"session_status",note:"checkin_note",unwell:"felt_unwell"} as Partial<Record<keyof Form,string>>)[key]??key));
  const display=(key:keyof Form,value:string)=>!value?t("design.not_specified"):key==="status"?t("athlete.state_"+value):key==="pain"||key==="unwell"?t("athlete."+value):value;
  const reviewed=review?formOf(review.current):null;
  const changes=reviewed?(Object.keys(form) as (keyof Form)[]).filter(key=>form[key]!==reviewed[key]):[];
  const choices=[{value:"",label:t("design.not_specified")},{value:"yes",label:t("athlete.yes")},{value:"no",label:t("athlete.no")}];
  return <details open={defaultOpen} className="mt-3 border-t border-hairline pt-3 text-[13px]">
    <summary className="cursor-pointer text-ink2">{t("athlete.checkin_title")}</summary>
    <form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();if(!conflict&&!refresh.isPending&&!review)save.mutate(form);}}>
      <fieldset disabled={save.isPending||refresh.isPending} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2"><Select label={t("athlete.session_status")} value={form.status} onChange={value=>set("status",value)} options={(activityId?["completed","partial"]:["completed","partial","skipped"]).map(value=>({value,label:t("athlete.state_"+value)}))}/>
          {form.status!=="skipped"&&<Input label={t("athlete.rpe")} type="number" min={0} max={10} step={1} value={form.rpe} onChange={value=>set("rpe",value)}/>}
        </div>
        <Input label={t("athlete.checkin_note")} value={form.note} maxLength={2000} onChange={value=>set("note",value)}/>
        <details className="border-t border-hairline pt-3">
          <summary className="cursor-pointer text-ink2">{t("athlete.additional_feedback")}</summary>
          <div className="mt-3 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {(["fatigue","soreness","workout_quality"] as const).filter(key=>form.status!=="skipped"||key!=="workout_quality").map(key=><Input key={key} label={t("athlete."+key)} type="number" min={0} max={10} step={1} value={form[key]} onChange={value=>set(key,value)}/>)}
              <Select label={t("athlete.pain")} value={form.pain} onChange={value=>set("pain",value)} options={choices}/><Select label={t("athlete.felt_unwell")} value={form.unwell} onChange={value=>set("unwell",value)} options={choices}/>
            </div>
            {(["modification_reason","terrain_notes"] as const).map(key=><Input key={key} label={t("athlete."+key)} value={form[key]} maxLength={1000} onChange={value=>set(key,value)}/>)}
          </div>
        </details>
        <p className="text-[12px] text-muted">{t("athlete.checkin_limits")}</p>
        {save.isError&&<p role="alert" className="text-alertText">{t(conflict?"athlete.conflict":"athlete.save_error")}</p>}
        {conflict&&!review&&<Button variant="ghost" type="button" disabled={refresh.isPending} onClick={()=>refresh.mutate()}>{t(refresh.isPending?"common.loading":"athlete.checkin_review_current")}</Button>}
        {refresh.isError&&<p role="alert" className="text-alertText">{t("athlete.checkin_review_error")}</p>}
        {review&&reviewed&&<section aria-label={t("athlete.checkin_review_current")} className="space-y-3 border border-hairline p-3">
          <p>{t("athlete.checkin_review_note")}</p>
          <p>{t("athlete.checkin_saved_value")}: {display("status",reviewed.status)}</p>
          {!!changes.length&&<dl className="space-y-3">{changes.map(key=><div key={key}><dt className="font-medium">{label(key)}</dt><dd className="mt-1 break-words"><span className="block">{t("athlete.checkin_saved_value")}: {display(key,reviewed[key])}</span><span className="block">{t("athlete.checkin_your_value")}: {display(key,form[key])}</span></dd></div>)}</dl>}
          <div className="flex flex-wrap gap-3"><Button variant="ghost" type="button" onClick={()=>acceptReview(true)}>{t("athlete.checkin_keep_edits")}</Button><Button variant="ghost" type="button" onClick={()=>acceptReview(false)}>{t("athlete.checkin_use_saved")}</Button></div>
        </section>}
        <div className="flex items-center gap-3"><Button type="submit" disabled={save.isPending||refresh.isPending||conflict||!!review||(!dirty&&revision>0)}>{t(save.isPending?"athlete.saving":"athlete.save_checkin")}</Button><span role="status">{dirty?<Badge>{t("athlete.unsaved")}</Badge>:revision>0?<Badge tone="positive">{t("settings.saved")}</Badge>:null}</span></div>
      </fieldset>
    </form>
  </details>;
}
