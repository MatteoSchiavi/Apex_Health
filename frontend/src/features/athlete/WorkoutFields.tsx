import {StepEditor,freshStep} from "./StructuredWorkoutSteps";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Button, Input, Select, friendlyDiscipline } from "../../components/kit";
import type { WorkoutFieldsValue } from "./importTypes";

export function WorkoutFields({ value, onChange }: { value: WorkoutFieldsValue; onChange: (next: WorkoutFieldsValue) => void }) {
  const { t } = useTranslation();
  const disciplines = useQuery({ queryKey: ["athlete-disciplines"], queryFn: () => api.get<{name: string}[]>("/athlete/disciplines") });
  const options = [{ value: "", label: t("athlete.choose_sport") }, ...(disciplines.data ?? []).map(d => ({ value: d.name, label: friendlyDiscipline(d.name, t) }))];
  if (value.discipline && !options.some(d => d.value === value.discipline)) options.push({ value: value.discipline, label: friendlyDiscipline(value.discipline, t) });
  function edit<K extends keyof WorkoutFieldsValue>(key: K, v: WorkoutFieldsValue[K]) { onChange({ ...value, [key]: v }); }
  return <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-2">
    <Select label={t("athlete.sport")} value={value.discipline} options={options} onChange={v => edit("discipline", v)} />
    <Input label={t("athlete.session_type")} value={value.session_type ?? ""} onChange={v => edit("session_type", v || null)} />
    <Input label={t("athlete.start_time")} type="time" value={value.start_time?.slice(0, 5) ?? ""} onChange={v => edit("start_time", v || null)} />
    <Input label={t("athlete.workout_minutes")} type="number" min={0} max={1440} value={String(value.duration_min ?? "")} onChange={v => edit("duration_min", v === "" ? null : Number(v))} />
    <Input label={t("athlete.workout_distance")} type="number" min={0} max={5000000} value={String(value.distance_m ?? "")} onChange={v => edit("distance_m", v === "" ? null : Number(v))} />
  </div><Input label={t("athlete.workout_description")} value={value.description} onChange={v => edit("description", v)} />
    <details><summary className="cursor-pointer text-[13px]">{t("athleteImport.optional_targets")}</summary><p className="my-3 text-[12px] text-muted">{t("athleteImport.targets_note")}</p><div className="grid gap-3 sm:grid-cols-2">{["hr_bpm", "power_w", "pace_s_km", "rpe"].map(key => <Input key={key} label={t("athlete.intensity_" + key)} value={value.intensity_targets[key] ?? ""} onChange={v => { const targets = { ...value.intensity_targets }; if (v) targets[key] = v; else delete targets[key]; edit("intensity_targets", targets); }} />)}</div></details>
    <details open={!!value.steps?.length || undefined}><summary className="cursor-pointer text-[13px]">{t("structuredWorkout.instructions_title")}</summary><div className="mt-3 space-y-3">{value.steps?.map((step,index)=><StepEditor key={step.id} step={step} index={index} onChange={next=>edit("steps",value.steps!.map(old=>old.id===step.id?next:old))} onRemove={()=>edit("steps",value.steps!.filter(old=>old.id!==step.id))}/>)}<Button variant="ghost" onClick={()=>edit("steps",[...(value.steps??[]),freshStep()])}>{t("structuredWorkout.add_block")}</Button><p className="text-[12px] text-muted">{t("structuredWorkout.target_note")}</p></div></details>
    <label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={value.protected} onChange={e => edit("protected", e.target.checked)} />{t("athlete.protect_workout")}</label>
  </div>;
}
