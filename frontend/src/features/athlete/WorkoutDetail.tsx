import {StepEditor,StepSummary,freshStep,stepError,type StructuredWorkout,type WorkoutStep} from "./StructuredWorkoutSteps";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, ErrorNote, Input, Loading, PageHeader, fmtDuration, friendlyDiscipline } from "../../components/kit";
import { SessionCheckin } from "./SessionCheckin";
import { useAthleteDay } from "./YourDay";

interface WorkoutReceipt { id: number; planned_session_id: number; revision: number; payload_hash: string; source: string; structure: StructuredWorkout; duration_total_s: number | null }
interface WorkoutDraft { id: number; planned_session_id: number; plan_revision: number; workout_revision: number; payload_hash: string; status: string; structure: StructuredWorkout; duration_total_s: number | null }
interface WorkoutDetailResponse { pending_draft?: WorkoutDraft | null; history?: WorkoutReceipt[]; planned_session_id: number; plan_revision: number; protected: boolean; editable: boolean; edit_block_reason: "past" | "protected" | "completed_or_skipped" | "recorded" | null; workout: WorkoutReceipt | null; session: { date: string; discipline: string; session_type: string | null; duration_min: number | null; description: string | null }; education: (WorkoutStep & { number?: string; parent_id?: string | null; objective: string; execution: string; common_mistake?: string; conservative_alternative?: string; limitation: string })[] }

function WorkoutCompletion({ sessionId, date }: { sessionId: number; date: string }) {
  const { t } = useTranslation();
  const day = useAthleteDay(date);
  const context = !day.isError && day.data?.date === date ? day.data : null;
  const session = context?.sessions.find(item => item.id === sessionId);
  const activity = session?.activity_id == null ? null : context?.activities.find(item =>
    item.id === session.activity_id && item.planned_session_id === sessionId);
  const checkin = activity?.checkin ?? session?.checkin;
  const validReceipt = !checkin || (checkin.planned_session_id === sessionId
    && checkin.activity_id === (activity?.id ?? null));
  const available = !!session && (session.activity_id == null || !!activity) && validReceipt;
  return <Card>
    <CardHeader title={<h2>{t("structuredWorkout.completion_title")}</h2>}
      right={available && <Badge tone={session.status === "completed" ? "positive" : "neutral"}>{t("athlete.state_" + session.status)}</Badge>} />
    {day.isLoading ? <Loading /> : available ? <>
      <p className="text-[13px] text-muted">{t("structuredWorkout.completion_note")}</p>
      {activity && <Link className="text-link mt-3 inline-block text-[13px]" to={`/app/activities/${activity.id}`}>{t("athlete.view_activity")} ↗</Link>}
      <SessionCheckin key={`${sessionId}:${activity?.id ?? "unrecorded"}`} defaultOpen anchor="planned"
        plannedSessionId={sessionId} activityId={activity?.id} checkin={checkin} />
    </> : <>
      <p role="status" className="text-[13px] text-muted">{t("structuredWorkout.completion_unavailable")}</p>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[13px]">
        {session?.activity_id != null && <Link className="text-link" to={`/app/activities/${session.activity_id}`}>{t("athlete.view_activity")} ↗</Link>}
        <Link className="text-link" to={`/app?date=${date}`}>{t("athlete.your_day")}</Link>
        <Button variant="ghost" disabled={day.isFetching} onClick={() => void day.refetch()}>{t("structuredWorkout.completion_retry")}</Button>
      </div>
    </>}
  </Card>;
}

