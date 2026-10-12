import { FocusAllocationEditor } from "./FocusAllocationEditor";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, ApiError, type Me } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, ErrorNote, Input, Loading, Select } from "../../components/kit";
import { ConfiguredZones } from "./ConfiguredZones";
import { AiConsentPanel } from "./AiConsentPanel";
import { AvailabilityEditor, availabilityError, type AvailabilityEntry } from "./AvailabilityEditor";
import type { AthleteContext, AthleteProfile, Focus, SportContext } from "./types";

const FOCUSES: Focus[] = ["gym", "running", "cycling"];
const numeric = (value: string) => value === "" ? undefined : Number(value);
interface ProfileDraft {
  focuses: Focus[]; context: AthleteContext; step: number;
  ftpWatts: string; ftpDate: string; ftpConfirmed: boolean;
}
// BrowserRouter has no data-router blocker. Keep drafts only in memory for back
// navigation; never store private athlete notes in browser persistence.
const emptyEntry = (): AvailabilityEntry => ({ selected: [0, 1, 2, 3, 4], start: "", end: "" });
const retainedDrafts = new Map<number, { draft: ProfileDraft; baseline: string; revision: number; entry: AvailabilityEntry }>();
const profileDraft = (profile: AthleteProfile): ProfileDraft => ({
  focuses: profile.training_focus, context: profile.context, step: profile.context.onboarding_step ?? 0,
  ftpWatts: String(profile.context.ftp?.watts ?? ""), ftpDate: profile.context.ftp?.measured_on ?? "", ftpConfirmed: profile.context.ftp?.confirmed ?? false,
});

