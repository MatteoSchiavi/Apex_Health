import {FocusAllocationEditor} from "./FocusAllocationEditor";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Select } from "../../components/kit";
import { AvailabilityEditor, type AvailabilityEntry } from "./AvailabilityEditor";
import type { AthleteContext, Focus, SportContext } from "./types";
import type { ImportProposal } from "./importTypes";

export function ImportEvidence({ field, proposal, onResolve }: { field: string; proposal: ImportProposal; onResolve: (field: string, defer: boolean) => void }) {
  const { t } = useTranslation();
  const matches = (candidate: string) => {
    if (field === "weekly" || field === "dated") return candidate === field || (candidate.startsWith(field + ".") && !/^(weekly\.rows|dated\.sessions)\.\d+(\.|$)/.test(candidate));
    return candidate === field || candidate.startsWith(field + ".");
  };
  const sources = proposal.sources.filter(source => matches(source.field.replace(/^profile\./, "")));
  const issues = proposal.issues.filter(issue => { const key = issue.field.replace(/^profile\./, ""); return matches(key); });
  return <div className="space-y-2 text-[12px]">{sources.map((source, index) => <div key={index} className="border-l-2 border-hairline pl-3"><p className="text-muted">{t("athleteImport.certainty_" + source.certainty)}</p><blockquote className="break-words">“{source.quote}”</blockquote></div>)}{issues.map((issue, index) => <div key={index} className="border-l-2 border-warning pl-3"><p>{issue.question}</p><p className="mt-1 text-muted">{t(issue.required ? "athleteImport.required_question" : "athleteImport.optional_question")}</p><div className="mt-2 flex flex-wrap gap-2"><Button variant="ghost" onClick={() => onResolve(issue.field, false)}>{t("athleteImport.use_correction")}</Button>{!issue.required && <Button variant="ghost" onClick={() => onResolve(issue.field, true)}>{t("athleteImport.defer")}</Button>}</div></div>)}</div>;
}

