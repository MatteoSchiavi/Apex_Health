import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, ErrorNote, Input, Loading, friendlyDiscipline } from "../../components/kit";
import { useAiState } from "./AiConsentPanel";
import type { Doc } from "../lab/types";
import type { DatedWorkout, PlanDraft, PlanStructure } from "./importTypes";
import { emptyWorkout } from "./importTypes";
import { WorkoutFields } from "./WorkoutFields";
import { PlanReadiness } from "./PlanReadiness";
import { planReadiness } from "./planReadiness";

const emptyStructure = (): PlanStructure => ({ title: "", starts_on: null, ends_on: null, weekly_structure: "", sessions: [], ambiguities: [], protected: false });

export function PlanDocumentPanel({ document: doc }: { document: Doc }) {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const ai = useAiState();
  const drafts = useQuery({ queryKey: ["plan-drafts", uid], queryFn: () => api.get<PlanDraft[]>("/lab/plan-drafts") });
  const disciplines = useQuery({ queryKey: ["athlete-disciplines"], queryFn: () => api.get<{ name: string }[]>("/athlete/disciplines") });
  const [editing, setEditing] = useState<PlanStructure | null>(null);
  const [shownDraft, setShownDraft] = useState<PlanDraft | null>(null);
  const [ambiguitiesReviewed, setAmbiguitiesReviewed] = useState(false);
  const saved = drafts.data?.find(d => d.document_id === doc.id);
  const latest = shownDraft && (!saved || shownDraft.version >= saved.version) ? shownDraft : saved;
  const extract = useMutation({ mutationFn: (useAi: boolean) => api.post<PlanDraft>(`/lab/documents/${doc.id}/plan-drafts`, {
    expected_document_revision: doc.revision, use_ai: useAi, ...(useAi ? {} : { structure: editing }),
  }), onSuccess: next => { setShownDraft(next); setEditing(null); setAmbiguitiesReviewed(false); void qc.invalidateQueries({ queryKey: ["plan-drafts"] }); void qc.invalidateQueries({ queryKey: ["athlete-ai"] }); } });
  const confirm = useMutation({ mutationFn: () => api.post<{ draft: PlanDraft }>(`/lab/plan-drafts/${latest!.id}/confirm`, { payload_hash: latest!.payload_hash, ambiguities_reviewed: ambiguitiesReviewed }), onSuccess: next => {
    setShownDraft(next.draft); ["plan-drafts", "athlete-day", "athlete-sport-overview", "structured-workout", "endurance", "lab", "athlete-profile", "athlete-templates", "me"].forEach(key => void qc.invalidateQueries({ queryKey: [key] }));
  } });
  const dirty = !!editing && JSON.stringify(editing) !== JSON.stringify(latest?.structure ?? { ...emptyStructure(), title: doc.filename });
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const click = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const link = target?.closest<HTMLAnchorElement>("a[href]");
      const tab = target?.closest<HTMLButtonElement>("button[role=tab], button[aria-pressed]");
      const leaves = (link && link.target !== "_blank" && !link.download && link.href !== window.location.href) || (tab && tab.getAttribute("aria-selected") !== "true" && tab.getAttribute("aria-pressed") !== "true");
      if (leaves && !window.confirm(t("athlete.leave_unsaved"))) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    window.addEventListener("beforeunload", guard); document.addEventListener("click", click, true);
    return () => { window.removeEventListener("beforeunload", guard); document.removeEventListener("click", click, true); };
  }, [dirty, t]);
  function begin() { setEditing(structuredClone(latest?.structure ?? { ...emptyStructure(), title: doc.filename })); setAmbiguitiesReviewed(false); confirm.reset(); extract.reset(); }
  function update<K extends keyof PlanStructure>(key: K, value: PlanStructure[K]) { setEditing(old => ({ ...old!, [key]: value })); }
  function workoutUpdate<K extends keyof DatedWorkout>(index: number, key: K, value: DatedWorkout[K]) {
    setEditing(old => ({ ...old!, sessions: old!.sessions.map((w, i) => i === index ? { ...w, [key]: value } : w) }));
  }
  if (doc.status !== "confirmed") return <p className="mt-4 text-[13px] text-muted">{t("athlete.review_document_first")} <Link to={`/app/lab?tab=documents#document-${doc.id}`} className="text-link">{t("v01Plan.review_source")}</Link></p>;
  const show = editing ?? latest?.structure;
  const sports = disciplines.data?.map(d => d.name);
  const readiness = show ? planReadiness(show, sports) : null;
  const staleSource = !!latest && latest.document_revision !== doc.revision;
  const pending = extract.isPending || confirm.isPending;
  const error = extract.error ?? confirm.error;
  const protectedConflict = error instanceof ApiError && error.status === 409 && JSON.stringify(error.body).includes("protected upcoming workouts");
  return <section className="mt-5 border-t border-hairline pt-4" aria-label={t("athlete.plan_document_title")}>
    <fieldset disabled={pending} className="space-y-5">
      <div><h3 className="text-[16px] font-medium">{t("athlete.plan_document_title")}</h3><p className="mt-2 text-[13px] text-muted">{t("v01Plan.review_steps")}</p></div>
      {drafts.isLoading && <Loading />}
      {!editing && !drafts.isLoading && <div className="flex flex-wrap gap-3"><Button onClick={begin}>{t(latest ? "athlete.revise_structure" : "athlete.review_structure")}</Button>
        {!!ai.data && ai.data.effective_access !== "disabled" && !ai.data.budget.exhausted && <Button variant="ghost" onClick={() => extract.mutate(true)}>{t("athlete.extract_with_ai")}</Button>}</div>}
      {show && <>
        {!editing && <div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-medium">{show.title || t("athlete.untitled_plan")}</h4><p className="mt-1 text-[12px] text-muted">{show.starts_on ?? "—"} – {show.ends_on ?? "—"} · {t("v01Plan.workout_count", { count: show.sessions.length })}</p>{show.weekly_structure && <p className="mt-2 text-[13px] text-muted whitespace-pre-wrap">{show.weekly_structure}</p>}</div><Badge tone={latest?.status === "confirmed" ? "positive" : "warning"}>{t(latest?.status === "confirmed" ? "athlete.structure_confirmed" : "v01Plan.draft_not_active")}</Badge></div>}
        {(editing || latest?.status !== "confirmed") && <PlanReadiness structure={show} disciplines={sports} />}
        {!editing && staleSource && <p role="alert" className="text-[13px] text-alertText">{t("v01Plan.source_changed")}</p>}
        {editing && <><Input label={t("athlete.plan_title")} value={editing.title} onChange={v => update("title", v)} /><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_start")} type="date" value={editing.starts_on ?? ""} onChange={v => update("starts_on", v || null)} /><Input label={t("athlete.event_end")} type="date" value={editing.ends_on ?? ""} onChange={v => update("ends_on", v || null)} /></div><Input label={t("athlete.weekly_structure")} value={editing.weekly_structure} onChange={v => update("weekly_structure", v)} /><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={editing.protected} onChange={e => update("protected", e.target.checked)} />{t("athlete.protect_plan")}</label></>}
        <ol className="space-y-3">{show.sessions.map((w, index) => <li key={index} className="border border-hairline p-3">
          <p className="text-[13px] font-medium">{t("v01Plan.session_name", { number: index + 1, sport: friendlyDiscipline(w.discipline, t) })} · {w.duration_min == null ? t("athlete.duration_unknown") : t("athlete.duration_minutes", { count: w.duration_min })}{w.protected ? ` · ${t("athlete.protected")}` : ""}</p>
          {editing ? <div className="mt-3"><Input label={t("athlete.event_date")} type="date" value={w.date ?? ""} onChange={v => workoutUpdate(index, "date", v || null)} /></div> : <p className="mt-1 text-[13px] text-muted">{w.date ?? t("athlete.date_unknown")}{w.start_time ? ` · ${w.start_time.slice(0, 5)}` : ""}</p>}
          <details className="mt-3" open={editing && !w.discipline ? true : undefined}><summary className="cursor-pointer text-[13px]">{t("v01Plan.workout_details")}</summary>
            {editing ? <div className="mt-4 space-y-3"><WorkoutFields value={w} onChange={value => setEditing(old => ({ ...old!, sessions: old!.sessions.map((item, i) => i === index ? { ...item, ...value } : item) }))} /><Button variant="ghost" onClick={() => update("sessions", editing.sessions.filter((_, i) => i !== index))}>{t("athlete.remove_workout")}</Button></div> : <div className="mt-3 text-[13px] text-muted"><p>{w.description}</p><p>{Object.entries(w.intensity_targets).filter(([, value]) => value).map(([key, value]) => `${t("athlete.intensity_" + key)}: ${value}`).join(" · ")}</p><p>{w.distance_m == null ? t("athlete.distance_unknown") : t("athlete.distance_metres", { count: w.distance_m })}</p></div>}
          </details>
        </li>)}</ol>
        {editing && <Button variant="ghost" onClick={() => update("sessions", [...editing.sessions, { ...emptyWorkout(), date: null }])}>{t("athlete.add_workout")}</Button>}
        {!!show.ambiguities.length && <details className="border-l-2 border-warning pl-3 text-[13px]" open={editing || show.ambiguities.length <= 3 ? true : undefined}><summary className="cursor-pointer font-medium">{t("v01Plan.review_questions", { count: show.ambiguities.length })}</summary><p className="mt-2 text-muted">{t("v01Plan.questions_note")}</p><ul className="mt-3 space-y-3">{show.ambiguities.map((item, i) => <li key={i}>{editing ? <div className="space-y-2"><Input label={t("athleteImport.question_number", { count: i + 1 })} value={item} onChange={value => update("ambiguities", editing.ambiguities.map((old, index) => index === i ? value : old))} /><p className="text-[12px] text-muted">{t("athleteImport.legacy_question_note")}</p><Button variant="ghost" onClick={() => update("ambiguities", editing.ambiguities.filter((_, index) => index !== i))}>{t("athleteImport.use_correction")}</Button></div> : <p>{item}</p>}</li>)}</ul></details>}
        {editing ? <div className="flex flex-wrap gap-3"><Button disabled={pending || !readiness?.saveable || !sports} onClick={() => extract.mutate(false)}>{t("athlete.save_structure_draft")}</Button><Button variant="ghost" onClick={() => { if (!dirty || window.confirm(t("athlete.leave_unsaved"))) setEditing(null); }}>{t("common.cancel")}</Button></div> : latest?.status === "draft" && <div className="space-y-3 border-t border-hairline pt-4"><p className="text-[13px] text-muted">{t("athleteImport.activation_scope")}</p><label className="flex min-h-11 items-start gap-2 text-[13px]"><input type="checkbox" checked={ambiguitiesReviewed} onChange={e => setAmbiguitiesReviewed(e.target.checked)} /><span>{t("athlete.confirm_structure_agreement")}</span></label>{!ambiguitiesReviewed && <p className="text-[12px] text-muted">{t("v01Plan.acknowledge_required")}</p>}<Button disabled={!ambiguitiesReviewed || pending || !readiness?.ready || !sports || staleSource} onClick={() => confirm.mutate()}>{t("athlete.confirm_active_plan")}</Button></div>}
        {latest?.status === "confirmed" && !editing && <p role="status" className="text-[13px]">{t("athleteImport.plan_activated")} <Link to="/app/training?tab=plan" className="text-link">{t("v01Plan.view_today")}</Link></p>}
      </>}
      {(drafts.isError || disciplines.isError) && <ErrorNote />}
      {error && <p role="alert" className="text-[13px] text-alertText">{t(protectedConflict ? "v01Plan.protected_conflict" : error instanceof ApiError && error.status === 409 ? "athlete.conflict" : "athlete.structure_error")}</p>}
    </fieldset>
  </section>;
}
