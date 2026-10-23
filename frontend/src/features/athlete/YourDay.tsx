import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { localDay, useUnits } from "../../components/data";
import { Badge, Button, Card, ErrorNote, Loading, Select, SportIcon, fmtDuration, fmtNum, friendlyDiscipline } from "../../components/kit";
import { SessionCheckin } from "./SessionCheckin";
import type { AthleteDay, DayActivity } from "./types";

export function useAthleteDay(date?: string) {
  const me = useUi(s => s.me);
  const day = date ?? localDay(me?.timezone);
  return useQuery({ queryKey: ["athlete-day", me?.user_id, day], queryFn: () => api.get<AthleteDay>("/athlete/day?date="+day), refetchInterval: 300000 });
}

function RecordedActivity({ activity, day }: { activity: DayActivity; day: AthleteDay }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [selected, setSelected] = useState("");
  const association = useMutation({ mutationFn: (id: number | null) => api.put(`/athlete/activities/${activity.id}/association`, { planned_session_id: id }), onSuccess: () => { ["athlete-day", "athlete-sport-overview", "structured-workout"].forEach(key => qc.invalidateQueries({queryKey:[key]})); } });
  return <li className="border-t border-hairline py-4">
    <div className="flex items-start gap-3"><SportIcon discipline={activity.discipline} size={22} /><div className="min-w-0 flex-1">
      <Link className="text-link font-medium" to={`/app/activities/${activity.id}`}>{friendlyDiscipline(activity.discipline, t)} ↗</Link>
      <p className="mt-1 text-[12px] text-muted">{new Date(activity.start_time).toLocaleTimeString(i18n.language, { timeZone: day.timezone, hour: "2-digit", minute: "2-digit" })} · {fmtDuration(activity.duration_s)}</p>
    </div><Badge tone={activity.association === "confirmed" ? "positive" : "neutral"}>{t("athlete.association_"+activity.association)}</Badge></div>
    {activity.comparison && <p className="mt-3 text-[13px] text-muted">{t("athlete.duration_comparison", { planned: fmtNum(activity.comparison.target_duration_min), recorded: fmtNum(activity.comparison.recorded_duration_min), delta: fmtNum(activity.comparison.duration_delta_min) })}</p>}
    {!activity.planned_session_id && activity.association !== "independent" && <div className="mt-3 space-y-3">
      <p className="text-[12px] text-muted">{t("athlete.association_explanation")}</p>
      {!!day.sessions.filter(s => !s.activity_id).length && <div className="flex flex-wrap items-end gap-3"><Select label={t("athlete.associate_session")} value={selected} onChange={setSelected} options={[{ value: "", label: t("athlete.choose_session") }, ...day.sessions.filter(s => !s.activity_id).map(s => ({ value: String(s.id), label: `${friendlyDiscipline(s.discipline, t)} · ${s.start_time?.slice(0,5) ?? "—"} · ${fmtNum(s.duration_min)} min · #${s.id}` }))]} /><Button variant="ghost" disabled={!selected || association.isPending} onClick={() => association.mutate(Number(selected))}>{t("athlete.confirm_association")}</Button></div>}
      <div className="flex flex-wrap gap-3"><Button variant="ghost" disabled={association.isPending} onClick={() => association.mutate(null)}>{t("athlete.keep_independent")}</Button><Link className="text-link self-center" to="/app/coach?tab=changes">{t("athlete.review_plan")}</Link></div>
    </div>}
    {association.isError && <ErrorNote />}
    <SessionCheckin activityId={activity.id} plannedSessionId={activity.planned_session_id ?? undefined} checkin={activity.checkin} />
  </li>;
}

