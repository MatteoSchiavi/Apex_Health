import {StepSummary} from "./StructuredWorkoutSteps";
import { useTranslation } from "react-i18next";
import { Button, Input, Select, friendlyDiscipline } from "../../components/kit";
import { WorkoutFields } from "./WorkoutFields";
import { removeImportRow } from "./importReviewHelpers";
import { ImportEvidence } from "./ImportProfileReview";
import { emptyWorkout, type ImportProposal, type PlanDraft } from "./importTypes";

export function ImportPlanReview({ proposal, onChange }: { proposal: ImportProposal; onChange: (value: ImportProposal) => void }) {
  const { t, i18n } = useTranslation();
  const days = Array.from({ length: 7 }, (_, day) => ({ value: String(day), label: new Intl.DateTimeFormat(i18n.language, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + day))) }));
  function resolve(field: string, defer: boolean) {
    let next = { ...proposal, issues: proposal.issues.filter(issue => issue.field !== field) };
    if (defer) {
      const weeklyIndex = field.match(/^weekly\.rows\.(\d+)/);
      const datedIndex = field.match(/^dated\.sessions\.(\d+)/);
      if (weeklyIndex && next.weekly) next = removeImportRow(next, "weekly", Number(weeklyIndex[1]));
      else if (datedIndex && next.dated) next = removeImportRow(next, "dated", Number(datedIndex[1]));
      else if (field.startsWith("weekly")) next = { ...next, weekly: null };
      else if (field.startsWith("dated")) next = { ...next, dated: null };
    }
    onChange(next);
  }
  return <div className="space-y-6"><p className="text-[13px] text-muted">{t("athleteImport.plan_optional_note")}</p>
    <section aria-label={t("athleteImport.weekly_template")} className="space-y-4"><h3 className="text-[16px] font-medium">{t("athleteImport.weekly_template")}</h3>
      {!proposal.weekly ? <Button variant="ghost" onClick={() => onChange({ ...proposal, weekly: { title: "", rows: [{ ...emptyWorkout(), id: crypto.randomUUID(), day: 0 }], notes: "" } })}>{t("athleteImport.add_template")}</Button> : <>
        <Input label={t("athlete.plan_title")} value={proposal.weekly.title} onChange={title => onChange({ ...proposal, weekly: { ...proposal.weekly!, title } })} />
        <p className="text-[12px] text-muted">{t("athleteImport.weekly_note")}</p>
        {proposal.weekly.rows.map((row, index) => <fieldset key={row.id} className="space-y-3 border border-hairline p-4"><legend className="px-1 text-[14px] font-medium">{days[row.day]?.label} · {index + 1}</legend>
          <Select label={t("athleteImport.weekday")} value={String(row.day)} options={days} onChange={day => onChange({ ...proposal, weekly: { ...proposal.weekly!, rows: proposal.weekly!.rows.map(old => old.id === row.id ? { ...old, day: Number(day) } : old) } })} />
          <WorkoutFields value={row} onChange={value => onChange({ ...proposal, weekly: { ...proposal.weekly!, rows: proposal.weekly!.rows.map(old => old.id === row.id ? { ...old, ...value } : old) } })} />
          <ImportEvidence field={`weekly.rows.${index}`} proposal={proposal} onResolve={resolve} />
          <Button variant="ghost" onClick={() => onChange(removeImportRow(proposal, "weekly", index))}>{t("athlete.remove_workout")}</Button>
        </fieldset>)}
        <Input label={t("lab.notes")} value={proposal.weekly.notes} onChange={notes => onChange({ ...proposal, weekly: { ...proposal.weekly!, notes } })} />
        <Button variant="ghost" onClick={() => onChange({ ...proposal, weekly: { ...proposal.weekly!, rows: [...proposal.weekly!.rows, { ...emptyWorkout(), id: crypto.randomUUID(), day: 0 }] } })}>{t("athleteImport.add_weekly_workout")}</Button>
        <Button variant="ghost" onClick={() => onChange({ ...proposal, weekly: null, issues: proposal.issues.filter(issue => !issue.field.startsWith("weekly")) })}>{t("athleteImport.discard_template")}</Button>
        <ImportEvidence field="weekly" proposal={proposal} onResolve={resolve} />
      </>}
    </section>
    <details open={!!proposal.dated}><summary className="cursor-pointer text-[16px] font-medium">{t("athleteImport.dated_workouts")}</summary><div className="mt-4 space-y-4">
      {!proposal.dated ? <Button variant="ghost" onClick={() => onChange({ ...proposal, dated: { title: "", starts_on: null, ends_on: null, weekly_structure: "", sessions: [], ambiguities: [], protected: false } })}>{t("athleteImport.add_dated")}</Button> : <>
        <Input label={t("athlete.plan_title")} value={proposal.dated.title} onChange={title => onChange({ ...proposal, dated: { ...proposal.dated!, title } })} />
        <div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_start")} type="date" value={proposal.dated.starts_on ?? ""} onChange={v => onChange({ ...proposal, dated: { ...proposal.dated!, starts_on: v || null } })} /><Input label={t("athlete.event_end")} type="date" value={proposal.dated.ends_on ?? ""} onChange={v => onChange({ ...proposal, dated: { ...proposal.dated!, ends_on: v || null } })} /></div>
        {proposal.dated.sessions.map((row, index) => <fieldset key={index} className="space-y-3 border border-hairline p-4"><legend className="px-1 text-[14px]">{t("athleteImport.workout_number", { count: index + 1 })}</legend><Input label={t("athlete.event_date")} type="date" value={row.date ?? ""} onChange={date => onChange({ ...proposal, dated: { ...proposal.dated!, sessions: proposal.dated!.sessions.map((old, i) => i === index ? { ...old, date: date || null } : old) } })} />
          <WorkoutFields value={row} onChange={value => onChange({ ...proposal, dated: { ...proposal.dated!, sessions: proposal.dated!.sessions.map((old, i) => i === index ? { ...old, ...value } : old) } })} />
          <ImportEvidence field={`dated.sessions.${index}`} proposal={proposal} onResolve={resolve} />
          <Button variant="ghost" onClick={() => onChange(removeImportRow(proposal, "dated", index))}>{t("athlete.remove_workout")}</Button></fieldset>)}
        <Button variant="ghost" onClick={() => onChange({ ...proposal, dated: { ...proposal.dated!, sessions: [...proposal.dated!.sessions, { ...emptyWorkout(), date: null }] } })}>{t("athlete.add_workout")}</Button>
        <label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={proposal.dated.protected} onChange={e => onChange({ ...proposal, dated: { ...proposal.dated!, protected: e.target.checked } })} />{t("athlete.protect_plan")}</label>
        <ImportEvidence field="dated" proposal={proposal} onResolve={resolve} />
        {!!proposal.dated.ambiguities.length && <div className="space-y-3">{proposal.dated.ambiguities.map((question, index) => <div key={index} className="border-l-2 border-warning pl-3"><p className="text-[13px]">{question}</p><Button variant="ghost" onClick={() => onChange({ ...proposal, dated: { ...proposal.dated!, ambiguities: proposal.dated!.ambiguities.filter((_, i) => i !== index) } })}>{t("athleteImport.use_correction")}</Button></div>)}</div>}
        <Button variant="ghost" onClick={() => onChange({ ...proposal, dated: null, issues: proposal.issues.filter(issue => !issue.field.startsWith("dated")) })}>{t("athleteImport.discard_dated")}</Button>
      </>}
    </div></details>
  </div>;
}

