import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, ErrorNote, Input, friendlyDiscipline } from "../../components/kit";
import { useAiState } from "./AiConsentPanel";
import type { Doc } from "../lab/types";
import { WorkoutFields } from "./WorkoutFields";

interface Workout {
  date: string | null; discipline: string; duration_min: number | null; distance_m: number | null;
  start_time: string | null; session_type: string | null; description: string; intensity_targets: Record<string, string>; protected: boolean;
}
interface Structure {
  title: string; starts_on: string | null; ends_on: string | null; weekly_structure: string;
  sessions: Workout[]; ambiguities: string[]; protected: boolean;
}
interface Draft {
  id: number; document_id: number; document_revision: number; version: number; structure: Structure;
  payload_hash: string; status: string; confirmed_at: string | null;
}
const emptyStructure = (): Structure => ({ title: "", starts_on: null, ends_on: null, weekly_structure: "", sessions: [], ambiguities: [], protected: false });

export function PlanDocumentPanel({ document: doc }: { document: Doc }) {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const ai = useAiState();
  const drafts = useQuery({ queryKey: ["plan-drafts", uid], queryFn: () => api.get<Draft[]>("/lab/plan-drafts") });
  const disciplines = useQuery({ queryKey: ["athlete-disciplines"], queryFn: () => api.get<{ name: string }[]>("/athlete/disciplines") });
  const [editing, setEditing] = useState<Structure | null>(null);
  const [shownDraft, setShownDraft] = useState<Draft | null>(null);
  const [ambiguitiesReviewed, setAmbiguitiesReviewed] = useState(false);
  const latest = shownDraft ?? drafts.data?.find(d => d.document_id === doc.id);
  const extract = useMutation({ mutationFn: (useAi: boolean) => api.post<Draft>(`/lab/documents/${doc.id}/plan-drafts`, {
    expected_document_revision: doc.revision, use_ai: useAi, ...(useAi ? {} : { structure: editing }),
  }), onSuccess: next => { setShownDraft(next); setEditing(null); setAmbiguitiesReviewed(false); qc.invalidateQueries({ queryKey: ["plan-drafts"] }); qc.invalidateQueries({ queryKey: ["athlete-ai"] }); } });
  const confirm = useMutation({ mutationFn: () => api.post<{ draft: Draft }>(`/lab/plan-drafts/${latest!.id}/confirm`, { payload_hash: latest!.payload_hash, ambiguities_reviewed: ambiguitiesReviewed }), onSuccess: next => {
    setShownDraft(next.draft); ["plan-drafts", "athlete-day", "athlete-sport-overview", "structured-workout", "endurance", "lab", "athlete-profile", "athlete-templates", "me"].forEach(key => qc.invalidateQueries({ queryKey: [key] }));
  } });
  function begin() { setEditing(latest?.structure ?? { ...emptyStructure(), title: doc.filename }); }
  function update<K extends keyof Structure>(key: K, value: Structure[K]) { setEditing(old => ({ ...old!, [key]: value })); }
  function workoutUpdate<K extends keyof Workout>(index: number, key: K, value: Workout[K]) {
    setEditing(old => ({ ...old!, sessions: old!.sessions.map((w, i) => i === index ? { ...w, [key]: value } : w) }));
  }
  if (doc.status !== "confirmed") return <p className="mt-4 text-[13px] text-muted">{t("athlete.review_document_first")}</p>;
  const show = editing ?? latest?.structure;
  return <section className="mt-5 border-t border-hairline pt-4" aria-label={t("athlete.plan_document_title")}>
    <fieldset disabled={extract.isPending || confirm.isPending}><h3 className="text-[14px] font-medium">{t("athlete.plan_document_title")}</h3><p className="mt-2 text-[13px] text-muted">{t("athlete.plan_document_note")}</p>
    {!editing && <div className="mt-4 flex flex-wrap gap-3"><Button variant="ghost" onClick={begin}>{t(latest ? "athlete.revise_structure" : "athlete.review_structure")}</Button>
      <Button variant="ghost" disabled={ai.data?.effective_access === "disabled" || !ai.data || ai.data.budget.exhausted || extract.isPending} onClick={() => extract.mutate(true)}>{t("athlete.extract_with_ai")}</Button></div>}
    {ai.data?.effective_access === "disabled" && <Link className="mt-3 text-link inline-block" to="/app/settings?tab=profile">{t("athlete.ai_optional_extraction")}</Link>}
    {show && <div className="mt-5 space-y-4">
      {editing ? <><Input label={t("athlete.plan_title")} value={editing.title} onChange={v => update("title", v)} /><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_start")} type="date" value={editing.starts_on ?? ""} onChange={v => update("starts_on", v || null)} /><Input label={t("athlete.event_end")} type="date" value={editing.ends_on ?? ""} onChange={v => update("ends_on", v || null)} /></div><Input label={t("athlete.weekly_structure")} value={editing.weekly_structure} onChange={v => update("weekly_structure", v)} /><label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={editing.protected} onChange={e => update("protected", e.target.checked)} />{t("athlete.protect_plan")}</label></> : <div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-medium">{show.title || t("athlete.untitled_plan")}</h4><p className="mt-1 text-[12px] text-muted">{show.starts_on ?? "—"} – {show.ends_on ?? "—"} · {t("athlete.extraction_version", { count: latest?.version })}</p><p className="mt-2 text-[13px] text-muted">{show.weekly_structure}</p></div>{latest?.status === "confirmed" && <Badge tone="positive">{t("athlete.structure_confirmed")}</Badge>}</div>}
      <ul className="space-y-3">{show.sessions.map((w, index) => <li key={index} className="border border-hairline p-3"><details open={!!editing}>
        <summary className="cursor-pointer text-[13px] font-medium">{w.date ?? t("athlete.date_unknown")} · {friendlyDiscipline(w.discipline, t)} · {w.duration_min == null ? t("athlete.duration_unknown") : t("athlete.duration_minutes", { count: w.duration_min })}{w.protected ? ` · ${t("athlete.protected")}` : ""}</summary>
        {editing ? <div className="mt-4 space-y-3"><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_date")} type="date" value={w.date ?? ""} onChange={v => workoutUpdate(index, "date", v || null)} /></div>
          <WorkoutFields value={w} onChange={value => setEditing(old => ({ ...old!, sessions: old!.sessions.map((item, i) => i === index ? { ...item, ...value } : item) }))} /><Button variant="ghost" onClick={() => update("sessions", editing.sessions.filter((_, i) => i !== index))}>{t("athlete.remove_workout")}</Button>
        </div> : <div className="mt-3 text-[13px] text-muted"><p>{w.description}</p><p>{Object.entries(w.intensity_targets).filter(([, value]) => value).map(([key, value]) => `${t("athlete.intensity_"+key)}: ${value}`).join(" · ")}</p><p>{w.distance_m == null ? t("athlete.distance_unknown") : t("athlete.distance_metres", { count: w.distance_m })}</p></div>}
      </details></li>)}</ul>
      {editing && <><Button variant="ghost" onClick={() => update("sessions", [...editing.sessions, { date: null, discipline: "", duration_min: null, distance_m: null, start_time: null, session_type: null, description: "", intensity_targets: {}, protected: false }])}>{t("athlete.add_workout")}</Button><div className="flex flex-wrap gap-3"><Button disabled={extract.isPending} onClick={() => extract.mutate(false)}>{t("athlete.save_structure_draft")}</Button><Button variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button></div></>}
      {!!show.ambiguities.length && <div className="border-l-2 border-warning pl-3 text-[13px]"><p className="font-medium">{t("athlete.ambiguities")}</p><ul className="mt-2 space-y-2">{show.ambiguities.map((item, i) => <li key={i}>{editing ? <div className="space-y-2"><Input label={t("athleteImport.question_number", { count: i + 1 })} value={item} onChange={value => update("ambiguities", editing.ambiguities.map((old, index) => index === i ? value : old))} /><p className="text-[12px] text-muted">{t("athleteImport.legacy_question_note")}</p><Button variant="ghost" onClick={() => update("ambiguities", editing.ambiguities.filter((_, index) => index !== i))}>{t("athleteImport.use_correction")}</Button></div> : <p>{item}</p>}</li>)}</ul></div>}
      {!editing && latest?.status === "draft" && <div><label className="flex items-start gap-2 text-[13px]"><input type="checkbox" checked={ambiguitiesReviewed} onChange={e => setAmbiguitiesReviewed(e.target.checked)} /><span>{t("athlete.confirm_structure_agreement")}</span></label><Button className="mt-4" disabled={!ambiguitiesReviewed || confirm.isPending || !show.starts_on || !show.ends_on || !show.sessions.length || show.sessions.some(w => !w.date)} onClick={() => confirm.mutate()}>{t("athlete.confirm_active_plan")}</Button></div>}
    </div>}
    {(drafts.isError || disciplines.isError) && <ErrorNote />}
    {(extract.isError || confirm.isError) && <p role="alert" className="mt-4 text-[13px] text-alertText">{t((extract.error instanceof ApiError && extract.error.status === 409) || (confirm.error instanceof ApiError && confirm.error.status === 409) ? "athlete.conflict" : "athlete.structure_error")}</p>}
  </fieldset></section>;
}
