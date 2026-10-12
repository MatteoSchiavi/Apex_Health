import { useTranslation } from "react-i18next";
import { Input, Select } from "../../components/kit";
import type { Focus, MeasurableGoal } from "./types";

export function goalInvalid(goal?: MeasurableGoal) {
  return !!goal && (!Number.isFinite(goal.target) || goal.target <= 0 || goal.target > 100000 ||
    (goal.metric === "best_power_w" && (!Number.isInteger(goal.duration_s) || goal.duration_s! < 1 || goal.duration_s! > 3600)) ||
    (goal.metric === "exercise_estimated_1rm_kg" && !goal.exercise?.trim()));
}

export function MeasurableGoalEditor({ focus, value, onChange }: { focus: Focus; value?: MeasurableGoal; onChange: (goal?: MeasurableGoal) => void }) {
  const { i18n } = useTranslation();
  const it = i18n.resolvedLanguage?.startsWith("it");
  const labels: Record<MeasurableGoal["metric"], string> = {
    weekly_distance_km: it ? "Distanza settimanale (km)" : "Weekly distance (km)",
    weekly_duration_min: it ? "Durata settimanale (min)" : "Weekly duration (min)",
    longest_distance_km: it ? "Distanza della sessione più lunga (km)" : "Longest session distance (km)",
    best_power_w: it ? "Potenza media su durata specifica (W)" : "Mean power over a specified duration (W)",
    exercise_estimated_1rm_kg: it ? "Massimale stimato per esercizio (kg)" : "Estimated exercise one-rep maximum (kg)",
  };
  const allowed: MeasurableGoal["metric"][] = focus === "gym" ? ["weekly_duration_min", "exercise_estimated_1rm_kg"] : ["weekly_distance_km", "weekly_duration_min", "longest_distance_km", ...(focus === "cycling" ? ["best_power_w" as const] : [])];
  return <fieldset className="space-y-3 border-t border-hairline pt-4">
    <legend className="text-[14px] font-medium">{it ? "Obiettivo misurabile facoltativo" : "Optional measurable goal"}</legend>
    <p className="text-[12px] text-muted">{it ? "Confronta dati compatibili con un obiettivo scelto da te. Non modifica il piano o il carico prescritto." : "Compare compatible recordings with a target you choose. This does not change your plan or prescribed load."}</p>
    <Select label={it ? "Misura dell’obiettivo" : "Goal measurement"} value={value?.metric ?? ""} options={[{value:"",label:it ? "Nessun obiettivo misurabile" : "No measurable goal"}, ...allowed.map(metric=>({value:metric,label:labels[metric]}))]} onChange={metric=>onChange(metric ? {metric:metric as MeasurableGoal["metric"],target:0,...(metric === "best_power_w" ? {duration_s:300} : {}),...(metric === "exercise_estimated_1rm_kg" ? {exercise:""} : {})} : undefined)} />
    {value && <><Input label={it ? "Valore dell’obiettivo" : "Target value"} type="number" min={0.01} max={100000} step={0.01} value={value.target > 0 ? String(value.target) : ""} onChange={v=>onChange({...value,target:Number(v)})} />
      {value.metric === "best_power_w" && <Input label={it ? "Durata della potenza (secondi)" : "Power duration (seconds)"} type="number" min={1} max={3600} value={String(value.duration_s ?? "")} onChange={v=>onChange({...value,duration_s:Number(v)})} />}
      {value.metric === "exercise_estimated_1rm_kg" && <Input label={it ? "Nome esatto dell’esercizio registrato" : "Exact recorded exercise name"} value={value.exercise ?? ""} onChange={exercise=>onChange({...value,exercise})} />}
      {goalInvalid(value) && <p className="text-[12px] text-muted" role="status">{it ? "Completa un valore positivo e il riferimento richiesto prima di salvare." : "Enter a positive target and the required reference before saving."}</p>}
    </>}
  </fieldset>;
}
