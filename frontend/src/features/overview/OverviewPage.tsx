/**
 * Overview — the home dashboard (mockup: home_main_dashboard).
 *
 * Layout law (12-col): readiness hero + synthesis diagnosis on the first
 * row; ACWR load block (8-col) beside the biomarker strip (4-col); activity
 * log + sleep card below. Mobile collapses to stacked 2-col pods.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Watch } from "lucide-react";
import { api, type Overview } from "../../app/api";
import {
  Badge,
  BigStat,
  Card,
  CardHeader,
  DeltaChip,
  Empty,
  ErrorNote,
  Loading,
  RangeBar,
  ScoreBar,
  fmtHours,
  fmtNum,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

function scoreTone(v: number | null) {
  if (v === null) return "muted" as const;
  if (v >= 75) return "positive" as const;
  if (v >= 50) return "primary" as const;
  if (v >= 35) return "warning" as const;
  return "alert" as const;
}

function ScoreHero({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const readiness = o.readiness.value;
  const sleep = o.sleep_score.value;
  const readinessLabel =
    readiness === null ? "—" : readiness >= 75 ? t("common.optimal") : readiness >= 50 ? t("common.good") : t("common.fair");

  return (
    <Card className="col-span-12 xl:col-span-8">
      <CardHeader
        eyebrow={t("overview.adaptive_readiness")}
        title={readinessLabel}
        right={<DeltaChip delta={o.readiness.delta_7d} compact />}
      />
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-card border border-hairline bg-surface2 p-4">
          <div className="eyebrow mb-2">{t("overview.system_readiness")}</div>
          <BigStat value={fmtNum(readiness)} unit="/100" size="lg" />
          <div className="mt-3">
            <ScoreBar value={readiness ?? 0} tone={scoreTone(readiness)} />
          </div>
          <div className="num mt-2 flex justify-between text-[10px] text-faint">
            <span>
              {t("overview.floor")}: {fmtNum(Math.max(0, (readiness ?? 0) - 14))}
            </span>
            <span>
              {t("overview.cap")}: {fmtNum(Math.min(100, (readiness ?? 0) + 8))}
            </span>
          </div>
        </div>
        <div className="rounded-card border border-hairline bg-surface2 p-4">
          <div className="eyebrow mb-2">{t("overview.sleep_score")}</div>
          <BigStat value={fmtNum(sleep)} unit="/100" size="lg" />
          <div className="mt-3">
            <ScoreBar value={sleep ?? 0} tone={scoreTone(sleep)} />
          </div>
          <div className="num mt-2 flex justify-between text-[10px] text-faint">
            <span>{fmtHours(o.sleep_hours ? o.sleep_hours * 3600 : null)}</span>
            <span>
              {t("overview.deep")} {fmtNum(o.sleep?.stages.deep_s ? o.sleep.stages.deep_s / 3600 : null, 1)}
              h
            </span>
          </div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-hairline pt-3">
        <MiniStat label="CTL" value={`${fmtNum(o.chronic_load, 0)}`} unit="TSS/d" />
        <MiniStat
          label={t("overview.hrv_norm")}
          value={fmtNum(o.hrv_ms)}
          unit="ms"
          delta={o.hrv_baseline_ms && o.hrv_ms ? ((o.hrv_ms - o.hrv_baseline_ms) / o.hrv_baseline_ms) * 100 : null}
        />
        <MiniStat
          label={t("overview.freshness")}
          value={
            o.chronic_load && o.acute_load
              ? `${fmtNum(o.chronic_load - o.acute_load, 0)}`
              : "—"
          }
          unit="TSB"
        />
      </div>
    </Card>
  );
}

function MiniStat({
  label,
  value,
  unit,
  delta,
}: {
  label: string;
  value: string;
  unit: string;
  delta?: number | null;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0">
        <div className="eyebrow truncate">{label}</div>
        <div className="num text-[15px] font-semibold text-ink">
          {value} <span className="text-[10px] font-normal text-muted">{unit}</span>
        </div>
      </div>
      {delta !== undefined && delta !== null && Number.isFinite(delta) && (
        <span
          className={`num text-[10px] font-semibold ${delta >= 0 ? "text-positiveText" : "text-alertText"}`}
        >
          {delta >= 0 ? "+" : "−"}
          {Math.abs(delta).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

function AcwrBlock({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const acwr = o.acwr;
  const tone =
    acwr === null
      ? "muted"
      : acwr >= 0.8 && acwr <= 1.3
        ? "positive"
        : acwr > 1.5 || acwr < 0.6
          ? "alert"
          : "warning";

  // 28-day acute/chronic series from the metrics endpoint
  const trend = useQuery({
    queryKey: ["metric", "acute_load", 28],
    queryFn: () => api.get<import("../../app/api").MetricTrend>("/metrics/acute_load?days=28"),
  });
  const chronic = useQuery({
    queryKey: ["metric", "chronic_load", 28],
    queryFn: () => api.get<import("../../app/api").MetricTrend>("/metrics/chronic_load?days=28"),
  });

  const points = trend.data?.points ?? [];
  const chronicPoints = chronic.data?.points ?? [];
  const dates = points.map((p) => p.date);

  const option = {
    grid: { left: 46, right: 8, top: 26, bottom: 22 },
    tooltip: {
      trigger: "axis",
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
    },
    legend: {
      top: 0,
      left: 0,
      icon: "rect",
      itemWidth: 10,
      itemHeight: 2,
      textStyle: { color: c.muted, fontSize: 10, fontFamily: "Geist" },
      data: [
        t("overview.acute_load"),
        t("overview.chronic_load"),
      ],
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: (v: string) => v.slice(5),
        interval: Math.max(0, Math.floor(dates.length / 5) - 1),
      },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
    },
    series: [
      {
        name: t("overview.acute_load"),
        type: "bar",
        data: points.map((p) => p.value),
        barMaxWidth: 8,
        itemStyle: { color: c.hairline, borderRadius: [2, 2, 0, 0] },
      },
      {
        name: t("overview.chronic_load"),
        type: "line",
        data: chronicPoints.map((p) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: c.primary, width: 2 },
        itemStyle: { color: c.primary },
      },
    ],
  };

  return (
    <Card className="col-span-12 xl:col-span-8">
      <CardHeader
        eyebrow={t("overview.strain_title")}
        title={t("overview.acwr_title")}
        right={<Badge tone="neutral">{t("overview.range28")}</Badge>}
      />
      <div className="grid grid-cols-3 gap-3">
        <LoadStat label={t("overview.acute_load")} value={fmtNum(o.acute_load, 0)} unit="TSS" sub={t("overview.fatigue")} />
        <LoadStat label={t("overview.chronic_load")} value={fmtNum(o.chronic_load, 0)} unit="TSS" sub={t("overview.fitness")} />
        <LoadStat
          label={t("overview.acwr_index")}
          value={fmtNum(acwr, 2)}
          unit=""
          sub={t("overview.optimal_window")}
          tone={tone}
        />
      </div>
      <div className="mt-3">
        {dates.length ? (
          <EChart option={option} height={220} />
        ) : (
          <Empty>{t("biometrics.no_data")}</Empty>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-hairline pt-3 text-[12px] text-muted">
        <CheckCircle2 size={14} className="text-positiveText" />
        {t("overview.no_overreach")}
      </div>
    </Card>
  );
}

function LoadStat({
  label,
  value,
  unit,
  sub,
  tone = "muted",
}: {
  label: string;
  value: string;
  unit: string;
  sub?: string;
  tone?: "muted" | "positive" | "warning" | "alert";
}) {
  const toneCls = {
    muted: "text-ink",
    positive: "text-positiveText",
    warning: "text-warningText",
    alert: "text-alertText",
  }[tone];
  return (
    <div className="rounded-card border border-hairline bg-surface2 p-3">
      <div className="eyebrow truncate">{label}</div>
      <div className={`num mt-1 text-[22px] font-bold ${toneCls}`}>
        {value}
        {unit && <span className="ml-1 text-[10px] font-medium text-muted">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-faint">{sub}</div>}
    </div>
  );
}

function BiomarkerStrip({ o }: { o: Overview }) {
  const { t } = useTranslation();
  return (
    <Card className="col-span-12 xl:col-span-4">
      <CardHeader
        eyebrow={t("overview.biomarkers")}
        right={<Badge tone="positive">{t("overview.all_normal")}</Badge>}
      />
      <div className="grid grid-cols-2 gap-3">
        <Biomarker
          label={t("overview.resting_hr")}
          value={fmtNum(o.resting_hr)}
          unit="bpm"
          delta={o.resting_hr_delta_7d}
          goodWhen="down"
          range={[38, 62]}
          marker={o.resting_hr ?? undefined}
        />
        <Biomarker
          label={t("overview.spo2")}
          value={fmtNum(o.spo2_avg, 1)}
          unit="%"
          delta={o.spo2_delta_7d}
          goodWhen="up"
          range={[92, 100]}
          marker={o.spo2_avg ?? undefined}
        />
        <Biomarker
          label={t("overview.respiration")}
          value={fmtNum(o.respiration_avg, 1)}
          unit="br/min"
          range={[11, 17]}
          marker={o.respiration_avg ?? undefined}
        />
        <Biomarker
          label={t("biometrics.weight")}
          value={fmtNum(o.weight_kg, 1)}
          unit="kg"
          range={[60, 90]}
          marker={o.weight_kg ?? undefined}
        />
      </div>
    </Card>
  );
}

function Biomarker({
  label,
  value,
  unit,
  delta,
  goodWhen = "up",
  range,
  marker,
}: {
  label: string;
  value: string;
  unit: string;
  delta?: number | null;
  goodWhen?: "up" | "down";
  range: [number, number];
  marker?: number;
}) {
  return (
    <div className="rounded-card border border-hairline bg-surface2 p-3">
      <div className="flex items-center justify-between">
        <div className="eyebrow truncate">{label}</div>
        <DeltaChip delta={delta} unit={unit === "%" ? "%" : undefined} goodWhen={goodWhen} compact />
      </div>
      <BigStat value={value} unit={unit} size="md" className="mt-1" />
      <div className="mt-2.5">
        <RangeBar min={range[0]} max={range[1]} marker={marker} />
        <div className="num mt-1 flex justify-between text-[9px] text-faint">
          <span>{range[0]}</span>
          <span>{range[1]}</span>
        </div>
      </div>
    </div>
  );
}

function ActivityLog({ o }: { o: Overview }) {
  const { t } = useTranslation();
  return (
    <Card className="col-span-12 xl:col-span-4">
      <CardHeader
        eyebrow={t("overview.calibrated")}
        right={
          <Link
            to="/app/activities"
            className="flex items-center gap-1 text-[11px] font-medium text-primaryText hover:underline"
          >
            {t("overview.telemetry_log")} <ArrowRight size={11} />
          </Link>
        }
      />
      {o.activities.length === 0 ? (
        <Empty>{t("overview.no_activities")}</Empty>
      ) : (
        <div className="flex flex-col gap-2">
          {o.activities.map((a) => (
            <Link
              key={a.id}
              to={`/app/activities/${a.id}`}
              className="rounded-card border border-hairline bg-surface2 p-3 transition-colors hover:bg-surface3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                  <Watch size={14} className="text-muted" />
                  {new Date(a.start_time).toLocaleTimeString(undefined, {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <span className="num rounded-sm bg-hairline px-1.5 py-0.5 text-[10px] text-muted">
                  {fmtDuration(a.duration_s)}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <Metric label={t("activities.distance")} value={`${fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)} km`} />
                <Metric label={t("activities.avg_hr")} value={`${fmtNum(a.avg_hr)} ${t("common.bpm")}`} />
                <Metric label={t("overview.load")} value={fmtNum(a.training_load, 0)} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow truncate">{label}</div>
      <div className="num mt-0.5 text-[13px] font-semibold text-ink">{value}</div>
    </div>
  );
}

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function SleepStrip({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const stages = o.sleep?.stages;
  const total = (stages?.deep_s ?? 0) + (stages?.rem_s ?? 0) + (stages?.light_s ?? 0) + (stages?.awake_s ?? 0);
  const parts = stages && total > 0
    ? [
        { key: "deep", label: "stage.deep", v: stages.deep_s ?? 0, color: "var(--c-stage-deep)" },
        { key: "rem", label: "stage.rem", v: stages.rem_s ?? 0, color: "var(--c-stage-rem)" },
        { key: "light", label: "stage.core", v: stages.light_s ?? 0, color: "var(--c-stage-core)" },
        { key: "awake", label: "stage.awake", v: stages.awake_s ?? 0, color: "var(--c-stage-awake)" },
      ]
    : [];
  return (
    <Card className="col-span-12">
      <CardHeader
        eyebrow={t("overview.last_night")}
        title={
          o.sleep
            ? new Date(o.sleep.start_time).toLocaleDateString(undefined, {
                weekday: "long",
                day: "numeric",
                month: "short",
              })
            : t("sleep.no_night")
        }
        right={
          o.sleep && (
            <Link to="/app/sleep" className="text-[11px] font-medium text-primaryText hover:underline">
              {t("nav.sleep")}
            </Link>
          )
        }
      />
      {o.sleep ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <div className="eyebrow">{t("overview.sleep_score")}</div>
            <BigStat value={fmtNum(o.sleep.sleep_score)} unit="/100" className="mt-1" />
          </div>
          <div>
            <div className="eyebrow">{t("sleep.time_asleep")}</div>
            <BigStat value={fmtHours(o.sleep.total_sleep_s)} className="mt-1" />
          </div>
          <div className="col-span-2">
            <div className="eyebrow mb-2">{t("stage.deep")} / {t("stage.rem")} / {t("stage.core")}</div>
            <div className="flex h-2 w-full gap-0.5 overflow-hidden rounded-full">
              {parts.map((p) => (
                <div
                  key={p.key}
                  className="h-full rounded-full"
                  style={{ width: `${Math.round((p.v / total) * 100)}%`, background: p.color }}
                />
              ))}
            </div>
            <div className="num mt-1.5 flex gap-3 text-[10px] text-muted">
              {parts.map((p) => (
                <span key={p.key}>
                  <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ background: p.color }} />
                  {t(p.label)} {Math.round((p.v / total) * 100)}%
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <Empty>{t("sleep.no_night")}</Empty>
      )}
    </Card>
  );
}

export default function OverviewPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.get<Overview>("/dashboard/overview"),
    refetchInterval: 5 * 60_000,
  });

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorNote />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="eyebrow">{t("app.name")} {t("app.suffix")}</div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            {t("overview.title")}
          </h1>
        </div>
        <div className="num text-[12px] text-muted">
          {new Date(data.date + "T00:00:00").toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
          })}
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <ScoreHero o={data} />
        <BiomarkerStrip o={data} />
        <AcwrBlock o={data} />
        <ActivityLog o={data} />
        <SleepStrip o={data} />
        {data.alerts.length > 0 && (
          <Card className="col-span-12 border-alertSoft">
            <CardHeader eyebrow={t("overview.open_alerts")} />
            <div className="flex flex-col gap-2">
              {data.alerts.map((a, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-sm bg-alertSoft px-2.5 py-1.5 text-[12px] text-alertText"
                >
                  <span className="eyebrow">{a.severity}</span>
                  {a.message}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
