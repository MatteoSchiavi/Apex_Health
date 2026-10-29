import { YourDay } from "../athlete/YourDay";
import type { AthleteDay } from "../athlete/types";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type Overview, type MetricTrend } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Card,
  CardHeader,
  DeltaChip,
  Empty,
  ErrorNote,
  Loading,
  Segmented,
  StatPod,
  SportIcon,
  Sparkline,
  ZoneBar,
  fmtNum,
  fmtHours,
  fmtDuration,
  friendlyDiscipline,
} from "../../components/kit";
import { TrendChart } from "../../components/charts/TrendChart";
import { localDay, shiftDay, useUnits } from "../../components/data";
import { MetricDirection, PersonalRange, RANGE_METRICS } from "../../components/MetricInterpretation";
import { METRIC_LABELS } from "../../components/data";
import { ActivityCalendar } from "./ActivityCalendar";
import { DecisionCard } from "../lab/DecisionCard";
import { useEffect, useState } from "react";

function More({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="text-link">
      {children}
      <ArrowRight size={15} />
    </Link>
  );
}
function latestPoint(data: MetricTrend | undefined, end: string) {
  return [...(data?.points ?? [])].reverse().find(point => point.value != null && point.date <= end);
}

function ScoreCard({ metric, score, date, displayedDay, allowLatest }: { metric: string; score: Overview["readiness"]; date: string; displayedDay: string; allowLatest: boolean }) {
  const { t } = useTranslation();
  const history = useQuery({
    queryKey: ["metric", metric, "90", date],
    queryFn: () => api.get<MetricTrend>(`/metrics/${metric}?days=90&end=${date}`),
    enabled: allowLatest && score.value == null,
    refetchInterval: 300_000,
  });
  const latest = allowLatest && score.value == null ? latestPoint(history.data, date) : undefined;
  const value = score.value ?? latest?.value ?? null;
  const sourceDay = score.value != null ? date : latest?.date;
  return <div className="min-w-0">
    <Link to={`/app/biometrics/${metric}`} className="block rounded-control py-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
      <div className="stat-pod !py-0">
        <p className="text-[12px] text-muted">{t(METRIC_LABELS[metric])}</p>
        <div className="num mt-1 flex flex-wrap items-baseline gap-x-2 text-[25px] font-medium tracking-[-.045em]">
          <span data-testid="score-value">{fmtNum(value)}{value != null && <span className="ml-1 text-[12px] font-normal tracking-normal text-muted">/100</span>}</span>
          {score.value != null && <DeltaChip delta={score.delta_7d} compact />}
        </div>
      </div>
      <p className="mt-2 text-[12px] text-muted">{t(value == null ? allowLatest && history.isLoading ? "common.loading" : allowLatest && history.isError ? "overviewLatest.unavailable" : "betaDaily.score_missing" : metric === "provider_sleep_score" ? "metricView.provider_sleep_score" : "metricView.estimates")}</p>
      {allowLatest && sourceDay && sourceDay !== displayedDay && <p className="mt-1 text-[12px] text-muted">{t("overviewLatest.as_of", {date: sourceDay})}</p>}
    </Link>
  </div>;
}

function useLatestLoad(o: Overview | undefined, allowLatest: boolean) {
  // Keep the three load numbers, their units and their chart on one snapshot.
  // Never replace any load measurement already available for the selected day.
  const date = o?.date ?? "";
  const missing = !!o && o.acute_load == null && o.chronic_load == null && o.acwr == null;
  const history = useQuery({
    queryKey: ["metric", "acute_load", "90", date],
    queryFn: () => api.get<MetricTrend>(`/metrics/acute_load?days=90&end=${date}`),
    enabled: allowLatest && missing,
    refetchInterval: 300_000,
  });
  const day = latestPoint(history.data, date)?.date;
  const snapshot = useQuery({
    queryKey: ["overview", day],
    queryFn: () => api.get<Overview>(`/dashboard/overview?date=${day}`),
    enabled: allowLatest && missing && !!day && day < date,
    refetchInterval: 300_000,
  });
  return allowLatest && missing && day && day < date && snapshot.data?.date === day ? snapshot.data : o;
}

