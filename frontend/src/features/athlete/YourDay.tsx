import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { localDay, useUnits } from "../../components/data";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Loading, Select, SportIcon, fmtDuration, fmtNum, friendlyDiscipline } from "../../components/kit";
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
  const association = useMutation({ mutationFn: (id: number | null) => api.put(`/athlete/activities/${activity.id}/association`, { planned_session_id: id }), onSuccess: () => qc.invalidateQueries({ queryKey: ["athlete-day"] }) });
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
  const protect = useMutation({ mutationFn: ({ id, revision, value, wholePlan }: { id: number; revision: number; value: boolean; wholePlan?: boolean }) => api.put(`/lab/${wholePlan ? "plans" : "planned-sessions"}/${id}/protection`, { protected: value, expected_plan_revision: revision }), onSuccess: () => qc.invalidateQueries({ queryKey: ["athlete-day"] }) });
  if (data.isLoading) return <Loading />;
  if (!data.data || data.isError) return <ErrorNote />;
  const day = data.data;
  const recorded = activityId ? day.activities.filter(a => a.id === activityId) : day.activities;
  const sessions = activityId ? day.sessions.filter(s => s.activity_id === activityId) : day.sessions;
  return <Card className="!p-5 sm:!p-7">
    <CardHeader title={t(activityId ? "athlete.session_context" : "athlete.your_day")} right={<span className="text-[12px] text-muted">{new Date(day.date+"T12:00:00Z").toLocaleDateString(i18n.language, { timeZone: "UTC", dateStyle: "medium" })}</span>} />
    {!activityId && <><p className="mb-4 text-[14px] text-muted">{t("athlete.day_"+day.state)}</p>
      <div className="mb-4 flex flex-wrap gap-3">{day.training_focus.map((focus, i) => <Badge key={focus}>{i+1} · {t("athlete.focus_"+focus)}</Badge>)}</div></>}
    {!!sessions.length && <section aria-label={t("athlete.planned_sessions")}><h3 className="mb-3 text-[13px] font-medium">{t("athlete.planned_sessions")}</h3><ul>
      {sessions.map(s => <li key={s.id} className="border-t border-hairline py-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="text-[15px] font-medium">{friendlyDiscipline(s.discipline, t)}{s.start_time ? ` · ${s.start_time.slice(0,5)}` : ""}</p><p className="mt-1 text-[12px] text-muted">{s.duration_min == null ? t("athlete.duration_unknown") : t("athlete.duration_minutes", { count: s.duration_min })}{s.description ? ` · ${s.description}` : ""}</p>{s.plan_title && <p className="mt-1 text-[12px] text-muted">{s.plan_title}</p>}</div><div className="flex shrink-0 flex-col items-end gap-2"><Badge tone={s.status === "completed" ? "positive" : "neutral"}>{t("athlete.state_"+s.status)}</Badge>{s.protected && <Badge>{t("athlete.protected")}</Badge>}</div></div>
        {s.activity_id ? <Link className="text-link mt-3 inline-block" to={`/app/activities/${s.activity_id}`}>{t("athlete.view_activity")} ↗</Link> : <SessionCheckin plannedSessionId={s.id} checkin={s.checkin} />}
        <button className="text-link mt-3 text-[12px]" disabled={protect.isPending} onClick={() => protect.mutate({ id: s.plan_protected ? s.plan_id : s.id, revision: s.plan_revision, value: s.plan_protected ? false : !s.workout_protected, wholePlan: s.plan_protected })}>{t(s.plan_protected ? "athlete.unprotect_plan" : s.workout_protected ? "athlete.unprotect_workout" : "athlete.protect_workout")}</button>
      </li>)}
    </ul></section>}
    {!activityId && day.legacy_gym_sessions.map(g => <div className="border-t border-hairline py-4 text-[13px]" key={g.gym_day_plan_id}><Link className="text-link" to="/app/training">{g.title} ↗</Link><p className="mt-1 text-muted">{t("athlete.legacy_gym_context")}</p></div>)}
    {protect.isError && <ErrorNote />}
    {!!recorded.length && <section aria-label={t("athlete.recorded_sessions")} className="mt-4"><h3 className="mb-2 text-[13px] font-medium">{t("athlete.recorded_sessions")}</h3><ul>{recorded.map(a => <RecordedActivity key={a.id} activity={a} day={day} />)}</ul></section>}
    {!activityId && !day.sessions.length && !day.activities.length && !day.legacy_gym_sessions.length && <Empty action={<Link className="text-link" to="/app/settings?tab=profile">{t("athlete.build_context")} ↗</Link>}>{t("athlete.no_prescription")}</Empty>}
    {!activityId && !!day.activities.length && <div className="mt-4 border-t border-hairline pt-4"><div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {Object.entries(day.totals).map(([key, total]) => <div key={key} className="text-[12px]"><p className="text-muted">{t("athlete.total_"+key)}</p><p className="num mt-1 text-[18px]">{key === "duration_s" ? fmtDuration(total.value) : key === "distance_m" ? `${fmtNum(units.distance(total.value), 1)} ${units.distanceUnit}` : key === "elevation_gain_m" ? `${fmtNum(units.elevation(total.value))} ${units.elevationUnit}` : `${fmtNum(total.value, 1)} ${total.unit}`}</p><p className="mt-1 text-muted">{t("athlete.coverage_sessions", { known: total.available_sessions, total: total.total_sessions })}</p></div>)}
    </div><p className="mt-4 text-[12px] text-muted">{t("athlete.load_scales_note")}</p></div>}
  </Card>;
}