export function YourDay({ date, activityId }: { date?: string; activityId?: number }) {
  const { t, i18n } = useTranslation();
  const data = useAthleteDay(date);
  const qc = useQueryClient();
  const units = useUnits();
  const protect = useMutation({ mutationFn: ({ id, revision, value, wholePlan }: { id: number; revision: number; value: boolean; wholePlan?: boolean }) => api.put(`/lab/${wholePlan ? "plans" : "planned-sessions"}/${id}/protection`, { protected: value, expected_plan_revision: revision }), onSuccess: () => { ["athlete-day", "athlete-sport-overview", "structured-workout"].forEach(key => qc.invalidateQueries({queryKey:[key]})); } });
  if (data.isLoading) return <Loading />;
  if (!data.data || data.isError) return <ErrorNote />;
  const day = data.data;
  const context = day.planning_context;
  const contextLink = context?.state === "plan_draft" ? `/app/training?tab=planning#${context.draft_template_id ? "template-"+context.draft_template_id : "document-"+context.draft_document_id}` : context?.state === "template_ready" ? `/app/training?tab=planning#template-${context.template_id}` : context?.state === "profile_ready" ? "/app/training?tab=planning" : "/app/settings?tab=profile";
  const gymLink = `/app/training?date=${day.date}#gym-session`;
  const recorded = activityId ? day.activities.filter(a => a.id === activityId) : day.activities;
  const sessions = activityId ? day.sessions.filter(s => s.activity_id === activityId) : day.sessions;
  const remaining = sessions.filter(s => ["planned", "modified", "partial"].includes(s.status));
  const reportedCompleted = sessions.filter(s => s.status === "completed");
  const remainingGym = day.legacy_gym_sessions.filter(g => g.status !== "completed");
  const remainingCount = remaining.length + remainingGym.length;
  const hasCompleted = recorded.length > 0 || reportedCompleted.length > 0 || day.legacy_gym_sessions.some(g => g.status === "completed");
  const hasPartial = remainingGym.some(g => g.status === "active") || remaining.some(s => s.status === "partial") || recorded.some(a => a.checkin?.status === "partial");
  const rest = context?.state === "active_rest_day" && !sessions.length && !recorded.length && !day.legacy_gym_sessions.length;
  const state = hasPartial || (hasCompleted && remainingCount > 0) ? "in_progress"
    : hasCompleted ? "completed"
    : sessions.length > 0 && sessions.every(s => s.status === "skipped") && !day.legacy_gym_sessions.length ? "skipped"
    : sessions.length || day.legacy_gym_sessions.length ? "planned" : rest ? "rest" : "unscheduled";
  const next = remaining[0] ?? (remainingGym.length ? undefined : sessions[0]);
  const title = recorded.length > 1 ? t("betaDaily.recorded_count", { count: recorded.length })
    : recorded.length === 1 ? friendlyDiscipline(recorded[0].discipline, t)
    : next ? next.session_type || friendlyDiscipline(next.discipline, t)
    : remainingGym[0]?.title ?? day.legacy_gym_sessions[0]?.title ?? t(rest ? "betaDaily.rest_title" : "betaDaily.unscheduled_title");
  const duration = recorded.length ? day.totals.duration_s?.value ?? recorded.reduce((sum, a) => sum + a.duration_s, 0) : next?.duration_min == null ? null : next.duration_min * 60;
  // Cross-sport distances cannot be combined into a meaningful headline total.
  const distance = recorded.length ? day.totals.distance_m?.value ?? (recorded.length === 1 ? recorded[0].distance_m : null) : next?.distance_m;
  const emptyDay = !sessions.length && !recorded.length && !day.legacy_gym_sessions.length;
  const cta = remaining[0] ? { to: `/app/workouts/${remaining[0].id}`, label: t("betaDaily.view_workout") }
    : remainingGym.length ? { to: gymLink, label: t("betaDaily.view_workout") }
    : recorded.length ? { to: recorded.length === 1 ? `/app/activities/${recorded[0].id}` : "/app/activities", label: t(recorded.length === 1 ? "athlete.view_activity" : "betaDaily.view_activities") }
    : next ? { to: `/app/workouts/${next.id}`, label: t("betaDaily.view_workout") }
    : day.legacy_gym_sessions.length ? { to: gymLink, label: t("betaDaily.view_workout") }
    : !day.is_historical && !rest ? { to: contextLink, label: t(context?.state === "plan_draft" ? "athlete.review_draft" : context?.state === "profile_ready" || context?.state === "template_ready" ? "athlete.create_review_plan" : "athlete.build_context") }
    : null;
  return <Card className="!p-5 sm:!p-6">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-[15px] font-medium">{t(activityId ? "athlete.session_context" : "athlete.your_day")}</h2>
      <span className="text-[12px] text-muted">{new Date(day.date+"T12:00:00Z").toLocaleDateString(i18n.language, { timeZone: "UTC", dateStyle: "medium" })}</span>
    </div>
    {!activityId && <div data-testid="daily-summary" className="mt-3">
      <div className="flex flex-wrap items-center gap-2"><Badge tone={state === "completed" ? "positive" : "neutral"}>{t(state === "skipped" ? "athlete.state_skipped" : "betaDaily.state_"+state)}</Badge>{day.is_historical && <span className="text-[12px] text-muted">{t("design.history")}</span>}</div>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0"><p className="text-[20px] font-medium leading-snug">{title}</p>
          {remainingCount > 0 && recorded.length > 0 && <p className="mt-1 text-[12px] text-muted">{t("betaDaily.remaining_count", { count: remainingCount })} · {friendlyDiscipline(remaining[0]?.discipline ?? "strength", t)}{remaining[0]?.start_time ? ` · ${remaining[0].start_time.slice(0,5)}` : ""}</p>}
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink2">
            {duration != null && <span>{t(recorded.length ? "athlete.total_duration_s" : "betaDaily.planned_duration")}: <span className="num font-medium text-ink">{fmtDuration(duration)}</span></span>}
            {distance != null && <span>{t(recorded.length ? "athlete.total_distance_m" : "betaDaily.planned_distance")}: <span className="num font-medium text-ink">{fmtNum(units.distance(distance), 1)} {units.distanceUnit}</span></span>}
          </div>
        </div>
        {cta && <Link className="text-link min-h-11 inline-flex items-center font-medium" to={cta.to}>{cta.label} ↗</Link>}
      </div>
      {recorded.length > 1 && <ul aria-label={t("betaDaily.session_summary")} className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-muted">{recorded.slice(0,4).map(a => <li key={a.id}>{friendlyDiscipline(a.discipline, t)} · {fmtDuration(a.duration_s)}</li>)}{recorded.length > 4 && <li>{t("betaDaily.more_count", { count: recorded.length - 4 })}</li>}</ul>}
      {!recorded.length && sessions.length > 1 && <ul aria-label={t("betaDaily.session_summary")} className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-muted">{sessions.slice(0,4).map(s => <li key={s.id}>{friendlyDiscipline(s.discipline, t)} · {t("athlete.state_"+s.status)}{s.start_time ? ` · ${s.start_time.slice(0,5)}` : ""}</li>)}{sessions.length > 4 && <li>{t("betaDaily.more_count", { count: sessions.length - 4 })}</li>}</ul>}
      {emptyDay && <p className="mt-2 text-[13px] text-muted">{t(day.is_historical ? "athlete.context_historical_empty" : context ? "athlete.context_" + context.state : "athlete.no_prescription")}</p>}
    </div>}
    <details open={activityId ? true : undefined} className="mt-3 border-t border-hairline pt-3" data-testid="daily-details">
      <summary className="cursor-pointer text-[13px] text-ink2">{t("betaDaily.details")}</summary>
      <div className="mt-4">
      {!activityId && <div className="mb-4 flex flex-wrap gap-3">{(day.focus_configuration?.effective_priorities ?? day.training_focus).map((focus, i) => <Badge key={focus}>{day.focus_configuration?.focus_mode !== "balanced" && `${i+1} · `}{t("athlete.focus_"+focus)}</Badge>)}</div>}
    {!!recorded.length && <section aria-label={t("athlete.recorded_sessions")} className="mt-4"><h3 className="mb-2 text-[13px] font-medium">{t("athlete.recorded_sessions")}</h3><ul>{recorded.map(a => <RecordedActivity key={a.id} activity={a} day={day} />)}</ul></section>}
    {!!sessions.length && <section aria-label={t("athlete.planned_sessions")}><h3 className="mb-3 text-[13px] font-medium">{t("athlete.planned_sessions")}</h3><ul>
      {sessions.map(s => <li key={s.id} className="border-t border-hairline py-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-[15px] font-medium">{friendlyDiscipline(s.discipline, t)}{s.start_time ? ` · ${s.start_time.slice(0,5)}` : ""}</p><p className="mt-1 text-[12px] text-muted">{s.duration_min == null ? t("athlete.duration_unknown") : t("athlete.duration_minutes", { count: s.duration_min })}{s.description ? ` · ${s.description}` : ""}</p>{s.plan_title && <p className="mt-1 text-[12px] text-muted">{s.plan_title}</p>}</div><div className="flex shrink-0 flex-col items-end gap-2"><Badge tone={s.status === "completed" ? "positive" : "neutral"}>{t("athlete.state_"+s.status)}</Badge>{s.protected && <Badge>{t("athlete.protected")}</Badge>}</div></div>
        {s.activity_id ? <Link className="text-link mt-3 inline-block" to={`/app/activities/${s.activity_id}`}>{t("athlete.view_activity")} ↗</Link> : <SessionCheckin plannedSessionId={s.id} checkin={s.checkin} />}
        <Link className="text-link mt-3 mr-4 inline-block text-[12px]" to={`/app/workouts/${s.id}`}>{t("athlete.workout_detail")} ↗</Link>
        <button className="text-link mt-3 text-[12px]" disabled={protect.isPending} onClick={() => protect.mutate({ id: s.plan_protected ? s.plan_id : s.id, revision: s.plan_revision, value: s.plan_protected ? false : !s.workout_protected, wholePlan: s.plan_protected })}>{t(s.plan_protected ? "athlete.unprotect_plan" : s.workout_protected ? "athlete.unprotect_workout" : "athlete.protect_workout")}</button>
      </li>)}
    </ul></section>}
    {!activityId && day.legacy_gym_sessions.map(g => <div className="border-t border-hairline py-4 text-[13px]" key={g.gym_day_plan_id}><Link className="text-link" to={gymLink}>{g.title} ↗</Link><p className="mt-1 text-muted">{t("athlete.legacy_gym_context")}</p></div>)}
    {protect.isError && <ErrorNote />}
    {!activityId && !!day.activities.length && <div className="mt-4 border-t border-hairline pt-4"><div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {Object.entries(day.totals).map(([key, total]) => <div key={key} className="text-[12px]"><p className="text-muted">{t("athlete.total_"+key)}</p><p className="num mt-1 text-[18px]">{key === "duration_s" ? fmtDuration(total.value) : key === "distance_m" ? `${fmtNum(units.distance(total.value), 1)} ${units.distanceUnit}` : key === "elevation_gain_m" ? `${fmtNum(units.elevation(total.value))} ${units.elevationUnit}` : `${fmtNum(total.value, 1)} ${total.unit}`}</p><p className="mt-1 text-muted">{t("athlete.coverage_sessions", { known: total.available_sessions, total: total.total_sessions })}</p></div>)}
    </div>{day.sport_totals && Object.keys(day.sport_totals).length > 1 && <section className="mt-4" aria-label={t("athlete.per_sport_totals")}><h3 className="text-[13px] font-medium">{t("athlete.per_sport_totals")}</h3><ul className="mt-2 space-y-2">{Object.entries(day.sport_totals).map(([sport, totals]) => <li className="text-[13px]" key={sport}>{friendlyDiscipline(sport, t)} · {fmtDuration(totals.duration_s.value)}{totals.distance_m.value != null && <> · {fmtNum(units.distance(totals.distance_m.value), 1)} {units.distanceUnit}</>}</li>)}</ul></section>}<p className="mt-4 text-[12px] text-muted">{t("athlete.load_scales_note")}</p></div>}
      </div>
    </details>
  </Card>;
}
