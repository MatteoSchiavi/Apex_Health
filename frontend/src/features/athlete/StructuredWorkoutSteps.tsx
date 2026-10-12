import {useState} from "react";
import {useTranslation} from "react-i18next";
import {Button,Input,Select,fmtDuration} from "../../components/kit";
export type StepKind = "warmup" | "easy" | "endurance" | "tempo" | "threshold" | "interval" | "recovery" | "cooldown" | "strength" | "technical" | "repeat";
export interface WorkoutTarget { kind: "pace_s_km" | "hr_bpm" | "power_w" | "rpe"; lower: number; upper: number }
export interface WorkoutStep { id: string; kind: StepKind; duration_s: number | null; distance_m: number | null; target: WorkoutTarget | null; description: string; exercise: string | null; sets: number | null; reps: number | null; load_kg: number | null; repetitions: number; steps: WorkoutStep[] }
export interface StructuredWorkout { title: string; objective: string; steps: WorkoutStep[] }
const stepKinds: StepKind[] = ["warmup", "easy", "endurance", "tempo", "threshold", "interval", "recovery", "cooldown", "strength", "technical", "repeat"];
export const freshStep = (kind: StepKind = "easy"): WorkoutStep => ({ id: crypto.randomUUID(), kind, duration_s: null, distance_m: null, target: null, description: "", exercise: null, sets: null, reps: null, load_kg: null, repetitions: 1, steps: [] });
const numeric = (value: string) => value === "" ? null : Number(value);
export function stepError(step: WorkoutStep): boolean {
  if (step.kind === "repeat") return !step.steps.length || step.repetitions < 1 || step.repetitions > 50 || !Number.isInteger(step.repetitions) || step.steps.some(child => child.kind === "repeat" || stepError(child));
  if (step.duration_s !== null && (!Number.isInteger(step.duration_s) || step.duration_s <= 0 || step.duration_s > 86400)) return true;
  if (step.distance_m !== null && (step.distance_m <= 0 || step.distance_m > 500000)) return true;
  if (step.target) { const max = { pace_s_km: 3600, hr_bpm: 300, power_w: 4000, rpe: 10 }[step.target.kind]; if (!Number.isFinite(step.target.lower) || !Number.isFinite(step.target.upper) || step.target.lower < 0 || step.target.upper <= 0 || step.target.lower > step.target.upper || step.target.upper > max || (["pace_s_km", "hr_bpm"].includes(step.target.kind) && step.target.lower <= 0)) return true; }
  return (["sets", "reps"] as const).some(key => step[key] !== null && (!Number.isInteger(step[key]) || step[key]! < 1 || step[key]! > 100)) || (step.load_kg !== null && (step.load_kg < 0 || step.load_kg > 1500));
}
function RangeTarget({ value, onChange }: { value: WorkoutTarget | null; onChange: (value: WorkoutTarget | null) => void }) {
  const { t } = useTranslation();
  return <div className="space-y-3"><Select label={t("structuredWorkout.target_kind")} value={value?.kind ?? ""} options={[{ value: "", label: t("structuredWorkout.no_target") }, ...["pace_s_km", "hr_bpm", "power_w", "rpe"].map(kind => ({ value: kind, label: t("structuredWorkout.target_" + kind) }))]} onChange={kind => onChange(kind ? { kind: kind as WorkoutTarget["kind"], lower: NaN, upper: NaN } : null)} />{value && <div className="grid gap-3 sm:grid-cols-2"><Input label={t("structuredWorkout.target_lower")} type="number" min={0} step={0.1} value={Number.isFinite(value.lower) ? value.lower : ""} onChange={v => onChange({ ...value, lower: v === "" ? NaN : Number(v) })} /><Input label={t("structuredWorkout.target_upper")} type="number" min={0} step={0.1} value={Number.isFinite(value.upper) ? value.upper : ""} onChange={v => onChange({ ...value, upper: v === "" ? NaN : Number(v) })} /></div>}</div>;
}
export function StepEditor({ step, index, onChange, onRemove, child = false }: { step: WorkoutStep; index: number; onChange: (value: WorkoutStep) => void; onRemove: () => void; child?: boolean }) {
  const { t } = useTranslation();
  const stop = step.duration_s !== null ? "duration" : step.distance_m !== null ? "distance" : "";
  const [stopChoice, setStopChoice] = useState(stop);
  function edit<K extends keyof WorkoutStep>(key: K, value: WorkoutStep[K]) { onChange({ ...step, [key]: value }); }
  return <fieldset className="min-w-0 space-y-3 border border-hairline p-4"><legend className="px-1 text-[14px] font-medium">{t(child ? "structuredWorkout.child_number" : "structuredWorkout.block_number", { count: index + 1 })}</legend>
    <Select label={t("structuredWorkout.block_kind")} value={step.kind} options={stepKinds.filter(kind => !child || kind !== "repeat").map(kind => ({ value: kind, label: t("structuredWorkout.kind_" + kind) }))} onChange={kind => { const next = { ...step, kind: kind as StepKind }; if (kind === "repeat") { next.duration_s = null; next.distance_m = null; next.target = null; next.steps = [freshStep("interval"), freshStep("recovery")]; next.exercise = null; next.sets = null; next.reps = null; next.load_kg = null; setStopChoice(""); } else { next.steps = []; next.repetitions = 1; if (kind !== "strength") { next.exercise = null; next.sets = null; next.reps = null; next.load_kg = null; } } onChange(next); }} />
    <Input label={t("structuredWorkout.instructions")} value={step.description} onChange={v => edit("description", v)} />
    {step.kind === "repeat" ? <><Input label={t("structuredWorkout.repeat_count")} type="number" min={1} max={50} step={1} value={step.repetitions} onChange={v => edit("repetitions", Number(v))} /><p className="text-[12px] text-muted">{t("structuredWorkout.repeat_note")}</p><div className="space-y-3">{step.steps.map((item, i) => <StepEditor key={item.id} step={item} index={i} child onChange={value => edit("steps", step.steps.map(old => old.id === item.id ? value : old))} onRemove={() => edit("steps", step.steps.filter(old => old.id !== item.id))} />)}</div><Button variant="ghost" onClick={() => edit("steps", [...step.steps, freshStep()])}>{t("structuredWorkout.add_child")}</Button></> : <>
      <Select label={t("structuredWorkout.stop_condition")} value={stopChoice} options={[{ value: "", label: t("structuredWorkout.unspecified") }, { value: "duration", label: t("structuredWorkout.duration_seconds") }, { value: "distance", label: t("structuredWorkout.distance_metres") }]} onChange={v => { setStopChoice(v); onChange({ ...step, duration_s: null, distance_m: null }); }} />
      {stopChoice === "duration" && <Input label={t("structuredWorkout.duration_seconds")} type="number" min={1} max={86400} step={1} value={step.duration_s ?? ""} onChange={v => edit("duration_s", numeric(v))} />}
      {stopChoice === "distance" && <Input label={t("structuredWorkout.distance_metres")} type="number" min={0.1} max={500000} value={step.distance_m ?? ""} onChange={v => edit("distance_m", numeric(v))} />}
      <RangeTarget value={step.target} onChange={v => edit("target", v)} />
      {step.kind === "strength" && <div className="grid gap-3 sm:grid-cols-2"><Input label={t("structuredWorkout.exercise")} value={step.exercise ?? ""} onChange={v => edit("exercise", v || null)} />{(["sets", "reps", "load_kg"] as const).map(key => <Input key={key} label={t("structuredWorkout." + key)} type="number" min={key === "load_kg" ? 0 : 1} max={key === "load_kg" ? 1500 : 100} step={key === "load_kg" ? 0.1 : 1} value={step[key] ?? ""} onChange={v => edit(key, numeric(v))} />)}</div>}
    </>}
    {stepError(step) && <p role="alert" className="text-[13px] text-alertText">{t("structuredWorkout.invalid_block")}</p>}<Button variant="ghost" onClick={onRemove}>{t("structuredWorkout.remove_block")}</Button>
  </fieldset>;
}

export function StepSummary({ step, number }: { step: WorkoutStep; number: string }) {
  const { t } = useTranslation();
  return <li className="space-y-2 border-t border-hairline pt-3 text-[13px]"><h4 className="font-medium">{number}. {t("structuredWorkout.kind_" + step.kind)}{step.kind === "repeat" && ` · ${step.repetitions} ×`}</h4><p>{step.description}</p>{step.kind === "repeat" ? <ol className="ml-3 space-y-3 border-l border-hairline pl-3">{step.steps.map((child, index) => <StepSummary key={child.id} step={child} number={`${number}.${index + 1}`} />)}</ol> : <><p>{step.duration_s !== null ? fmtDuration(step.duration_s) : step.distance_m !== null ? `${step.distance_m} m` : t("structuredWorkout.unspecified_stop")}</p><p>{step.target ? `${t("structuredWorkout.target_" + step.target.kind)}: ${step.target.lower}–${step.target.upper}` : t("structuredWorkout.no_target")}</p>{step.kind === "strength" && <p>{step.exercise} · {t("structuredWorkout.strength_summary", { sets: step.sets ?? "—", reps: step.reps ?? "—", load: step.load_kg ?? "—" })}</p>}</>}</li>;
}