function LoadPanel({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const [metric, setMetric] = useState("acute_load");
  const trend = useQuery({
    queryKey: ["metric", metric, 28, o.date],
    queryFn: () =>
      api.get<MetricTrend>("/metrics/" + metric + "?days=28&end=" + o.date),
  });
  return (
    <Card>
      <CardHeader
        title={t("design.training_load")}
        right={<More to="/app/training">{t("design.view_training")}</More>}
      />
      <div className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatPod
          label={t("betaDaily.acute_scope")}
          value={fmtNum(o.acute_load, 1)}
          unit={o.load_metadata?.unit ?? t("betaDaily.load_unit_unknown")}
        />
        <StatPod
          label={t("betaDaily.chronic_scope")}
          value={fmtNum(o.chronic_load, 1)}
          unit={o.load_metadata?.unit ?? t("betaDaily.load_unit_unknown")}
        />
        <StatPod
          label="ACWR"
          value={fmtNum(o.acwr, 2)}
          unit={t("design.ratio")}
        />
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <span className="text-[12px] text-muted">{t("design.days28")}</span>
        <Segmented
          value={metric}
          onChange={setMetric}
          options={[
            { value: "acute_load", label: t("design.acute") },
            { value: "chronic_load", label: t("design.chronic") },
          ]}
        />
      </div>
      {trend.isError ? (
        <ErrorNote />
      ) : trend.isLoading ? (
        <Loading />
      ) : !trend.data?.points.some(point => point.value != null) ? (
        <Empty action={<More to="/app/settings?tab=data-health">{t("lab.data_health")}</More>}>{t("completion.load_missing")}</Empty>
      ) : (
        <TrendChart
          points={trend.data?.points ?? []}
          start={trend.data?.start_date}
          end={o.date}
          unit={o.load_metadata?.unit ?? t("betaDaily.load_unit_unknown")}
          label={t("design.training_load")}
        />
      )}
      <div className="mt-3 border-t border-hairline pt-4 text-[12px] text-muted">
        {t("design.load_note")}
      </div>
    </Card>
  );
}
function Signal({ metric, fallback, unit, date, days, allowLatest }: { metric: string; fallback: number | null; unit: string; date: string; days: string; allowLatest: boolean }) {
  const { t } = useTranslation();
  const trend = useQuery({
    queryKey: ["metric", metric, days, date],
    queryFn: () => api.get<MetricTrend>(`/metrics/${metric}?days=${days}&end=${date}`),
  });
  const data = trend.data;
  const selectedValue = data?.points.find((p) => p.date === date)?.value ?? fallback;
  const withinRange = latestPoint(data, date);
  const history = useQuery({
    queryKey: ["metric", metric, "90", date],
    queryFn: () => api.get<MetricTrend>(`/metrics/${metric}?days=90&end=${date}`),
    enabled: allowLatest && selectedValue == null && trend.isSuccess && !withinRange,
    refetchInterval: 300_000,
  });
  const latest = allowLatest && selectedValue == null ? withinRange ?? latestPoint(history.data, date) : undefined;
  const value = selectedValue ?? latest?.value ?? null;
  const valueDate = selectedValue != null ? date : latest?.date;
  const valueTrend = withinRange ? data : history.data;
  const byDate = new Map(data?.points.map((p) => [p.date, p.value]) ?? []);
  const chart = Array.from({ length: Number(days) }, (_, i) => byDate.get(shiftDay(date, i - Number(days) + 1)) ?? null);
  const label = t(METRIC_LABELS[metric]);
  return <Card className="!p-4 sm:!p-5">
    <Link to={`/app/biometrics/${metric}`} className="flex items-center justify-between text-[13px] text-ink2"><span>{label}</span><ArrowRight size={14} aria-hidden="true" /></Link>
    <div className="my-3 flex items-baseline gap-2"><span className="num text-[28px] sm:text-[34px] font-medium tracking-[-.045em]">{unit === "h" ? fmtHours(value == null ? null : value * 3600) : fmtNum(value, metric === "spo2" || metric === "respiration" || metric === "vo2max" ? 1 : 0)}</span>{unit !== "h" && <span className="text-[12px] text-muted">{unit}</span>}</div>
    {allowLatest && valueDate && valueDate !== date && <p className="mb-2 text-[12px] text-muted">{t("overviewLatest.as_of", {date: valueDate})}</p>}
    {trend.isError ? <span className="text-[12px] text-muted">{t("refinement.trend_unavailable")}</span> : RANGE_METRICS.has(metric) && value != null && valueTrend ? <PersonalRange compact trend={valueDate === latestPoint(valueTrend, date)?.date ? valueTrend : { ...valueTrend, points: [{ date, value }], reference_range: null }} /> : <>
      <div role="img" aria-label={t("refinement.recorded_trend", { days })}><Sparkline points={chart} height={26} color="var(--c-text-muted)" /></div>
      {data && <div className="mt-2"><MetricDirection metric={metric} points={data.points} /></div>}
    </>}
  </Card>;
}

export default function OverviewPage() {
  const { t, i18n } = useTranslation();
  const units = useUnits();
  const me = useUi((s) => s.me);
  useEffect(() => {
    if (me) void api.post("/alpha/events", { event: "overview_viewed" }).catch(() => {});
  }, [me]);
  const setupDevices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<{ integration_id: number; provider: string; status?: string }[]>("/settings/devices"),
    staleTime: 60_000,
  });
  const setupSleep = useQuery({
    queryKey: ["setup-sleep-baseline"],
    queryFn: () => api.get<MetricTrend>("/metrics/sleep_duration?days=28"),
    staleTime: 60_000,
  });
  const [setupHidden, setSetupHidden] = useState(() => {
    try { return localStorage.getItem("apex.setup-checklist.dismissed") === "1"; } catch { return false; }
  });
  const [params, setParams] = useSearchParams();
  const date = params.get("date");
  // Observe YourDay's response without initiating a second request on mount.
  const setupProfile = useQuery<AthleteDay>({
    queryKey: ["athlete-day", me?.user_id, date ?? localDay(me?.timezone)],
    enabled: false,
  });
  const [range, setRange] = useState("7");
  const [historyOpen, setHistoryOpen] = useState(() => window.location.hash === "#training-load");
  const overview = useQuery({
    queryKey: ["overview", date ?? "latest"],
    queryFn: () => api.get<Overview>("/dashboard/overview" + (date ? "?date=" + date : "")),
    refetchInterval: 300_000,
  });
  const latestLoad = useLatestLoad(overview.data, !!overview.data && !date);
  const o = overview.data;
  const load = latestLoad ?? o;
  const today = localDay(me?.timezone);
  const requestedDay = date ?? today;
  const signals = o ? [
    { metric: "hrv_ms", fallback: o.hrv_ms, unit: "ms" },
    { metric: "resting_hr", fallback: o.resting_hr, unit: "bpm" },
    { metric: "sleep_duration", fallback: o.sleep_hours, unit: "h" },
    { metric: "spo2", fallback: o.spo2_avg, unit: "%" },
    { metric: "respiration", fallback: o.respiration_avg, unit: "br/min" },
    { metric: "vo2max", fallback: o.vo2max, unit: "ml/kg/min" },
  ] : [];
  const body = o ? [
    { key: "weight", value: units.weight(o.weight_kg), unit: units.weightUnit },
    { key: "body_fat", value: o.body_fat_pct, unit: "%" },
    { key: "steps", value: o.steps, unit: "" },
    { key: "floors", value: o.floors, unit: "" },
    { key: "hydration", value: units.metric("hydration", o.hydration_ml ?? null), unit: units.metricUnit("hydration", "ml") },
  ] : [];
  const hasHealthData = !!o && (signals.some((r) => r.fallback != null) || body.some((r) => r.value != null) || !!o.sleep || o.readiness.value != null || o.recovery.value != null || o.strain.value != null || o.sleep_score.value != null || o.acute_load != null || o.chronic_load != null || o.acwr != null);
  const hasData = hasHealthData || !!o?.activities.length;
  const recentActivities = o?.recent_activities ?? o?.activities ?? [];
  const connectedSources = setupDevices.data?.filter((device) => device.status === "active").length ?? 0;
  const recordedNights = setupSleep.data?.points.filter((p) => p.value != null).length ?? 0;
  const profileReady = setupProfile.data?.planning_context
    ? setupProfile.data.planning_context.profile_state === "ready"
    : !!setupProfile.data?.training_focus.length;
  const setupComplete = [connectedSources > 0, profileReady, recordedNights >= 14];
  const stageParts = o?.sleep ? [
    { key: "deep", value: o.sleep.stages.deep_s ?? 0, color: "var(--c-stage-deep)" },
    { key: "rem", value: o.sleep.stages.rem_s ?? 0, color: "var(--c-stage-rem)" },
    { key: "core", value: o.sleep.stages.light_s ?? 0, color: "var(--c-stage-core)" },
    { key: "awake", value: o.sleep.stages.awake_s ?? 0, color: "var(--c-stage-awake)" },
  ] : [];
  return <div className="focus-workspace flex flex-col gap-4 sm:gap-5" data-testid="today-workspace">
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <h1 className="text-[24px] font-medium tracking-[-.035em]">{t(date && requestedDay !== today ? "redesign.overview.day_review" : "redesign.overview.today")}</h1>
      <nav aria-label={t("redesign.overview.date_navigation")} className="flex items-center gap-1">
        <button className="flex min-h-11 min-w-11 items-center justify-center rounded-control text-muted hover:bg-surface" aria-label={t("common.prev_day")} onClick={() => setParams({ date: shiftDay(requestedDay, -1) })}><ChevronLeft size={18} /></button>
        <span className="num text-[12px] text-ink2">{new Date(requestedDay + "T12:00:00").toLocaleDateString(i18n.language, { month: "short", day: "numeric", year: "numeric" })}</span>
        <button disabled={requestedDay >= today} className="flex min-h-11 min-w-11 items-center justify-center rounded-control text-muted hover:bg-surface disabled:opacity-30" aria-label={t("common.next_day")} onClick={() => setParams({ date: shiftDay(requestedDay, 1) })}><ChevronRight size={18} /></button>
        {date && <button onClick={() => setParams({})} className="text-link min-h-11 px-2 text-[12px]">{t("common.today")}</button>}
      </nav>
    </header>
    {o && !o.anchor_is_today && <div className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-warning px-4 py-3 text-[13px]"><span>{t("overview.history_notice", { date: o.date })}</span><Badge tone="warning">{t("design.history")}</Badge></div>}
    {o && !!o.alerts.length && <div role="status">{[...o.alerts].sort((a, b) => (({ critical: 0, high: 1, error: 1, warning: 2, low: 3, info: 4 } as Record<string, number>)[a.severity] ?? 5) - (({ critical: 0, high: 1, error: 1, warning: 2, low: 3, info: 4 } as Record<string, number>)[b.severity] ?? 5)).slice(0, 1).map((alert, index) => <div key={index} className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-warning bg-surface px-4 py-3 text-[13px]">
      <p className="min-w-0 flex-1">{alert.type === "sync_failure" ? t("v01Navigation.sync_attention") : alert.message}</p>
      {alert.type === "sync_failure" && <Link className="text-link inline-flex min-h-11 items-center font-medium" to="/app/settings?tab=data-health">{t("v01Navigation.check_sync")} →</Link>}
    </div>)}</div>}
    {/* Keep the day tree mounted across metric loading and refresh failures. */}
    <div key="daily-workspace" className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]" data-testid="today-focus-layout">
      <div className="min-w-0" data-testid="today-hero"><YourDay date={requestedDay} variant="focus" /></div>
      <aside className="focus-card p-4 sm:p-5" aria-label={t("redesign.overview.daily_evidence")}>
        {overview.isError && <div className="mb-3 text-[13px]" data-testid="overview-health-error">
          <p role="status" className="text-muted">{t(o ? "redesign.overview.health_stale" : "redesign.overview.health_unavailable")}</p>
          <button type="button" className="text-link mt-2 inline-flex min-h-11 items-center" disabled={overview.isFetching} onClick={() => void overview.refetch()}>{t(overview.isFetching ? "common.loading" : "common.retry")}</button>
        </div>}
        {!o && !overview.isError && <Loading />}
        {o && load && <>

        <section aria-label={t("completion.daily_scores")}>
          <h2 className="focus-kicker">{t("redesign.overview.daily_evidence")}</h2>
          <div className="mt-2 grid grid-cols-2 gap-x-5 gap-y-1">
            {[{ key: "readiness", score: o.readiness }, { key: "recovery", score: o.recovery }, { key: "strain", score: o.strain }, { key: "provider_sleep_score", score: o.sleep_score }].map(({key, score}) => <ScoreCard key={key} metric={key} score={score} date={o.date} displayedDay={requestedDay} allowLatest={!date} />)}
          </div>
        </section>
        <a href="#training-load" onClick={(event) => {
          event.preventDefault();
          setHistoryOpen(true);
          window.history.replaceState(window.history.state, "", "#training-load");
          requestAnimationFrame(() => document.getElementById("training-load")?.scrollIntoView({ block: "start" }));
        }} className="mt-3 flex min-h-11 flex-wrap items-baseline gap-x-2 gap-y-1 border-t border-hairline pt-3 text-[12px] text-ink2"><span>{t("betaDaily.acute_scope")}</span><span className="num font-medium text-ink">{fmtNum(load.acute_load, 1)} {load.acute_load != null && (load.load_metadata?.unit ?? t("betaDaily.load_unit_unknown"))}</span>{load.date !== o.date && <span className="text-muted">{t("overviewLatest.as_of", {date: load.date})}</span>}<span className="text-muted">{load.acute_load == null ? t("completion.load_missing") : t("betaDaily.load_trend")} →</span></a>
        {overview.isSuccess && !hasHealthData && <div className="mt-2 text-[13px]" data-testid="overview-health-empty">
          <p className="text-muted">{t(date ? "redesign.overview.health_empty_day" : connectedSources > 0 ? "redesign.overview.health_empty_connected" : "redesign.overview.health_empty", { date: requestedDay })}</p>
          <Link to="/app/settings?tab=devices" className="text-link inline-flex min-h-11 items-center">{t(date || connectedSources > 0 || !setupDevices.isSuccess ? "settings.devices" : "setup.connect")} <ArrowRight size={14} /></Link>
        </div>}
        </>}
      </aside>
    </div>
    {!setupHidden && !setupComplete.every(Boolean) && <details className="focus-card px-4 sm:px-5" data-testid="overview-setup">
      <summary className="flex min-h-14 cursor-pointer list-none flex-wrap items-center justify-between gap-2 py-3 text-[13px]"><span className="font-medium">{t("redesign.overview.setup_support")}</span><span className="text-muted">{t("redesign.overview.setup_count", { count: setupComplete.filter(Boolean).length })} <ChevronRight size={14} className="ml-1 inline" aria-hidden="true" /></span></summary>
      <div className="border-t border-hairline pb-4 pt-3">
        <div className="flex items-start justify-between gap-4"><div><h2 className="text-[15px] font-medium">{t("setup.title")}</h2><p className="mt-1 text-[12px] text-muted">{t("setup.body")}</p></div><button type="button" className="min-h-11 min-w-11 text-muted hover:text-ink" aria-label={t("setup.dismiss")} onClick={() => { try { localStorage.setItem("apex.setup-checklist.dismissed", "1"); } catch { /* Dismiss for this visit when storage is unavailable. */ } setSetupHidden(true); }}>×</button></div>
        <ul className="mt-3 grid gap-3 text-[13px] sm:grid-cols-3">{[
          { done: setupComplete[0], label: t("setup.connect"), to: "/app/settings?tab=devices", state: setupDevices.isLoading ? t("setup.checking") : setupComplete[0] ? t("setup.connected", { count: connectedSources }) : t("setup.not_connected") },
          { done: setupComplete[1], label: t("setup.profile"), to: "/app/settings?tab=profile", state: setupProfile.isPending ? t("setup.checking") : setupComplete[1] ? t("setup.profile_ready") : t("setup.profile_missing") },
          { done: setupComplete[2], label: t("setup.baseline"), to: "/app/sleep", state: setupSleep.isLoading ? t("setup.checking") : t("setup.baseline_count", { count: recordedNights }) },
        ].map((item) => <li key={item.label}><Link to={item.to} className="flex min-h-11 items-center gap-3 rounded-control border border-hairline px-3 py-2 hover:bg-surface2"><span aria-hidden="true" className={item.done ? "text-positiveText" : "text-faint"}>{item.done ? "✓" : "○"}</span><span className="min-w-0"><span className="block font-medium text-ink">{item.label}</span><span className="block text-[12px] text-muted">{item.state}</span></span><ArrowRight size={14} className="ml-auto shrink-0" /></Link></li>)}</ul>
      </div>
    </details>}
    {o && load && <>
    <div className="grid gap-4 lg:grid-cols-2" data-testid="today-recent-context">
      <Card className="focus-card !p-4 sm:!p-5"><CardHeader title={t("completion.recent_activities")} right={<More to="/app/activities">{t("design.view_log")}</More>} />
        {!recentActivities.length ? <p className="py-3 text-[13px] text-muted">{t("overview.no_activities")}</p> : recentActivities.slice(0, 3).map((a) => <Link key={a.id} to={`/app/activities/${a.id}`} className="flex min-h-14 items-center gap-3 border-t border-hairline py-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control bg-surface2"><SportIcon discipline={a.discipline} size={17} /></span><div className="min-w-0 flex-1"><p className="text-[13px] font-medium">{friendlyDiscipline(a.discipline, t)}</p><p className="mt-1 text-[12px] text-muted">{new Date(a.start_time).toLocaleDateString(i18n.language, { timeZone: me?.timezone, month: "short", day: "numeric" })} · {fmtDuration(a.duration_s)} · {a.discipline === "sailing" ? `${fmtNum(a.distance_m == null ? null : a.distance_m / 1852, 1)} nmi` : `${fmtNum(units.distance(a.distance_m), 1)} ${units.distanceUnit}`} · {fmtNum(a.avg_hr)} bpm</p></div><ArrowRight size={14} /></Link>)}
      </Card>
      <Card className="focus-card !p-4 sm:!p-5"><CardHeader title={t("overview.last_night")} right={<More to={o.sleep ? "/app/sleep/" + o.date : "/app/sleep"}>{t("design.view_sleep")}</More>} />
        {o.sleep ? <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2"><span className="num text-[34px] font-medium tracking-[-.045em]">{fmtHours(o.sleep.total_sleep_s)}</span><span className="text-[12px] text-muted">{t("sleep.asleep")}</span>{o.sleep.sleep_score != null && <p className="w-full text-[12px] text-muted">{t("metricView.provider_sleep_score")}: {fmtNum(o.sleep.sleep_score)} / 100</p>}</div> : <p className="py-3 text-[13px] text-muted">{t("overview.no_sleep")}</p>}
      </Card>
    </div>
    <details className="border-t border-hairline pt-4"><summary className="cursor-pointer text-[14px] font-medium">{t("athlete.recovery_context")}</summary><div className="mt-4"><DecisionCard date={requestedDay} /></div>
      <nav aria-label={t("refinement.quick_access")} className="mt-4 flex flex-wrap gap-x-6 gap-y-3 text-[13px]">
        {[{ to: "/app/calendar", key: "lab.calendar" }, { to: "/app/training", key: "design.view_training" }, { to: "/app/biometrics?tab=labs", key: "biometrics.labs" }, { to: "/app/coach", key: "nav.coach" }, { to: "/app/settings?tab=devices", key: "settings.devices" }].map(link => <More key={link.to} to={link.to}>{t(link.key)}</More>)}
      </nav>
    </details>
    <details className="focus-card px-4 sm:px-5" open={historyOpen} onToggle={(event) => setHistoryOpen(event.currentTarget.open)} data-testid="overview-history">
      <summary className="min-h-14 cursor-pointer py-4 text-[14px] font-medium">{t("redesign.overview.health_history")}</summary>
      {historyOpen && <div className="flex flex-col gap-5 border-t border-hairline py-4">
        {hasData && <section aria-label={t("refinement.recorded_signals")}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 className="section-label">{t("refinement.recorded_signals")}</h2><Segmented value={range} onChange={setRange} options={[7, 28, 180].map((days) => ({ value: String(days), label: t("metricView.days" + days) }))} /></div>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">{signals.map((signal) => <Signal key={signal.metric} {...signal} date={o.date} days={range} allowLatest={!date} />)}</div>
          <p className="mt-3 text-[12px] text-muted">{t("refinement.signal_note")}</p>
        </section>}
        {o.sleep && <Card><CardHeader title={t("redesign.overview.sleep_stages")} /><ZoneBar parts={stageParts} height={12} gap={2} /><div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">{stageParts.map((part) => <div key={part.key}><span className="flex items-center gap-2 text-[12px] text-muted"><span className="h-2 w-2" style={{ backgroundColor: part.color }} />{t("stage." + part.key)}</span><span className="num mt-2 block text-[20px]">{fmtHours(part.value)}</span></div>)}</div></Card>}
        <Card className="!py-4"><div className="grid grid-cols-2 gap-4"><Link to="/app/biometrics/steps"><StatPod label={t(METRIC_LABELS.steps)} value={fmtNum(o.steps)} /></Link><Link to="/app/biometrics/floors"><StatPod label={t(METRIC_LABELS.floors)} value={fmtNum(o.floors)} /></Link></div></Card>
        <div id="training-load" className="scroll-mt-20">{load.date !== o.date && <p className="mb-2 text-[12px] text-muted">{t("overviewLatest.as_of", {date: load.date})}</p>}<LoadPanel o={load} /></div>
        <ActivityCalendar date={date ?? today} />
      </div>}
    </details>
    </>}
  </div>;
}
