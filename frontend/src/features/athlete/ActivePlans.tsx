import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Badge, Button, Card, Loading, friendlyDiscipline } from "../../components/kit";

export interface ActivePlan {
  id: number; title: string | null; revision: number; start_date: string; end_date: string | null;
  protected: boolean; can_adapt: boolean;
  sessions: { id: number; date: string; discipline: string | null; session_type: string | null; duration_min: number | null; target_load: number | null; editable: boolean; block_reason: string | null }[];
}
export interface ActivePlansResponse { date: string; today: string; plans: ActivePlan[] }
export function useActivePlans(uid: number | undefined, date: string, enabled = true) {
  return useQuery({ queryKey: ["active-plans", uid, date], queryFn: () => api.get<ActivePlansResponse>("/athlete/plans?date=" + date), enabled: enabled && uid != null, staleTime: 0, retry: false });
}
export function ActivePlans({ uid, date, query }: { uid: number | undefined; date: string; query: ReturnType<typeof useActivePlans> }) {
  const { t } = useTranslation();
  return <section aria-label={t("workflowFlow.current_plan")} className="space-y-3">
    {query.isLoading && <Loading />}
    {query.isError && <Card><p role="status">{t("workflowFlow.plan_load_error")}</p><Button variant="ghost" disabled={query.isFetching} onClick={() => void query.refetch()}>{t("common.retry")}</Button></Card>}
    {query.data?.plans.map(plan => <Card key={plan.id}>
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-[16px] font-medium">{plan.title || t("workflowFlow.current_plan")}</h2><Badge>{t("workflowFlow.current_plan")}</Badge></div>
      <p className="mt-2 text-[13px] text-muted">{t("workflowFlow.adapt_note")}</p>
      <div className="mt-4 flex flex-wrap gap-4">{plan.can_adapt && !query.isError && <Link className="text-link inline-flex min-h-11 items-center" to="/app/coach" state={{coachContext:{userId:uid,date,planId:plan.id}}}>{t("workflowFlow.adjust_loads")} ↗</Link>}<Link className="text-link inline-flex min-h-11 items-center" to={`/app/calendar?date=${date}`}>{t("structuredWorkout.view_calendar")}</Link></div>
      {!plan.can_adapt && <p className="mt-3 text-[13px] text-muted">{t("workflowFlow.no_editable")}</p>}
      <h3 className="mt-4 text-[13px] font-medium">{t("workflowFlow.next_sessions")}</h3>
      {!plan.sessions.length && <p className="mt-2 text-[13px] text-muted">{t("workflowFlow.no_sessions")}</p>}
      <ul className="mt-2 divide-y divide-hairline">{plan.sessions.slice(0, 8).map(session => <li key={session.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-[13px]">
        <Link className="text-link inline-flex min-h-11 items-center" to={`/app/workouts/${session.id}`}>{session.date} · {session.session_type || friendlyDiscipline(session.discipline,t)}{session.duration_min != null ? ` · ${t("athlete.duration_minutes",{count:session.duration_min})}` : ""}</Link>
        {session.block_reason && <span className="text-muted">{t("workflowFlow.block_"+session.block_reason)}</span>}
      </li>)}</ul>
    </Card>)}
  </section>;
}
