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
  ZoneBar,
  fmtNum,
  fmtHours,
  fmtDuration,
  friendlyDiscipline,
} from "../../components/kit";
import { TrendChart } from "../../components/charts/TrendChart";
import { localDay, shiftDay, useUnits } from "../../components/data";
import { DecisionCard } from "../lab/DecisionCard";
import { useState } from "react";

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
export default function OverviewPage() {
  const { t } = useTranslation();
  const units = useUnits();
  const me = useUi((s) => s.me);
  const [params, setParams] = useSearchParams();
  const date = params.get("date");
  const [range, setRange] = useState("7");
  const overview = useQuery({
    queryKey: ["overview", date ?? "latest"],
    queryFn: () =>
      api.get<Overview>("/dashboard/overview" + (date ? "?date=" + date : "")),
    refetchInterval: 300_000,
  });
  const o = overview.data;
  const readiness = useQuery({
    queryKey: ["metric", "readiness", range, o?.date],
    queryFn: () =>
      api.get<MetricTrend>(
        "/metrics/readiness?days=" + range + "&end=" + o!.date,
      ),
    enabled: !!o,
  });
  if (overview.isLoading) return <Loading />;
  if (overview.isError || !o) return <ErrorNote />;

  const hasData =
    [
      o.readiness.value,
      o.recovery.value,
      o.sleep_hours,
      o.resting_hr,
      o.steps,
      o.hrv_ms,
      o.weight_kg,
      o.acute_load,
    ].some((v) => v != null) ||
    o.activities.length > 0 ||
    !!o.sleep;
  const signalRows = [
    {
      label: t("overview.resting_hr"),
      value: fmtNum(o.resting_hr),
      unit: "bpm",
      delta: o.resting_hr_delta_7d,
      to: "resting_hr",
    },
    {
      label: t("design.hrv_raw"),
      value: fmtNum(o.hrv_ms),
      unit: "ms",
      sub:
        o.hrv_baseline_ms != null
          ? t("design.baseline_value", { value: fmtNum(o.hrv_baseline_ms) })
          : t("design.baseline_missing"),
      to: "hrv_deviation",
    },
    {
      label: t("overview.spo2"),
      value: fmtNum(o.spo2_avg, 1),
      unit: "%",
      delta: o.spo2_delta_7d,
      to: "spo2",
    },
    {
      label: t("overview.respiration"),
      value: fmtNum(o.respiration_avg, 1),
      unit: "br/min",
      to: "respiration",
    },
    {
      label: t("biometrics.weight"),
      value: fmtNum(units.weight(o.weight_kg), 1),
      unit: units.weightUnit,
      to: "weight",
    },
    {
      label: t("biometrics.vo2max"),
      value: fmtNum(o.vo2max, 1),
      unit: "ml/kg/min",
      to: "vo2max",
    },
  ];
  const stageParts = o.sleep
    ? [
        {
          key: "deep",
          value: o.sleep.stages.deep_s ?? 0,
          color: "var(--c-stage-deep)",
        },
        {
          key: "rem",
          value: o.sleep.stages.rem_s ?? 0,
          color: "var(--c-stage-rem)",
        },
        {
          key: "core",
          value: o.sleep.stages.light_s ?? 0,
          color: "var(--c-stage-core)",
        },
        {
          key: "awake",
          value: o.sleep.stages.awake_s ?? 0,
          color: "var(--c-stage-awake)",
        },
      ]
    : [];
  const today = localDay(me?.timezone);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("design.overview")}
        subtitle={t("design.overview_sub")}
        actions={
          <div className="flex items-center gap-3">
            <button
              className="p-2 text-muted hover:text-ink"
              aria-label={t("common.prev_day")}
              onClick={() => setParams({ date: shiftDay(o.date, -1) })}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="num text-[13px]">
              {new Date(o.date + "T12:00:00").toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
            <button
              disabled={o.date >= today}
              className="p-2 text-muted hover:text-ink disabled:opacity-30"
              aria-label={t("common.next_day")}
              onClick={() => setParams({ date: shiftDay(o.date, 1) })}
            >
              <ChevronRight size={18} />
            </button>
            {date && (
              <button onClick={() => setParams({})} className="text-link">
                {t("common.today")}
              </button>
            )}
          </div>
        }
      />
      {!date && <DecisionCard />}
      {!o.anchor_is_today && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-warning bg-warningSoft px-4 py-3 text-[13px]">
          <span>{t("overview.history_notice", { date: o.date })}</span>
          <Badge tone="warning">{t("design.history")}</Badge>
        </div>
      )}
      {!hasData ? (
        <Card>
          <Empty
            action={
              <More to="/app/settings?tab=devices">
                {t("overview.connect_cta")}
              </More>
            }
          >
            {t("design.connect_empty")}
          </Empty>
        </Card>
      ) : (
        <>
          {o.alerts.length > 0 && (
            <div className="flex flex-col gap-2" role="status">
              {o.alerts.map((a, i) => (
                <div
                  key={i}
                  className="flex items-start gap-4 bg-alertSoft px-5 py-4 text-[13px]"
                >
                  <Badge
                    tone={
                      a.severity === "critical" || a.severity === "high"
                        ? "alert"
                        : "warning"
                    }
                  >
                    {a.severity}
                  </Badge>
                  <span>{a.message}</span>
                </div>
              ))}
            </div>
          )}
          <div className="grid gap-6 xl:grid-cols-[1.65fr_1fr]">
            <Card className="!p-6 md:!p-8">
              <CardHeader
                title={t("lab.legacy_readiness")}
                right={<Badge>{t("lab.heuristic")}</Badge>}
              />
              <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
                <div className="flex items-baseline gap-3">
                  <span className="hero-number num">
                    {fmtNum(o.readiness.value)}
                  </span>
                  <span className="text-[18px] text-muted">/ 100</span>
                </div>
                <div className="pb-2">
                  <DeltaChip
                    delta={o.readiness.delta_7d}
                    unit="pts"
                    suffix={t("design.vs_previous7")}
                  />
                </div>
              </div>
              <div className="mb-1 flex items-center justify-between gap-4">
                <span className="text-[12px] text-muted">
                  {t("design.readiness_trend")}
                </span>
                <Segmented
                  value={range}
                  onChange={setRange}
                  options={[
                    { value: "7", label: t("common.week") },
                    { value: "30", label: t("common.month") },
                  ]}
                />
              </div>
              {readiness.isError ? (
                <ErrorNote />
              ) : readiness.isLoading ? (
                <Loading />
              ) : (
                <TrendChart
                  points={readiness.data?.points ?? []}
                  start={readiness.data?.start_date}
                  end={o.date}
                  unit="/100"
                  label={t("lab.legacy_readiness")}
                  height={180}
                />
              )}
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4">
                <span className="text-[12px] text-muted">
                  {t("design.score_note")}
                </span>
                <More to="/app/biometrics/readiness">
                  {t("design.explore")}
                </More>
              </div>
            </Card>
            <Card className="!p-6 md:!p-8">
              <CardHeader
                title={t("design.at_glance")}
                right={<span className="text-[12px] text-muted">{o.date}</span>}
              />
              {[
                {
                  label: t("overview.recovery_label"),
                  v: o.recovery.value,
                  k: "recovery",
                  unit: "/100",
                },
                {
                  label: t("overview.strain_label"),
                  v: o.strain.value,
                  k: "strain",
                  unit: "/100",
                },
                {
                  label: t("overview.sleep_score"),
                  v: o.sleep_score.value,
                  k: "sleep_score",
                  unit: "/100",
                },
                {
                  label: t("biometrics.steps"),
                  v: o.steps,
                  k: "steps",
                  unit: "",
                },
              ].map((s) => {
                return (
                  <Link
                    key={s.k}
                    to={"/app/biometrics/" + s.k}
                    className="flex items-center justify-between gap-4 border-b border-hairline py-5 last:border-0"
                  >
                    <div>
                      <span className="text-[14px]">{s.label}</span>
                      <div className="mt-1">
                        <Badge>{t("lab.heuristic")}</Badge>
                      </div>
                    </div>
                    <div className="num text-[28px] font-medium tracking-[-.04em]">
                      {fmtNum(s.v)}
                      <span className="ml-2 text-[12px] font-normal tracking-normal text-muted">
                        {s.unit}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </Card>
          </div>
          <div className="grid gap-6 xl:grid-cols-[1fr_1.25fr]">
            <Card>
              <CardHeader
                title={t("design.body_signals")}
                right={
                  <More to="/app/biometrics">{t("design.all_metrics")}</More>
                }
              />
              {signalRows.map((r) => (
                <Link
                  to={"/app/biometrics/" + r.to}
                  key={r.to}
                  className="flex items-center justify-between gap-4 border-b border-hairline py-4 last:border-0"
                >
                  <div>
                    <div className="text-[14px]">{r.label}</div>
                    {r.sub && (
                      <p className="mt-1 text-[12px] text-muted">{r.sub}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <span className="num text-[22px] font-medium">
                      {r.value}
                      <span className="ml-2 text-[12px] font-normal text-muted">
                        {r.unit}
                      </span>
                    </span>
                    {r.delta != null && (
                      <div className="mt-1 text-[12px] text-muted">
                        <DeltaChip
                          delta={r.delta}
                          unit={r.unit === "%" ? "pp" : r.unit}
                          compact
                        />
                      </div>
                    )}
                  </div>
                </Link>
              ))}
              {o.hrv_norm_30d != null && (
                <p className="mt-4 border-t border-hairline pt-4 text-[12px] text-muted">
                  {t("design.hrv_norm", { value: fmtNum(o.hrv_norm_30d) })}
                </p>
              )}
            </Card>
            <LoadPanel o={o} />
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader
                title={t("activities.title")}
                right={<More to="/app/activities">{t("design.view_log")}</More>}
              />
              {o.activities.length === 0 ? (
                <Empty>{t("overview.no_activities")}</Empty>
              ) : (
                o.activities.map((a) => (
                  <Link
                    key={a.id}
                    to={"/app/activities/" + a.id}
                    className="flex items-center gap-4 border-b border-hairline py-5 last:border-0"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center bg-surface2">
                      <SportIcon discipline={a.discipline} size={19} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">
                        {friendlyDiscipline(a.discipline, t)}
                      </p>
                      <p className="mt-1 text-[12px] text-muted">
                        {fmtDuration(a.duration_s)} ·{" "}
                        {fmtNum(units.distance(a.distance_m), 1)}{" "}
                        {units.distanceUnit} · {fmtNum(a.avg_hr)} bpm
                      </p>
                    </div>
                    <div className="num text-right">
                      {fmtNum(a.training_load)}
                      <p className="text-[12px] text-muted">TSS</p>
                    </div>
                    <ArrowRight size={16} />
                  </Link>
                ))
              )}
              <p className="mt-4 text-[12px] text-muted">
                {t("design.week_load", { value: fmtNum(o.training_load_7d) })}
              </p>
            </Card>
            <Card>
              <CardHeader
                title={t("overview.last_night")}
                right={
                  <More to={o.sleep ? "/app/sleep/" + o.date : "/app/sleep"}>
                    {t("design.view_sleep")}
                  </More>
                }
              />
              {o.sleep ? (
                <>
                  <div className="mb-6 flex items-baseline gap-3">
                    <span className="num text-[48px] font-medium tracking-[-.055em]">
                      {fmtHours(o.sleep.total_sleep_s)}
                    </span>
                    <span className="text-[13px] text-muted">
                      {t("sleep.asleep")}
                    </span>
                  </div>
                  <ZoneBar parts={stageParts} height={12} gap={2} />
                  <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
                    {stageParts.map((p) => (
                      <div key={p.key}>
                        <span className="flex items-center gap-2 text-[12px] text-muted">
                          <span
                            className="h-2 w-2"
                            style={{ background: p.color }}
                          />
                          {t("stage." + p.key)}
                        </span>
                        <p className="num mt-2 font-medium">
                          {fmtHours(
                            o.sleep!.stages[
                              p.key === "core"
                                ? "light_s"
                                : p.key === "deep"
                                  ? "deep_s"
                                  : p.key === "rem"
                                    ? "rem_s"
                                    : "awake_s"
                            ],
                          )}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-6 border-t border-hairline pt-4 text-[12px] text-muted">
                    {new Date(o.sleep.start_time).toLocaleTimeString(
                      undefined,
                      {
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: me?.timezone,
                      },
                    )}{" "}
                    –{" "}
                    {new Date(o.sleep.end_time).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: me?.timezone,
                    })}
                  </div>
                </>
              ) : (
                <Empty>{t("sleep.no_night")}</Empty>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
