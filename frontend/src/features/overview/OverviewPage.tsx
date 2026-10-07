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
  PageHeader,
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
      <div className="grid grid-cols-3 gap-4">
        <StatPod
          label={t("design.acute")}
          value={fmtNum(o.acute_load, 1)}
          unit={t("lab.legacy_load_unit")}
        />
        <StatPod
          label={t("design.chronic")}
          value={fmtNum(o.chronic_load, 1)}
          unit={t("lab.legacy_load_unit")}
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
      ) : (
        <TrendChart
          points={trend.data?.points ?? []}
          start={trend.data?.start_date}
          end={o.date}
          unit={t("lab.legacy_load_unit")}
          label={t("design.training_load")}
        />
      )}
      <div className="mt-3 border-t border-hairline pt-4 text-[12px] text-muted">
        {t("design.load_note")}
      </div>
    </Card>
  );
}
function Signal({ metric, fallback, unit, date, days }: { metric: string; fallback: number | null; unit: string; date: string; days: string }) {
  const { t } = useTranslation();
  const trend = useQuery({
    queryKey: ["metric", metric, days, date],
    queryFn: () => api.get<MetricTrend>(`/metrics/${metric}?days=${days}&end=${date}`),
  });
  const data = trend.data;
  const value = data?.points.find((p) => p.date === date)?.value ?? fallback;
  const byDate = new Map(data?.points.map((p) => [p.date, p.value]) ?? []);
  const chart = Array.from({ length: Number(days) }, (_, i) => byDate.get(shiftDay(date, i - Number(days) + 1)) ?? null);
  const label = t(METRIC_LABELS[metric]);
  const latest = data?.points.filter((p) => p.value != null).at(-1);
  return <Card className="!p-4 sm:!p-5">
    <Link to={`/app/biometrics/${metric}`} className="flex items-center justify-between text-[13px] text-ink2"><span>{label}</span><ArrowRight size={14} aria-hidden="true" /></Link>
    <div className="my-3 flex items-baseline gap-2"><span className="num text-[28px] sm:text-[34px] font-medium tracking-[-.045em]">{unit === "h" ? fmtHours(value == null ? null : value * 3600) : fmtNum(value, metric === "spo2" || metric === "respiration" || metric === "vo2max" ? 1 : 0)}</span>{unit !== "h" && <span className="text-[12px] text-muted">{unit}</span>}</div>
    {trend.isError ? <span className="text-[12px] text-muted">{t("refinement.trend_unavailable")}</span> : RANGE_METRICS.has(metric) && value != null && data ? <PersonalRange compact trend={latest?.date === date ? data : { ...data, points: [{ date, value }], reference_range: null }} /> : <>
      <div role="img" aria-label={t("refinement.recorded_trend", { days })}><Sparkline points={chart} height={26} color="var(--c-text-muted)" /></div>
      {data && <div className="mt-2"><MetricDirection metric={metric} points={data.points} /></div>}
    </>}
  </Card>;
}