export function AthleteProfilePanel() {
  const { t, i18n } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const profile = useQuery({ queryKey: ["athlete-profile", uid], queryFn: () => api.get<AthleteProfile>("/athlete/profile") });
  const [focuses, setFocuses] = useState<Focus[]>([]);
  const [context, setContext] = useState<AthleteContext>({});
  const [step, setStep] = useState(0);
  const [baseline, setBaseline] = useState("");
  const [revision, setRevision] = useState(0);
  const [entry, setEntry] = useState<AvailabilityEntry>(emptyEntry);
  const [ftpWatts, setFtpWatts] = useState("");
  const [ftpDate, setFtpDate] = useState("");
  const [ftpConfirmed, setFtpConfirmed] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const draft = { focuses, context, step, ftpWatts, ftpDate, ftpConfirmed };
  const snapshot = JSON.stringify(draft);
  const dirty = Boolean(baseline && baseline !== snapshot);
  const pendingWindow = Boolean(entry.start || entry.end);
  const unsaved = dirty || pendingWindow;
  function hydrate(next: AthleteProfile, retained = uid == null ? undefined : retainedDrafts.get(uid)) {
    const value = retained?.draft ?? profileDraft(next);
    setFocuses(value.focuses); setContext(value.context); setStep(value.step);
    setFtpWatts(value.ftpWatts); setFtpDate(value.ftpDate); setFtpConfirmed(value.ftpConfirmed);
    setBaseline(retained?.baseline ?? JSON.stringify(value)); setRevision(retained?.revision ?? next.revision);
    setEntry(retained?.entry ?? emptyEntry());
  }
  useEffect(() => {
    if (profile.data && !unsaved) hydrate(profile.data);
  }, [profile.data]);
  useEffect(() => {
    if (uid == null || !baseline) return;
    if (unsaved) retainedDrafts.set(uid, { draft, baseline, revision, entry });
    else retainedDrafts.delete(uid);
  }, [uid, snapshot, baseline, revision, unsaved, entry]);
  useEffect(() => () => {
    if (uid != null && useUi.getState().me?.user_id !== uid) retainedDrafts.delete(uid);
  }, [uid]);
  useEffect(() => {
    if (!unsaved) return;
    const leave = () => {
      if (!window.confirm(t("athlete.leave_unsaved"))) return false;
      if (uid != null) retainedDrafts.delete(uid);
      return true;
    };
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const click = (event: MouseEvent) => {
      const element = event.target instanceof Element ? event.target : null;
      const link = element?.closest<HTMLAnchorElement>("a[href]");
      const tab = element?.closest<HTMLElement>('[role="tab"]');
      const leavingTab = tab && !root.current?.contains(tab) && tab.closest('[role="tablist"]')?.getAttribute("aria-label") === t("settings.title") && tab.getAttribute("aria-selected") !== "true";
      const leavingLink = link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && !link.download && link.target !== "_blank" && link.origin === window.location.origin && (link.pathname.startsWith("/app") || link.pathname.startsWith("/legal")) && link.href !== window.location.href;
      if ((leavingTab || leavingLink) && !leave()) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    const keydown = (event: KeyboardEvent) => {
      const tab = event.target instanceof Element ? event.target.closest('[role="tab"]') : null;
      if (!tab || root.current?.contains(tab) || tab.closest('[role="tablist"]')?.getAttribute("aria-label") !== t("settings.title")) return;
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) && !leave()) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", click, true); document.addEventListener("keydown", keydown, true);
    return () => { window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", click, true); document.removeEventListener("keydown", keydown, true); };
  }, [unsaved, uid, t]);
  function edit<K extends keyof AthleteContext>(key: K, value: AthleteContext[K]) { setContext(c => ({ ...c, [key]: value })); }
  function sportEdit<K extends keyof SportContext>(focus: Focus, key: K, value: SportContext[K]) {
    setContext(c => ({ ...c, focuses: { ...c.focuses, [focus]: { ...c.focuses?.[focus], [key]: value } } }));
  }
  const save = useMutation({
    mutationFn: (nextStep: number) => api.put<AthleteProfile>("/athlete/profile", {
      expected_revision: revision, training_focus: focuses,
      context: { ...context, supporting_focus: (context.supporting_focus ?? []).filter(f => focuses.includes(f)), weekly_allocation_min: Object.fromEntries(Object.entries(context.weekly_allocation_min ?? {}).filter(([f]) => focuses.includes(f as Focus))), seasonal_focus: (context.seasonal_focus ?? []).map(s => ({...s, priorities: s.priorities.filter(f => focuses.includes(f))})).filter(s => s.priorities.length), focuses: Object.fromEntries(focuses.map(f => [f, context.focuses?.[f] ?? {}])), onboarding_step: nextStep,
        ftp: ftpConfirmed && ftpWatts && ftpDate ? { watts: Number(ftpWatts), measured_on: ftpDate, confirmed: true } : null },
    }),
    onSuccess: next => { if (uid != null) retainedDrafts.delete(uid); hydrate(next, undefined); qc.setQueryData(["athlete-profile", uid], next);
      qc.invalidateQueries({ queryKey: ["athlete-day"] }); qc.invalidateQueries({ queryKey: ["lab"] });
      void api.get<Me>("/me").then(me => useUi.getState().setMe(me)).catch(() => {}); },
  });
  const remove = useMutation({ mutationFn: () => api.delete("/athlete/profile"), onSuccess: () => {
    save.reset(); if (uid != null) retainedDrafts.delete(uid); hydrate({ training_focus: [], context: {}, revision: revision + 1 }, undefined); qc.invalidateQueries({ queryKey: ["athlete-profile", uid] });
    void api.get<Me>("/me").then(me => useUi.getState().setMe(me)).catch(() => {}); qc.invalidateQueries({ queryKey: ["athlete-day"] });
  } });
  if (profile.isLoading) return <Loading />;
  if (profile.isError || !profile.data) return <ErrorNote />;
  const days = Array.from({ length: 7 }, (_, day) => ({ value: String(day), label: new Intl.DateTimeFormat(i18n.language, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1+day))) }));
  const dayOptions = [{ value: "", label: t("design.not_specified") }, ...days];
  const windows = context.availability ?? [];
  const incompleteWindow = Boolean(availabilityError(windows)) || pendingWindow;
  const allocationInvalid = context.weekly_time_budget_min != null && Object.values(context.weekly_allocation_min ?? {}).reduce((a,b)=>a+(b??0),0) > context.weekly_time_budget_min;
  const seasonsInvalid = (context.seasonal_focus ?? []).some((s,i,all) => !s.starts_on || !s.ends_on || s.ends_on < s.starts_on || !s.priorities.length || all.some((other,j) => j < i && s.starts_on <= other.ends_on && s.ends_on >= other.starts_on));
  const invalidProfile = allocationInvalid || seasonsInvalid || incompleteWindow || (ftpConfirmed && (!ftpWatts || !ftpDate));
  const status = save.isPending ? "athlete.saving_profile" : save.isError ? (save.error instanceof ApiError && save.error.status === 409 ? "athlete.conflict" : "athlete.save_error") : unsaved ? "athlete.unsaved_changes" : save.isSuccess ? "athlete.profile_saved" : remove.isSuccess ? "athlete.profile_deleted" : "athlete.profile_save_scope";
  const priorityFields = <div>
    <p className="mb-3 text-[13px] text-muted">{t("athlete.focus_note")}</p>
    <div className="flex flex-wrap gap-4">{FOCUSES.map(f => <label className="flex min-h-11 items-center gap-2 text-[14px]" key={f}><input type="checkbox" checked={focuses.includes(f)} onChange={e => { setFocuses(old => e.target.checked ? [...old, f] : old.filter(x => x !== f)); }} />{t("athlete.focus_" + f)}</label>)}</div>
    <ol className="mt-3 space-y-2">{focuses.map((f, index) => <li className="flex items-center gap-3 text-[13px]" key={f}><span>{index+1}. {t("athlete.focus_" + f)}</span>
      {index > 0 && <Button variant="ghost" onClick={() => { setFocuses(old => { const copy = [...old]; [copy[index-1], copy[index]] = [copy[index], copy[index-1]]; return copy; }); }}>{t("athlete.move_up")}</Button>}</li>)}</ol>
    <FocusAllocationEditor focuses={focuses} context={context} onChange={patch=>setContext(c=>({...c,...patch}))} />
  </div>;
  const goalFields = <Input label={t("athlete.main_goal")} value={context.main_goal ?? ""} onChange={v => edit("main_goal", v)} />;
  const timeFields = <div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.weekly_hours")} type="number" min={0} max={168} step={0.25} value={context.weekly_time_budget_min == null ? "" : String(context.weekly_time_budget_min / 60)} onChange={v => edit("weekly_time_budget_min", v === "" ? undefined : Math.round(Number(v)*60))} /><Select label={t("athlete.rest_day")} value={context.preferred_rest_day == null ? "" : String(context.preferred_rest_day)} onChange={v => edit("preferred_rest_day", numeric(v))} options={dayOptions} /></div>;
  const availabilityFields = <AvailabilityEditor value={windows} onChange={v => edit("availability", v)} entry={entry} onEntryChange={setEntry} revision={revision} />;
  const planFields = <div className="space-y-4"><Select label={t("athlete.existing_plan")} value={context.existing_plan ?? ""} onChange={v => edit("existing_plan", v || undefined)} options={[{ value: "", label: t("design.not_specified") }, ...["yes", "no", "unsure"].map(value => ({ value, label: t("athlete."+value) }))]} />
    <Link className="text-link" to="/app/lab?tab=documents">{t("athlete.upload_existing_plan")}</Link></div>;
  return <div ref={root} className="flex flex-col gap-6">
    <Card><CardHeader title={t("athlete.profile_title")} right={save.isSuccess && !unsaved && <Badge tone="positive">{t("settings.saved")}</Badge>} />
      <p className="mb-5 text-[13px] text-muted">{t("athlete.progressive_note")}</p>
      <fieldset disabled={save.isPending || remove.isPending}>
      {step < 5 ? <section aria-label={t("athlete.onboarding")}>
        <p className="eyebrow">{t("athlete.step", { count: step+1 })}</p><h3 className="my-4 text-[18px] font-medium">{t("athlete.question_" + step)}</h3>
        {[priorityFields, goalFields, timeFields, availabilityFields, planFields][step]}
        <div className="mt-5"><Button variant="ghost" disabled={pendingWindow} onClick={() => setStep(5)}>{t("athlete.complete_later")}</Button></div>
      </section> : <div className="space-y-5"><section><h3 className="mb-3 text-[15px] font-medium">{t("athlete.section_focus")}</h3>{priorityFields}</section><section><h3 className="mb-3 text-[15px] font-medium">{t("athlete.section_goals")}</h3>{goalFields}</section><details><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.availability")}</summary><div className="mt-4 space-y-4">{timeFields}{availabilityFields}</div></details><details><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.existing_plan")}</summary><div className="mt-4">{planFields}</div></details></div>}
      <details className="mt-6 border-t border-hairline pt-5"><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.optional_details")}</summary>
        <p className="mt-3 text-[13px] text-muted">{t("athlete.advanced_optional_note")}</p>
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
          {focuses.includes("cycling") && <fieldset className="space-y-3 border-t border-hairline pt-4"><legend className="text-[14px] font-medium">{t("athlete.ftp_title")}</legend><p className="text-[12px] text-muted">{t("athlete.ftp_note")}</p><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.ftp_watts")} type="number" min={1} value={ftpWatts} onChange={v => { setFtpWatts(v); setFtpConfirmed(false); }} /><Input label={t("athlete.ftp_date")} type="date" value={ftpDate} onChange={v => { setFtpDate(v); setFtpConfirmed(false); }} /></div><label className="flex items-start gap-2 text-[13px]"><input type="checkbox" checked={ftpConfirmed} onChange={e => { setFtpConfirmed(e.target.checked); }} />{t("athlete.ftp_confirm")}</label></fieldset>}
          <ConfiguredZones kind="hr" value={context.hr_zones} onChange={v => edit("hr_zones", v)} /><ConfiguredZones kind="power" value={context.power_zones} onChange={v => edit("power_zones", v)} />
          <Input label={t("athlete.restrictions")} value={context.self_declared_restrictions ?? ""} onChange={v => edit("self_declared_restrictions", v)} /><p className="text-[12px] text-muted">{t("athlete.restrictions_note")}</p>
          <Link className="text-link" to="/app/settings?tab=notifications">{t("athlete.notification_preferences")}</Link>
        </div>
      </details>
      <h3 className="mt-6 text-[15px] font-medium">{t("athlete.section_about")}</h3>
      <label className="mt-3 flex flex-col gap-2 text-[13px]"><span>{t("athlete.open_context")}</span><textarea className="min-h-28 w-full border border-hairline bg-transparent px-3 py-2 focus:border-ink" maxLength={8000} value={context.athlete_notes ?? ""} onChange={e => edit("athlete_notes", e.target.value)} /></label>
      <p className="mt-2 text-[12px] text-muted">{t("athlete.context_privacy")}</p>
      </fieldset>
      {seasonsInvalid && <p role="alert" className="mt-3 text-[13px] text-alertText">{t("athlete.season_invalid")}</p>}
      <p role={save.isError ? "alert" : "status"} className="mt-4 text-[13px] text-muted">{t(status)}</p>
      {remove.isError && <ErrorNote />}
      <div className="mt-5 flex flex-wrap gap-3"><Button disabled={save.isPending || remove.isPending || invalidProfile} onClick={() => save.mutate(step < 5 ? step + 1 : step)}>{t(save.isPending ? "athlete.saving_profile" : step < 5 ? step === 4 ? "athlete.finish" : "athlete.save_continue" : "athlete.save_profile")}</Button><a className="text-link self-center" href="/lab/export/account.json">{t("athlete.export_context")}</a><Button variant="ghost" disabled={remove.isPending || save.isPending} onClick={() => remove.mutate()}>{t("athlete.delete_context")}</Button>{save.isError && <Button variant="ghost" onClick={async () => { if (unsaved && !window.confirm(t("athlete.leave_unsaved"))) return; const next = await profile.refetch(); if (next.data) { if (uid != null) retainedDrafts.delete(uid); hydrate(next.data, undefined); save.reset(); } }}>{t("athlete.reload")}</Button>}</div>
    </Card>
    <AiConsentPanel />
  </div>;
}
