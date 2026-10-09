import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, ApiError, type Me } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, ErrorNote, Input, Loading, Select } from "../../components/kit";
import { ConfiguredZones } from "./ConfiguredZones";
import { AiConsentPanel } from "./AiConsentPanel";
import type { AthleteContext, AthleteProfile, Focus, SportContext } from "./types";

const FOCUSES: Focus[] = ["gym", "running", "cycling"];
const numeric = (value: string) => value === "" ? undefined : Number(value);

export function AthleteProfilePanel() {
  const { t, i18n } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const profile = useQuery({ queryKey: ["athlete-profile", uid], queryFn: () => api.get<AthleteProfile>("/athlete/profile") });
  const [focuses, setFocuses] = useState<Focus[]>([]);
  const [context, setContext] = useState<AthleteContext>({});
  const [step, setStep] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [ftpWatts, setFtpWatts] = useState("");
  const [ftpDate, setFtpDate] = useState("");
  const [ftpConfirmed, setFtpConfirmed] = useState(false);
  useEffect(() => {
    if (profile.data && !dirty) {
      setFocuses(profile.data.training_focus); setContext(profile.data.context); setStep(profile.data.context.onboarding_step ?? 0);
      setFtpWatts(String(profile.data.context.ftp?.watts ?? "")); setFtpDate(profile.data.context.ftp?.measured_on ?? ""); setFtpConfirmed(profile.data.context.ftp?.confirmed ?? false);
    }
  }, [profile.data, dirty]);
  function edit<K extends keyof AthleteContext>(key: K, value: AthleteContext[K]) { setDirty(true); setContext(c => ({ ...c, [key]: value })); }
  function sportEdit<K extends keyof SportContext>(focus: Focus, key: K, value: SportContext[K]) {
    setDirty(true); setContext(c => ({ ...c, focuses: { ...c.focuses, [focus]: { ...c.focuses?.[focus], [key]: value } } }));
  }
  const save = useMutation({
    mutationFn: (nextStep: number) => api.put<AthleteProfile>("/athlete/profile", {
      expected_revision: profile.data!.revision, training_focus: focuses,
      context: { ...context, focuses: Object.fromEntries(focuses.map(f => [f, context.focuses?.[f] ?? {}])), onboarding_step: nextStep,
        ftp: ftpConfirmed && ftpWatts && ftpDate ? { watts: Number(ftpWatts), measured_on: ftpDate, confirmed: true } : null },
    }),
    onSuccess: async next => { setDirty(false); qc.setQueryData(["athlete-profile", uid], next); setStep(next.context.onboarding_step ?? 0);
      qc.invalidateQueries({ queryKey: ["athlete-day"] }); qc.invalidateQueries({ queryKey: ["lab"] });
      const me = await api.get<Me>("/me"); useUi.getState().setMe(me); },
  });
  const remove = useMutation({ mutationFn: () => api.delete("/athlete/profile"), onSuccess: async () => {
    setDirty(false); await qc.invalidateQueries({ queryKey: ["athlete-profile", uid] });
    useUi.getState().setMe(await api.get<Me>("/me")); qc.invalidateQueries({ queryKey: ["athlete-day"] });
  } });
  if (profile.isLoading) return <Loading />;
  if (profile.isError || !profile.data) return <ErrorNote />;
  const days = Array.from({ length: 7 }, (_, day) => ({ value: String(day), label: new Intl.DateTimeFormat(i18n.language, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1+day))) }));
  const dayOptions = [{ value: "", label: t("design.not_specified") }, ...days];
  const windows = context.availability ?? [];
  const incompleteWindow = windows.some(w => !w.start || !w.end || w.start >= w.end);
  const priorityFields = <div>
    <p className="mb-3 text-[13px] text-muted">{t("athlete.focus_note")}</p>
    <div className="flex flex-wrap gap-4">{FOCUSES.map(f => <label className="flex min-h-11 items-center gap-2 text-[14px]" key={f}><input type="checkbox" checked={focuses.includes(f)} onChange={e => { setDirty(true); setFocuses(old => e.target.checked ? [...old, f] : old.filter(x => x !== f)); }} />{t("athlete.focus_" + f)}</label>)}</div>
    <ol className="mt-3 space-y-2">{focuses.map((f, index) => <li className="flex items-center gap-3 text-[13px]" key={f}><span>{index+1}. {t("athlete.focus_" + f)}</span>
      {index > 0 && <Button variant="ghost" onClick={() => { setDirty(true); setFocuses(old => { const copy = [...old]; [copy[index-1], copy[index]] = [copy[index], copy[index-1]]; return copy; }); }}>{t("athlete.move_up")}</Button>}</li>)}</ol>
  </div>;
  const goalFields = <Input label={t("athlete.main_goal")} value={context.main_goal ?? ""} onChange={v => edit("main_goal", v)} />;
  const timeFields = <div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.weekly_hours")} type="number" min={0} max={168} step={0.25} value={context.weekly_time_budget_min == null ? "" : String(context.weekly_time_budget_min / 60)} onChange={v => edit("weekly_time_budget_min", v === "" ? undefined : Math.round(Number(v)*60))} /><Select label={t("athlete.rest_day")} value={context.preferred_rest_day == null ? "" : String(context.preferred_rest_day)} onChange={v => edit("preferred_rest_day", numeric(v))} options={dayOptions} /></div>;
  const availabilityFields = <div className="space-y-3">
    <p className="text-[13px] text-muted">{t("athlete.availability_note")}</p>
    {windows.map((w, index) => <div className="grid items-end gap-3 sm:grid-cols-4" key={index}>
      <Select label={t("athlete.day")} value={String(w.day)} onChange={v => edit("availability", windows.map((old, n) => n === index ? { ...old, day: Number(v) } : old))} options={days} />
      <Input label={t("athlete.start_time")} type="time" value={w.start} onChange={v => edit("availability", windows.map((old, n) => n === index ? { ...old, start: v } : old))} />
      <Input label={t("athlete.end_time")} type="time" value={w.end} onChange={v => edit("availability", windows.map((old, n) => n === index ? { ...old, end: v } : old))} />
      <Button variant="ghost" onClick={() => edit("availability", windows.filter((_, n) => n !== index))}>{t("athlete.remove_window")}</Button>
    </div>)}
    <Button variant="ghost" onClick={() => edit("availability", [...windows, { day: 0, start: "", end: "" }])}>{t("athlete.add_window")}</Button>
    {incompleteWindow && <p role="status" className="text-[12px] text-muted">{t("athlete.complete_window")}</p>}
  </div>;
  const planFields = <div className="space-y-4"><Select label={t("athlete.existing_plan")} value={context.existing_plan ?? ""} onChange={v => edit("existing_plan", v || undefined)} options={[{ value: "", label: t("design.not_specified") }, ...["yes", "no", "unsure"].map(value => ({ value, label: t("athlete."+value) }))]} />
    <Link className="text-link" to="/app/lab?tab=documents">{t("athlete.upload_existing_plan")}</Link></div>;
  return <div className="flex flex-col gap-6">
    <Card><CardHeader title={t("athlete.profile_title")} right={save.isSuccess && <Badge tone="positive">{t("settings.saved")}</Badge>} />
      <p className="mb-5 text-[13px] text-muted">{t("athlete.progressive_note")}</p>
      {step < 5 ? <section aria-label={t("athlete.onboarding")}>
        <p className="eyebrow">{t("athlete.step", { count: step+1 })}</p><h3 className="my-4 text-[18px] font-medium">{t("athlete.question_" + step)}</h3>
        {[priorityFields, goalFields, timeFields, availabilityFields, planFields][step]}
        <div className="mt-5 flex flex-wrap gap-3"><Button disabled={save.isPending || incompleteWindow} onClick={() => save.mutate(step+1)}>{t(step === 4 ? "athlete.finish" : "athlete.save_continue")}</Button><Button variant="ghost" onClick={() => { setDirty(true); setStep(5); }}>{t("athlete.complete_later")}</Button></div>
      </section> : <div className="space-y-5">{priorityFields}{goalFields}{timeFields}<details><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.availability")}</summary><div className="mt-4">{availabilityFields}</div></details>{planFields}</div>}
      <details className="mt-6 border-t border-hairline pt-5"><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.optional_details")}</summary>
        <div className="mt-5 space-y-6">{focuses.map(f => { const sport = context.focuses?.[f] ?? {}; return <section key={f}><h3 className="mb-3 text-[15px] font-medium">{t("athlete.focus_"+f)}</h3><div className="grid gap-3 sm:grid-cols-2">
          <Select label={t("athlete.level")} value={sport.level ?? ""} onChange={v => sportEdit(f, "level", v || undefined)} options={[{ value: "", label: t("design.not_specified") }, ...["new", "beginner", "intermediate", "experienced"].map(value => ({ value, label: t("athlete.level_"+value) }))]} />
          <Input label={t("athlete.weekly_frequency")} type="number" min={0} max={21} value={String(sport.weekly_frequency ?? "")} onChange={v => sportEdit(f, "weekly_frequency", numeric(v))} />
          <Input label={t("athlete.weekly_minutes")} type="number" min={0} value={String(sport.weekly_duration_min ?? "")} onChange={v => sportEdit(f, "weekly_duration_min", numeric(v))} />
          {f !== "gym" && <><Input label={t("athlete.weekly_distance")} type="number" min={0} value={String(sport.weekly_distance_km ?? "")} onChange={v => sportEdit(f, "weekly_distance_km", numeric(v))} /><Input label={t("athlete.longest_distance")} type="number" min={0} value={String(sport.longest_distance_km ?? "")} onChange={v => sportEdit(f, "longest_distance_km", numeric(v))} /><Select label={t("athlete.long_day")} value={String(sport.long_session_day ?? "")} onChange={v => sportEdit(f, "long_session_day", numeric(v))} options={dayOptions} /></>}
          <Select label={t("athlete.goal_type")} value={sport.goal ?? ""} onChange={v => sportEdit(f, "goal", v || undefined)} options={[{ value: "", label: t("design.not_specified") }, ...["maintain", "health", "body_composition", "performance", "event"].map(value => ({ value, label: t("athlete.goal_"+value) }))]} />
          <Input label={t("athlete.equipment")} value={(sport.equipment ?? []).join(", ")} onChange={v => sportEdit(f, "equipment", v.split(",").map(s => s.trim()).filter(Boolean))} />
          <Input label={t("athlete.plan_constraints")} value={sport.constraints ?? ""} onChange={v => sportEdit(f, "constraints", v)} />
          {sport.goal === "event" && <><Input label={t("athlete.target_event")} value={sport.event?.title ?? ""} onChange={v => sportEdit(f, "event", { ...sport.event, title: v, priority: sport.event?.priority ?? 2 })} /><Input label={t("athlete.event_date")} type="date" value={sport.event?.date ?? ""} onChange={v => sportEdit(f, "event", { title: sport.event?.title ?? "", priority: sport.event?.priority ?? 2, ...sport.event, date: v || undefined })} /><Input label={t("athlete.event_distance")} type="number" min={0} value={String(sport.event?.distance_km ?? "")} onChange={v => sportEdit(f, "event", { title: sport.event?.title ?? "", priority: sport.event?.priority ?? 2, ...sport.event, distance_km: numeric(v) })} /><Select label={t("athlete.event_priority")} value={String(sport.event?.priority ?? 2)} onChange={v => sportEdit(f, "event", { title: sport.event?.title ?? "", ...sport.event, priority: Number(v) })} options={[1,2,3].map(value => ({ value: String(value), label: t("athlete.priority_"+value) }))} /></>}
        </div><fieldset className="mt-4"><legend className="text-[12px] text-muted">{t("athlete.preferred_days")}</legend><div className="flex flex-wrap gap-3">{days.map(d => <label className="flex min-h-11 items-center gap-2 text-[12px]" key={d.value}><input type="checkbox" checked={(sport.preferred_days ?? []).includes(Number(d.value))} onChange={e => sportEdit(f, "preferred_days", e.target.checked ? [...(sport.preferred_days ?? []), Number(d.value)] : (sport.preferred_days ?? []).filter(x => x !== Number(d.value)))} />{d.label}</label>)}</div></fieldset></section>; })}
          <div className="grid gap-3 sm:grid-cols-2">{(["sleep_work_schedule", "schedule_constraints", "gym_split", "preferred_exercises", "recent_consistency", "event_history", "devices", "coaching_style"] as const).map(key => <Input key={key} label={t("athlete."+key)} value={context[key] ?? ""} onChange={v => edit(key, v)} />)}
            <Input label={t("athlete.gym_years")} type="number" min={0} value={String(context.gym_experience_years ?? "")} onChange={v => edit("gym_experience_years", numeric(v))} />
            <Select label={t("athlete.rpe_preference")} value={context.rpe_preference == null ? "" : context.rpe_preference ? "yes" : "no"} onChange={v => edit("rpe_preference", v === "" ? undefined : v === "yes")} options={[{ value: "", label: t("design.not_specified") }, { value: "yes", label: t("athlete.yes") }, { value: "no", label: t("athlete.no") }]} />
          </div>
          {focuses.includes("cycling") && <fieldset className="space-y-3 border-t border-hairline pt-4"><legend className="text-[14px] font-medium">{t("athlete.ftp_title")}</legend><p className="text-[12px] text-muted">{t("athlete.ftp_note")}</p><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.ftp_watts")} type="number" min={1} value={ftpWatts} onChange={v => { setDirty(true); setFtpWatts(v); setFtpConfirmed(false); }} /><Input label={t("athlete.ftp_date")} type="date" value={ftpDate} onChange={v => { setDirty(true); setFtpDate(v); setFtpConfirmed(false); }} /></div><label className="flex items-start gap-2 text-[13px]"><input type="checkbox" checked={ftpConfirmed} onChange={e => { setDirty(true); setFtpConfirmed(e.target.checked); }} />{t("athlete.ftp_confirm")}</label></fieldset>}
          <ConfiguredZones kind="hr" value={context.hr_zones} onChange={v => edit("hr_zones", v)} /><ConfiguredZones kind="power" value={context.power_zones} onChange={v => edit("power_zones", v)} />
          <Input label={t("athlete.restrictions")} value={context.self_declared_restrictions ?? ""} onChange={v => edit("self_declared_restrictions", v)} /><p className="text-[12px] text-muted">{t("athlete.restrictions_note")}</p>
          <Link className="text-link" to="/app/settings?tab=notifications">{t("athlete.notification_preferences")}</Link>
        </div>
      </details>
      <label className="mt-6 flex flex-col gap-2 text-[13px]"><span>{t("athlete.open_context")}</span><textarea className="min-h-28 w-full border border-hairline bg-transparent px-3 py-2 focus:border-ink" maxLength={8000} value={context.athlete_notes ?? ""} onChange={e => edit("athlete_notes", e.target.value)} /></label>
      <p className="mt-2 text-[12px] text-muted">{t("athlete.context_privacy")}</p>
      {save.isError && <p role="alert" className="mt-3 text-[13px] text-alertText">{t(save.error instanceof ApiError && save.error.status === 409 ? "athlete.conflict" : "athlete.save_error")}</p>}
      {remove.isError && <ErrorNote />}
      <div className="mt-5 flex flex-wrap gap-3"><Button disabled={save.isPending || incompleteWindow || (ftpConfirmed && (!ftpWatts || !ftpDate))} onClick={() => save.mutate(step)}>{t("athlete.save_profile")}</Button><a className="text-link self-center" href="/lab/export/account.json">{t("athlete.export_context")}</a><Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>{t("athlete.delete_context")}</Button>{save.isError && <Button variant="ghost" onClick={() => { setDirty(false); profile.refetch(); }}>{t("athlete.reload")}</Button>}</div>
    </Card>
    <AiConsentPanel />
  </div>;
}
