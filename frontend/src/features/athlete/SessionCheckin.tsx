import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { Badge, Button, Input, Select } from "../../components/kit";
import type { Checkin } from "./types";

type Form = {status:string;rpe:string;pain:string;unwell:string;note:string;fatigue:string;soreness:string;workout_quality:string;modification_reason:string;terrain_notes:string};
const formOf=(c?:Checkin|null):Form=>({status:c?.status??"completed",rpe:String(c?.rpe??""),pain:c?.pain==null?"":c.pain?"yes":"no",unwell:c?.felt_unwell==null?"":c.felt_unwell?"yes":"no",note:c?.note??"",fatigue:String(c?.fatigue??""),soreness:String(c?.soreness??""),workout_quality:String(c?.workout_quality??""),modification_reason:c?.modification_reason??"",terrain_notes:c?.terrain_notes??""});
export function SessionCheckin({ activityId, plannedSessionId, checkin }: { activityId?: number; plannedSessionId?: number; checkin?: Checkin | null }) {
  const { t } = useTranslation();
  const qc=useQueryClient();
  const [form,setForm]=useState(()=>formOf(checkin));
  const [saved,setSaved]=useState(()=>JSON.stringify(formOf(checkin)));
  const [revision,setRevision]=useState(checkin?.revision??0);
  const dirty=JSON.stringify(form)!==saved;
  const dirtyRef=useRef(dirty);dirtyRef.current=dirty;
  useEffect(()=>{if(!dirtyRef.current){const next=formOf(checkin);setForm(next);setSaved(JSON.stringify(next));setRevision(checkin?.revision??0);}},[checkin?.revision,activityId,plannedSessionId]);
  const set=(key:keyof Form,value:string)=>setForm(f=>({...f,[key]:value}));
  const number=(value:string)=>value===""?null:Number(value);
  const save=useMutation({mutationFn:(submitted:Form)=>api.put<Checkin>("/athlete/checkins",{
    activity_id:activityId,planned_session_id:plannedSessionId,expected_revision:revision,status:submitted.status,
    rpe:submitted.status==="skipped"?null:number(submitted.rpe),pain:submitted.pain===""?null:submitted.pain==="yes",felt_unwell:submitted.unwell===""?null:submitted.unwell==="yes",
    fatigue:number(submitted.fatigue),soreness:number(submitted.soreness),workout_quality:submitted.status==="skipped"?null:number(submitted.workout_quality),
    note:submitted.note,modification_reason:submitted.modification_reason,terrain_notes:submitted.terrain_notes,
  }),onSuccess:receipt=>{const next=formOf(receipt);setForm(next);setSaved(JSON.stringify(next));setRevision(receipt.revision);for(const key of ["athlete-day","endurance","lab","sport-overview"])qc.invalidateQueries({queryKey:[key]});}});
  const choices=[{value:"",label:t("design.not_specified")},{value:"yes",label:t("athlete.yes")},{value:"no",label:t("athlete.no")}];
  return <details className="mt-3 border-t border-hairline pt-3 text-[13px]">
    <summary className="cursor-pointer text-ink2">{t("athlete.checkin_title")}</summary>
    <form className="mt-4 space-y-3" onSubmit={e=>{e.preventDefault();save.mutate(form);}}>
      <fieldset disabled={save.isPending} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2"><Select label={t("athlete.session_status")} value={form.status} onChange={value=>set("status",value)} options={(activityId?["completed","partial"]:["completed","partial","skipped"]).map(value=>({value,label:t("athlete.state_"+value)}))}/>
          {(["rpe","fatigue","soreness","workout_quality"] as const).filter(key=>form.status!=="skipped"||(key!=="rpe"&&key!=="workout_quality")).map(key=><Input key={key} label={t("athlete."+key)} type="number" min={0} max={10} step={1} value={form[key]} onChange={value=>set(key,value)}/>)}
          <Select label={t("athlete.pain")} value={form.pain} onChange={value=>set("pain",value)} options={choices}/><Select label={t("athlete.felt_unwell")} value={form.unwell} onChange={value=>set("unwell",value)} options={choices}/>
        </div>
        {(["note","modification_reason","terrain_notes"] as const).map(key=><Input key={key} label={t(key==="note"?"athlete.checkin_note":"athlete."+key)} value={form[key]} maxLength={key==="note"?2000:1000} onChange={value=>set(key,value)}/>)}
        <p className="text-[12px] text-muted">{t("athlete.checkin_limits")}</p>
        {save.isError&&<p role="alert" className="text-alertText">{t(save.error instanceof ApiError&&save.error.status===409?"athlete.conflict":"athlete.save_error")}</p>}
        <div className="flex items-center gap-3"><Button type="submit" disabled={save.isPending||(!dirty&&revision>0)}>{t(save.isPending?"athlete.saving":"athlete.save_checkin")}</Button><span role="status">{dirty?<Badge>{t("athlete.unsaved")}</Badge>:revision>0?<Badge tone="positive">{t("settings.saved")}</Badge>:null}</span></div>
      </fieldset>
    </form>
  </details>;
}