const textFields: { section: string; fields: [keyof AthleteContext, string][] }[] = [
  { section: "athlete.section_about", fields: [["athlete_notes", "athlete.open_context"], ["self_declared_restrictions", "athlete.restrictions"], ["recent_consistency", "athlete.recent_consistency"]] },
  { section: "athlete.section_goals", fields: [["main_goal", "athlete.main_goal"], ["event_history", "athlete.event_history"]] },
  { section: "athleteImport.season", fields: [["sleep_work_schedule", "athlete.sleep_work_schedule"], ["schedule_constraints", "athlete.schedule_constraints"], ["gym_split", "athlete.gym_split"], ["preferred_exercises", "athlete.preferred_exercises"], ["devices", "athlete.devices"], ["coaching_style", "athlete.coaching_style"]] },
];
export function ImportProfileReview({ proposal, onChange, selected, onSelected, entry, onEntry, revision }: {
  proposal: ImportProposal; onChange: (next: ImportProposal) => void; selected: string[]; onSelected: (next: string[]) => void;
  entry: AvailabilityEntry; onEntry: (next: AvailabilityEntry) => void; revision: number;
}) {
  const { t, i18n } = useTranslation();
  const context = proposal.profile.context;
  const focuses = proposal.profile.training_focus ?? [];
  const sportFocuses = [...new Set([...focuses, ...Object.keys(context.focuses ?? {}) as Focus[]])];
  const days = Array.from({ length: 7 }, (_, day) => ({ value: String(day), label: new Intl.DateTimeFormat(i18n.language, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + day))) }));
  const unknown = { value: "", label: t("design.not_specified") };
  function edit(key: keyof AthleteContext, value: unknown) {
    onChange({ ...proposal, profile: { ...proposal.profile, context: { ...context, [key]: value } } });
    if (!selected.includes("context." + key)) onSelected([...selected, "context." + key]);
  }
  function resolve(field: string, defer: boolean) {
    const normalized = field.replace(/^profile\./, "");
    if (defer) onSelected(selected.filter(key => normalized !== key && !normalized.startsWith(key + ".")));
    onChange({ ...proposal, issues: proposal.issues.filter(issue => issue.field !== field) });
  }
  function fact(field: string, title: string, children: ReactNode) {
    return <fieldset key={field} className="space-y-3 border border-hairline p-4"><legend className="px-1 text-[14px] font-medium">{title}</legend>
      <label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={selected.includes(field)} onChange={e => onSelected(e.target.checked ? [...selected, field] : selected.filter(key => key !== field))} />{t("athleteImport.save_field", { field: title })}</label>
      {children}<ImportEvidence field={field} proposal={proposal} onResolve={resolve} /><p className="text-[12px] text-muted">{t(selected.includes(field) ? "athleteImport.included" : "athleteImport.discarded")}</p>
    </fieldset>;
  }
  function sportEdit(focus: Focus, key: keyof SportContext, value: unknown) { edit("focuses", { ...context.focuses, [focus]: { ...context.focuses?.[focus], [key]: value } }); }
  return <div className="space-y-6">
    <section className="space-y-3"><h3 className="text-[16px] font-medium">{t("athlete.section_focus")}</h3>{fact("training_focus", t("athlete.section_focus"), <><div className="flex flex-wrap gap-4">{(["gym", "running", "cycling"] as Focus[]).map(focus => <label key={focus} className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={focuses.includes(focus)} onChange={e => { const next = e.target.checked ? [...focuses, focus] : focuses.filter(f => f !== focus); const sports = { ...context.focuses }; if (!e.target.checked) delete sports[focus]; onChange({ ...proposal, profile: { training_focus: next, context: { ...context, focuses: sports } } }); if (!selected.includes("training_focus")) onSelected([...selected, "training_focus"]); }} />{t("athlete.focus_" + focus)}</label>)}</div><ol className="space-y-2">{focuses.map((focus, index) => <li key={focus} className="flex items-center gap-3 text-[13px]"><span>{index + 1}. {t("athlete.focus_" + focus)}</span>{index > 0 && <Button variant="ghost" onClick={() => { const next = [...focuses]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange({ ...proposal, profile: { ...proposal.profile, training_focus: next } }); }}>{t("athlete.move_up")}</Button>}</li>)}</ol></>)}</section>
    {textFields.slice(0, 2).map(section => <section key={section.section} className="space-y-3"><h3 className="text-[16px] font-medium">{t(section.section)}</h3>{section.fields.map(([key, label], index) => index > 0 ? <details key={key} open={Object.hasOwn(context, key)}><summary className="cursor-pointer text-[13px]">{t(label)}</summary><div className="mt-3">{fact("context." + key, t(label), <Input label={t(label)} value={String(context[key] ?? "")} onChange={v => edit(key, v)} />)}</div></details> : fact("context." + key, t(label), <label className="flex flex-col gap-2 text-[13px]"><span>{t(label)}</span><textarea aria-label={t(label)} className="min-h-24 w-full border border-hairline bg-transparent px-3 py-2" maxLength={key === "athlete_notes" ? 8000 : key === "main_goal" || key === "recent_consistency" ? 1000 : 2000} value={String(context[key] ?? "")} onChange={e => edit(key, e.target.value)} /></label>))}</section>)}
    <section className="space-y-3"><h3 className="text-[16px] font-medium">{t("athlete.availability")}</h3>
      {fact("context.weekly_time_budget_min", t("athlete.weekly_hours"), <Input label={t("athlete.weekly_hours")} type="number" min={0} max={168} step={0.25} value={context.weekly_time_budget_min == null ? "" : String(context.weekly_time_budget_min / 60)} onChange={v => edit("weekly_time_budget_min", v === "" ? null : Math.round(Number(v) * 60))} />)}
      {fact("context.preferred_rest_day", t("athlete.rest_day"), <Select label={t("athlete.rest_day")} value={String(context.preferred_rest_day ?? "")} options={[unknown, ...days]} onChange={v => edit("preferred_rest_day", v === "" ? null : Number(v))} />)}
      {fact("context.availability", t("athlete.weekly_schedule"), <AvailabilityEditor value={context.availability ?? []} onChange={v => edit("availability", v)} entry={entry} onEntryChange={onEntry} revision={revision} />)}
    </section>
    {!!sportFocuses.length && <section className="space-y-3"><h3 className="text-[16px] font-medium">{t("athleteImport.sport_goals")}</h3>{fact("context.focuses", t("athleteImport.sport_goals"), <div className="space-y-4">{sportFocuses.map(focus => { const sport = context.focuses?.[focus] ?? {}; return <details key={focus} open={!!context.focuses?.[focus]}><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.focus_" + focus)}</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">
      <Select label={t("athlete.level")} value={sport.level ?? ""} options={[unknown, ...["new", "beginner", "intermediate", "experienced"].map(value => ({ value, label: t("athlete.level_" + value) }))]} onChange={v => sportEdit(focus, "level", v || null)} />
      <Select label={t("athlete.goal_type")} value={sport.goal ?? ""} options={[unknown, ...["maintain", "health", "body_composition", "performance", "event"].map(value => ({ value, label: t("athlete.goal_" + value) }))]} onChange={v => sportEdit(focus, "goal", v || null)} />
      {(["weekly_frequency", "weekly_duration_min", "weekly_distance_km", "longest_distance_km"] as const).map(key => <Input key={key} label={t("athlete." + ({ weekly_duration_min: "weekly_minutes", weekly_distance_km: "weekly_distance", longest_distance_km: "longest_distance" }[key as string] ?? key))} type="number" min={0} max={key === "weekly_frequency" ? 21 : key === "weekly_duration_min" ? 10080 : 5000} value={String(sport[key] ?? "")} onChange={v => sportEdit(focus, key, v === "" ? null : Number(v))} />)}
      <Input label={t("athlete.equipment")} value={(sport.equipment ?? []).join(", ")} onChange={v => sportEdit(focus, "equipment", v.split(",").map(s => s.trim()).filter(Boolean))} /><Input label={t("athlete.plan_constraints")} value={sport.constraints ?? ""} onChange={v => sportEdit(focus, "constraints", v)} />
      <Input label={t("athlete.target_event")} value={sport.event?.title ?? ""} onChange={v => sportEdit(focus, "event", { ...sport.event, title: v, priority: sport.event?.priority ?? 2 })} /><Input label={t("athlete.event_date")} type="date" value={sport.event?.date ?? ""} onChange={v => sportEdit(focus, "event", { title: sport.event?.title ?? "", priority: sport.event?.priority ?? 2, ...sport.event, date: v || null })} />
      <Input label={t("athlete.event_distance")} type="number" min={0.01} max={5000} value={String(sport.event?.distance_km ?? "")} onChange={v => sportEdit(focus, "event", { title: sport.event?.title ?? "", priority: sport.event?.priority ?? 2, ...sport.event, distance_km: v === "" ? null : Number(v) })} />
      <Select label={t("athlete.event_priority")} value={String(sport.event?.priority ?? 2)} options={[1, 2, 3].map(value => ({ value: String(value), label: t("athlete.priority_" + value) }))} onChange={v => sportEdit(focus, "event", { title: sport.event?.title ?? "", ...sport.event, priority: Number(v) })} />
    </div></details>; })}</div>)}</section>}
    {(["focus_mode","supporting_focus","weekly_allocation_min","seasonal_focus"] as const).some(key=>Object.hasOwn(context,key)) && <section className="space-y-4"><h3 className="text-[16px] font-medium">{t("athlete.focus_configuration")}</h3>{(["focus_mode","supporting_focus","weekly_allocation_min","seasonal_focus"] as const).filter(key=>Object.hasOwn(context,key)).map(key=>fact("context."+key,t(key==="seasonal_focus"?"athlete.seasonal_priorities":key==="focus_mode"?"athlete.focus_mode":key==="supporting_focus"?"athlete.supporting_disciplines":"athlete.weekly_allocation"),<p className="text-[12px] text-muted">{t("athleteImport.included")}</p>))}<FocusAllocationEditor expanded focuses={focuses} context={context} onChange={patch=>{onChange({...proposal,profile:{...proposal.profile,context:{...context,...patch}}});onSelected([...new Set([...selected,...Object.keys(patch).map(key=>"context."+key)])]);}}/></section>}
    <details open={textFields[2].fields.some(([key]) => Object.hasOwn(context, key)) || ["existing_plan", "gym_experience_years", "rpe_preference"].some(key => Object.hasOwn(context, key))}><summary className="cursor-pointer text-[16px] font-medium">{t("athleteImport.season")}</summary><div className="mt-3 space-y-3">{textFields[2].fields.map(([key, label]) => fact("context." + key, t(label), <Input label={t(label)} value={String(context[key] ?? "")} onChange={v => edit(key, v)} />))}
      {fact("context.existing_plan", t("athlete.existing_plan"), <Select label={t("athlete.existing_plan")} value={context.existing_plan ?? ""} options={[unknown, ...["yes", "no", "unsure"].map(value => ({ value, label: t("athlete." + value) }))]} onChange={v => edit("existing_plan", v || null)} />)}
      {fact("context.gym_experience_years", t("athlete.gym_years"), <Input label={t("athlete.gym_years")} type="number" min={0} max={100} value={String(context.gym_experience_years ?? "")} onChange={v => edit("gym_experience_years", v === "" ? null : Number(v))} />)}
      {fact("context.rpe_preference", t("athlete.rpe_preference"), <Select label={t("athlete.rpe_preference")} value={context.rpe_preference == null ? "" : context.rpe_preference ? "yes" : "no"} options={[unknown, ...["yes", "no"].map(value => ({ value, label: t("athlete." + value) }))]} onChange={v => edit("rpe_preference", v === "" ? null : v === "yes")} />)}
    </div></details>
  </div>;
}