export function CalendarPreview({ draft, pending, error, onActivate }: { draft: PlanDraft; pending: boolean; error: string | null; onActivate: () => void }) {
  const { t, i18n } = useTranslation();
  const sessions = [...draft.structure.sessions].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? "") || (a.start_time ?? "").localeCompare(b.start_time ?? ""));
  const complete = !!draft.structure.starts_on && !!draft.structure.ends_on && sessions.length > 0 && sessions.every(session => !!session.date && !!session.discipline) && !draft.structure.ambiguities.length;
  const dateLabel = (day: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: "full", timeZone: "UTC" }).format(new Date(day + "T12:00:00Z"));
  return <section aria-label={t("athleteImport.calendar_preview")} className="space-y-4 border border-hairline p-4"><h3 className="text-[16px] font-medium">{t("athleteImport.calendar_preview")}</h3><p className="text-[13px]">{draft.structure.title} · {draft.structure.starts_on} – {draft.structure.ends_on}</p><p className="text-[12px] text-muted">{t("athleteImport.preview_note", { count: sessions.length })}</p>
    <ol className="space-y-3">{sessions.map((session, index) => <li key={index} className="border-t border-hairline pt-3 text-[13px]"><p className="font-medium">{session.date ? dateLabel(session.date) : t("athlete.event_date")} · {friendlyDiscipline(session.discipline, t)} {session.start_time?.slice(0, 5)}</p><p>{session.session_type} · {session.duration_min == null ? t("athlete.duration_unknown") : t("athlete.duration_minutes", { count: session.duration_min })} · {session.distance_m == null ? t("athlete.distance_unknown") : t("athlete.distance_metres", { count: session.distance_m })}</p><p>{session.description}</p>{!!session.steps?.length && <ol className="mt-3 space-y-3">{session.steps.map((step,i)=><StepSummary key={step.id} step={step} number={String(i+1)}/>)}</ol>}<p>{Object.entries(session.intensity_targets).map(([key, value]) => `${t("athlete.intensity_" + key)}: ${value}`).join(" · ")}</p>{(session.protected || draft.structure.protected) && <p>{t("athlete.protected")}</p>}</li>)}</ol>
    {!complete && <p role="alert" className="text-[13px]">{t("athleteImport.complete_dates")}</p>}
    {!!draft.structure.ambiguities.length && <ul className="text-[13px]">{draft.structure.ambiguities.map((question, index) => <li key={index}>{question}</li>)}</ul>}
    {draft.status === "confirmed" ? <p role="status" className="text-[14px] font-medium">{t("athleteImport.plan_activated")}</p> : <><p className="text-[13px] text-muted">{t("athleteImport.activation_scope")}</p><Button disabled={!complete || pending} onClick={onActivate}>{t(pending ? "athleteImport.activating" : "athleteImport.activate")}</Button></>}
    {error && <p role="alert" className="text-[13px] text-alertText">{error}</p>}
  </section>;
}