export default function WorkoutDetail() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["structured-workout", uid, id], queryFn: () => api.get<WorkoutDetailResponse>(`/athlete/planned-sessions/${id}/workout`), enabled: /^\d+$/.test(id) });
  const [editing, setEditing] = useState<StructuredWorkout | null>(null);
  const [baseline, setBaseline] = useState("");
  const [draft, setDraft] = useState<WorkoutDraft | null>(null);
  useEffect(() => { if (query.data) setDraft(query.data.pending_draft ?? null); }, [query.dataUpdatedAt]);
  const [saved, setSaved] = useState(false);
  const [expectedPlanRevision, setExpectedPlanRevision] = useState(0);
  const [expectedWorkoutRevision, setExpectedWorkoutRevision] = useState(0);
  const dirty = !!editing && JSON.stringify(editing) !== baseline;
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const click = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null;
      if (link && link.origin === window.location.origin && !link.download && link.target !== '_blank' && link.href !== window.location.href && !window.confirm(t('athlete.leave_unsaved'))) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    window.addEventListener("beforeunload", guard); document.addEventListener('click',click,true);
    return () => {window.removeEventListener("beforeunload", guard);document.removeEventListener('click',click,true);};
  }, [dirty]);
  const create = useMutation({ mutationFn: () => api.post<WorkoutDraft>(`/athlete/planned-sessions/${id}/workout-drafts`, { expected_plan_revision: expectedPlanRevision, expected_workout_revision: expectedWorkoutRevision, structure: editing }), onSuccess: next => { setDraft(next); setEditing(null); setSaved(false); } });
  const confirm = useMutation({ mutationFn: () => api.post<WorkoutReceipt>(`/athlete/workout-drafts/${draft!.id}/confirm`, { payload_hash: draft!.payload_hash }), onSuccess: () => { setDraft(null); setEditing(null); setSaved(true); ["structured-workout", "athlete-day", "plan-drafts", "athlete-sport-overview", "lab"].forEach(key => qc.invalidateQueries({ queryKey: [key] })); } });
  const pending = create.isPending || confirm.isPending;
  function begin() {
    if (!query.data) return;
    const structure = draft?.structure ?? query.data.workout?.structure ?? { title: query.data.session.session_type ?? "", objective: query.data.session.description ?? "", steps: [] };
    setEditing(structuredClone(structure)); setBaseline(JSON.stringify(structure)); setExpectedPlanRevision(query.data.plan_revision); setExpectedWorkoutRevision(query.data.workout?.revision ?? 0); setSaved(false); create.reset(); confirm.reset();
  }
  function edit(next: StructuredWorkout) { setEditing(next); setSaved(false); }
  if (query.isLoading) return <Loading />;
  if (!query.data || query.isError || query.data.planned_session_id !== Number(id)) return <ErrorNote message={t("structuredWorkout.load_error")} />;
  const data = query.data;
  const show = editing ?? draft?.structure ?? data.workout?.structure;
  const error = create.error ?? confirm.error;
  const errorMessage = error instanceof ApiError && error.status === 409 ? t("structuredWorkout.conflict") : error ? t("structuredWorkout.save_error") : null;
  return <div className="space-y-6"><PageHeader title={show?.title || data.session.session_type || t("structuredWorkout.title")} subtitle={`${data.session.date} · ${friendlyDiscipline(data.session.discipline, t)}`} actions={<Link className="text-link inline-flex min-h-11 items-center text-[13px]" to="/app/coach" state={{coachContext:{userId:uid,date:data.session.date,plannedSessionId:data.planned_session_id}}}>{t("dailyFlow.ask_workout")} ↗</Link>} />
    <Card><CardHeader title={<h2>{t("structuredWorkout.instructions_title")}</h2>} right={data.protected && <Badge>{t("athlete.protected")}</Badge>} />{(show || editing) && <p className="mb-4 text-[13px] text-muted">{t("structuredWorkout.scope")}</p>}
      {!data.editable && <p role="status" className="mb-4 text-[13px]">{t("structuredWorkout.blocked_" + (data.edit_block_reason ?? "history"))}</p>}
      <fieldset disabled={pending}>{editing ? <div className="space-y-4"><Input label={t("athlete.plan_title")} value={editing.title} onChange={title => edit({ ...editing, title })} /><Input label={t("structuredWorkout.objective")} value={editing.objective} onChange={objective => edit({ ...editing, objective })} />{editing.steps.map((step, index) => <StepEditor key={step.id} step={step} index={index} onChange={value => edit({ ...editing, steps: editing.steps.map(old => old.id === step.id ? value : old) })} onRemove={() => edit({ ...editing, steps: editing.steps.filter(old => old.id !== step.id) })} />)}<Button variant="ghost" onClick={() => edit({ ...editing, steps: [...editing.steps, freshStep()] })}>{t("structuredWorkout.add_block")}</Button><p className="text-[12px] text-muted">{t("structuredWorkout.target_note")}</p></div> : show ? <><p className="mb-4 text-[14px]">{show.objective}</p><ol className="space-y-4">{show.steps.map((step, index) => <StepSummary key={step.id} step={step} number={String(index + 1)} />)}</ol></> : <div className="space-y-3"><p className="whitespace-pre-wrap text-[14px]">{data.session.description || t("structuredWorkout.no_structure")}</p>{data.session.duration_min != null && <p className="text-[13px] text-muted">{t("athlete.duration_minutes", { count: data.session.duration_min })}</p>}</div>}
      </fieldset>
      {draft && <p className="mt-4 text-[13px]">{t("structuredWorkout.duration_review",{seconds:draft.duration_total_s??t("design.not_specified")})}</p>}
      <p role="status" className="mt-5 text-[13px] font-medium">{t(pending ? "structuredWorkout.saving" : saved ? "structuredWorkout.saved" : editing && dirty ? "structuredWorkout.unsaved" : draft ? "structuredWorkout.review_scope" : "structuredWorkout.read_scope")}</p>
      <div className="mt-4 flex flex-wrap gap-3">{editing ? <><Button disabled={pending || !data.editable || !editing.steps.length || editing.steps.some(stepError)} onClick={() => create.mutate()}>{t("structuredWorkout.prepare_review")}</Button><Button variant="ghost" disabled={pending} onClick={() => { if (dirty && !window.confirm(t("athlete.leave_unsaved"))) return; setEditing(null); }}>{t("common.cancel")}</Button></> : <>{data.editable && <Button variant={draft ? "ghost" : "primary"} disabled={pending} onClick={begin}>{t(draft ? "structuredWorkout.revise" : "structuredWorkout.edit")}</Button>}{draft && <Button disabled={pending || !data.editable} onClick={() => confirm.mutate()}>{t("structuredWorkout.confirm")}</Button>}</>}</div>
      {errorMessage && <p role="alert" className="mt-4 text-[13px] text-alertText">{errorMessage}</p>}
      {error && <Button className="mt-3" variant="ghost" disabled={pending} onClick={async () => { if (editing && dirty && !window.confirm(t("athlete.leave_unsaved"))) return; const next = await query.refetch(); if (next.data) { setEditing(null); setDraft(null); create.reset(); confirm.reset(); setSaved(false); } }}>{t("structuredWorkout.reload")}</Button>}
    </Card>
    <WorkoutCompletion key={`${uid}:${id}:${data.session.date}`} sessionId={data.planned_session_id} date={data.session.date} />
    {!!data.education.length && !editing && !draft && <Card><CardHeader title={<h2>{t("structuredWorkout.education")}</h2>} /><p className="mb-4 text-[13px] text-muted">{t("structuredWorkout.education_note")}</p><div className="space-y-5">{data.education.map((item,index) => <section key={item.id} className={`border-t border-hairline pt-4 ${item.parent_id ? "ml-4 border-l pl-4" : ""}`}><h3 className="text-[15px] font-medium">{item.number ?? index+1}. {t("structuredWorkout.kind_" + item.kind)} · {item.objective}</h3>{item.description && <p className="mt-2 text-[13px]">{item.description}</p>}{item.kind === "repeat" ? <p className="mt-2 text-[13px]">{t("structuredWorkout.repeat_count")}: {item.repetitions}</p> : <div className="mt-2 space-y-1 text-[13px]"><p>{item.duration_s != null ? fmtDuration(item.duration_s) : item.distance_m != null ? `${item.distance_m} m` : t("structuredWorkout.unspecified_stop")}</p><p>{item.target ? `${t("structuredWorkout.target_"+item.target.kind)}: ${item.target.lower}–${item.target.upper}` : t("structuredWorkout.no_target")}</p>{item.kind === "strength" && <p>{item.exercise} · {t("structuredWorkout.strength_summary",{sets:item.sets??"—",reps:item.reps??"—",load:item.load_kg??"—"})}</p>}</div>}<p className="mt-2 text-[14px]">{item.execution}</p><p className="mt-2 text-[12px] text-muted">{item.limitation}</p><details className="mt-3"><summary className="cursor-pointer text-[13px]">{t("structuredWorkout.mistakes_alternatives")}</summary>{item.common_mistake && <p className="mt-3 text-[13px]">{item.common_mistake}</p>}{item.conservative_alternative && <p className="mt-3 text-[13px]">{item.conservative_alternative}</p>}{!item.common_mistake && !item.conservative_alternative && <p className="mt-3 text-[13px]">{t("structuredWorkout.conservative_note")}</p>}</details></section>)}</div></Card>}
    {!!data.history?.length && <Card><h2 className="mb-4 text-[15px] font-medium">{t("structuredWorkout.history")}</h2>{data.history.map(version=><details key={version.id} className="mt-3 border-t border-hairline pt-3"><summary className="cursor-pointer text-[13px]">{t("structuredWorkout.version",{revision:version.revision})} · {version.structure.title}</summary><ol className="mt-4 space-y-4">{version.structure.steps.map((step,index)=><StepSummary key={step.id} step={step} number={String(index+1)}/>)}</ol></details>)}</Card>}
    <Card><h2 className="mb-3 text-[15px] font-medium">{t("structuredWorkout.export")}</h2><p className="mb-4 text-[13px] text-muted">{t("structuredWorkout.export_note")}</p><a className="text-link" href={`/lab/workouts/${id}/export`} download>{t("structuredWorkout.export")}</a></Card>
    <div className="flex flex-wrap gap-4 text-[13px]"><Link className="text-link" to={`/app/calendar?date=${data.session.date}`}>{t("structuredWorkout.view_calendar")}</Link><Link className="text-link" to={`/app?date=${data.session.date}`}>{t("athlete.your_day")}</Link></div>
  </div>;
}