export default function OverviewPage() {
  const { t } = useTranslation();
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
  const [range, setRange] = useState("7");
  const overview = useQuery({
    queryKey: ["overview", date ?? "latest"],
    queryFn: () => api.get<Overview>("/dashboard/overview" + (date ? "?date=" + date : "")),
    refetchInterval: 300_000,
  });
  if (overview.isLoading) return <Loading />;
  if (overview.isError || !overview.data) return <ErrorNote />;
  const o = overview.data;
  const today = localDay(me?.timezone);
  const signals = [
    { metric: "hrv_ms", fallback: o.hrv_ms, unit: "ms" },
    { metric: "resting_hr", fallback: o.resting_hr, unit: "bpm" },
    { metric: "sleep_duration", fallback: o.sleep_hours, unit: "h" },
    { metric: "spo2", fallback: o.spo2_avg, unit: "%" },
    { metric: "respiration", fallback: o.respiration_avg, unit: "br/min" },
    { metric: "vo2max", fallback: o.vo2max, unit: "ml/kg/min" },
  ];
  const body = [
    { key: "weight", value: units.weight(o.weight_kg), unit: units.weightUnit },
    { key: "body_fat", value: o.body_fat_pct, unit: "%" },
    { key: "steps", value: o.steps, unit: "" },
    { key: "floors", value: o.floors, unit: "" },
    { key: "hydration", value: units.metric("hydration", o.hydration_ml ?? null), unit: units.metricUnit("hydration", "ml") },
  ];
  const hasData = signals.some((r) => r.fallback != null) || body.some((r) => r.value != null) || o.activities.length > 0 || !!o.sleep || o.readiness.value != null || o.recovery.value != null || o.strain.value != null || o.acute_load != null;
  const connectedSources = setupDevices.data?.filter((device) => device.status === "active").length ?? 0;
  const recordedNights = setupSleep.data?.points.filter((p) => p.value != null).length ?? 0;
  const setupComplete = [connectedSources > 0, !!(me?.name?.trim() && me.timezone), recordedNights >= 14];
  const stageParts = o.sleep ? [
    { key: "deep", value: o.sleep.stages.deep_s ?? 0, color: "var(--c-stage-deep)" },
    { key: "rem", value: o.sleep.stages.rem_s ?? 0, color: "var(--c-stage-rem)" },
    { key: "core", value: o.sleep.stages.light_s ?? 0, color: "var(--c-stage-core)" },
    { key: "awake", value: o.sleep.stages.awake_s ?? 0, color: "var(--c-stage-awake)" },
  ] : [];
  return <div className="flex flex-col gap-6">
    <PageHeader title={t("design.overview")} subtitle={t("design.overview_sub")} actions={<div className="flex items-center gap-3">
      <button className="p-2 text-muted hover:text-ink" aria-label={t("common.prev_day")} onClick={() => setParams({ date: shiftDay(o.date, -1) })}><ChevronLeft size={18} /></button>
      <span className="num text-[13px]">{new Date(o.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>
      <button disabled={o.date >= today} className="p-2 text-muted hover:text-ink disabled:opacity-30" aria-label={t("common.next_day")} onClick={() => setParams({ date: shiftDay(o.date, 1) })}><ChevronRight size={18} /></button>
      {date && <button onClick={() => setParams({})} className="text-link">{t("common.today")}</button>}
    </div>} />
    <nav aria-label={t("refinement.quick_access")} className="flex flex-wrap gap-x-6 gap-y-3 border-b border-hairline pb-4 text-[13px]">
      {[{ to: "/app/calendar", key: "lab.calendar" }, { to: "/app/training", key: "design.view_training" }, { to: "/app/biometrics?tab=labs", key: "biometrics.labs" }, { to: "/app/coach", key: "nav.coach" }, { to: "/app/settings?tab=devices", key: "settings.devices" }].map((link) => <More key={link.to} to={link.to}>{t(link.key)}</More>)}
    </nav>
    {!o.anchor_is_today && <div className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-warning px-4 py-3 text-[13px]"><span>{t("overview.history_notice", { date: o.date })}</span><Badge tone="warning">{t("design.history")}</Badge></div>}
    {!setupHidden && !setupComplete.every(Boolean) && <Card className="!p-4 sm:!p-5">
      <div className="flex items-start justify-between gap-4"><div><p className="eyebrow text-primaryText">{t("setup.eyebrow")}</p><h2 className="mt-1 text-[18px] font-medium">{t("setup.title")}</h2><p className="mt-1 text-[13px] text-muted">{t("setup.body")}</p></div><button type="button" className="min-h-11 min-w-11 text-muted hover:text-ink" aria-label={t("setup.dismiss")} onClick={() => { try { localStorage.setItem("apex.setup-checklist.dismissed", "1"); } catch { /* Dismiss for this visit when storage is unavailable. */ } setSetupHidden(true); }}>×</button></div>
      <ul className="mt-4 grid gap-3 text-[13px] sm:grid-cols-3">{[
        { done: setupComplete[0], label: t("setup.connect"), to: "/app/settings?tab=devices", state: setupDevices.isLoading ? t("setup.checking") : setupComplete[0] ? t("setup.connected", { count: connectedSources }) : t("setup.not_connected") },
        { done: setupComplete[1], label: t("setup.profile"), to: "/app/settings?tab=profile", state: setupComplete[1] ? t("setup.profile_ready") : t("setup.profile_missing") },
        { done: setupComplete[2], label: t("setup.baseline"), to: "/app/sleep", state: setupSleep.isLoading ? t("setup.checking") : t("setup.baseline_count", { count: recordedNights }) },
      ].map((item) => <li key={item.label}><Link to={item.to} className="flex min-h-11 items-center gap-3 border border-hairline px-3 py-2 hover:bg-surface2"><span aria-hidden="true" className={item.done ? "text-positiveText" : "text-faint"}>{item.done ? "✓" : "○"}</span><span className="min-w-0"><span className="block font-medium text-ink">{item.label}</span><span className="block text-[12px] text-muted">{item.state}</span></span><ArrowRight size={14} className="ml-auto shrink-0" /></Link></li>)}</ul>
    </Card>}
    {date ? <DecisionCard date={date} /> : <DecisionCard />}
    {!hasData ? <><Card><Empty action={<More to="/app/settings?tab=devices">{t("overview.connect_cta")}</More>}>{t("design.connect_empty")}</Empty></Card></> : <>
      {!!o.alerts.length && <div className="flex flex-col gap-2" role="status">{o.alerts.map((a, i) => <div key={i} className="flex items-start gap-4 border-l-2 border-alert px-5 py-3 text-[13px]"><Badge tone={a.severity === "critical" || a.severity === "high" ? "alert" : "warning"}>{a.severity}</Badge><span>{a.message}</span></div>)}</div>}
      <section aria-label={t("refinement.recorded_signals")}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 className="section-label">{t("refinement.recorded_signals")}</h2><Segmented value={range} onChange={setRange} options={[7, 28, 180].map((days) => ({ value: String(days), label: t("metricView.days" + days) }))} /></div>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">{signals.map((signal) => <Signal key={signal.metric} {...signal} date={o.date} days={range} />)}</div>
        <p className="mt-3 text-[12px] text-muted">{t("refinement.signal_note")}</p>
      </section>
      <div className="grid gap-6 xl:grid-cols-[1fr_1.25fr]">
        <Card><CardHeader title={t("design.body_activity")} right={<More to="/app/biometrics?tab=body">{t("design.all_metrics")}</More>} />
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">{body.map((b) => <Link key={b.key} to={`/app/biometrics/${b.key}`}><StatPod label={t(METRIC_LABELS[b.key])} value={fmtNum(b.value, ["steps", "floors", "hydration"].includes(b.key) ? 0 : 1)} unit={b.unit} /></Link>)}</div>
          <details className="mt-5 border-t border-hairline pt-4"><summary className="cursor-pointer text-[13px] text-muted">{t("metricView.estimates")}</summary><p className="my-3 text-[12px] text-muted">{t("metricView.estimates_note")}</p><div className="grid grid-cols-3 gap-3">{[{ key: "readiness", score: o.readiness }, { key: "recovery", score: o.recovery }, { key: "strain", score: o.strain }].map((e) => <Link key={e.key} to={`/app/biometrics/${e.key}`}><StatPod label={t(METRIC_LABELS[e.key])} value={fmtNum(e.score.value)} unit="/100" /><DeltaChip delta={e.score.delta_7d} compact /></Link>)}</div></details>
        </Card>
        <LoadPanel o={o} />
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card><CardHeader title={t("activities.title")} right={<More to="/app/activities">{t("design.view_log")}</More>} />
          {!o.activities.length ? <Empty>{t("overview.no_activities")}</Empty> : o.activities.map((a) => <Link key={a.id} to={`/app/activities/${a.id}`} className="flex items-center gap-4 border-b border-hairline py-5 last:border-0"><span className="flex h-10 w-10 shrink-0 items-center justify-center bg-surface2"><SportIcon discipline={a.discipline} size={19} /></span><div className="min-w-0 flex-1"><p className="font-medium">{friendlyDiscipline(a.discipline, t)}</p><p className="mt-1 text-[12px] text-muted">{fmtDuration(a.duration_s)} · {a.discipline === "sailing" ? `${fmtNum(a.distance_m == null ? null : a.distance_m / 1852, 1)} nmi` : `${fmtNum(units.distance(a.distance_m), 1)} ${units.distanceUnit}`} · {fmtNum(a.avg_hr)} bpm</p></div><ArrowRight size={16} /></Link>)}
          <p className="mt-4 text-[12px] text-muted">{t("design.week_load", { value: fmtNum(o.training_load_7d) })}</p>
        </Card>
        <Card><CardHeader title={t("overview.last_night")} right={<More to={o.sleep ? "/app/sleep/" + o.date : "/app/sleep"}>{t("design.view_sleep")}</More>} />
          {o.sleep ? <><div className="mb-6 flex items-baseline gap-3"><span className="num text-[48px] font-medium tracking-[-.055em]">{fmtHours(o.sleep.total_sleep_s)}</span><span className="text-[13px] text-muted">{t("sleep.asleep")}</span></div><ZoneBar parts={stageParts} height={12} gap={2} /><div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">{stageParts.map((part) => <div key={part.key}><span className="flex items-center gap-2 text-[12px] text-muted"><span className="h-2 w-2" style={{ backgroundColor: part.color }} />{t("stage." + part.key)}</span><span className="num mt-2 block text-[20px]">{fmtHours(part.value)}</span></div>)}</div>{o.sleep.sleep_score != null && <p className="mt-5 border-t border-hairline pt-4 text-[12px] text-muted">{t("metricView.provider_sleep_score")}: {fmtNum(o.sleep.sleep_score)} / 100</p>}</> : <Empty>{t("overview.no_sleep")}</Empty>}
        </Card>
      </div>
    </>}
  </div>;
}
