/**
 * Overview — the home dashboard (mockup: home_main_dashboard).
 *
 * Layout law (12-col): telemetry status strip; readiness hero (8) beside
 * synthesis diagnosis (4); ACWR load block (8) beside biomarkers (4);
 * calibrated activities (4) + parasympathetic tone (8); last night strip.
 * The dashboard anchors to the day the backend resolved (today, or the
 * most recent day that carries data) and labels that state honestly.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Link2,
  Zap,
} from "lucide-react";
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
  PageHeader,
  RangeBar,
  ScoreBar,
  SportIcon,
  StatPod,
  ZoneBar,
  fmtClock,
  fmtHours,
  fmtNum,
  friendlyDiscipline,
  timeAgo,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

function scoreTone(v: number | null) {
  if (v === null) return "muted" as const;
  if (v >= 75) return "positive" as const;
  if (v >= 50) return "primary" as const;
  if (v >= 35) return "warning" as const;
  return "alert" as const;
}

function stageColor(key: string): string {
  return {
    deep: "var(--c-stage-deep)",
    rem: "var(--c-stage-rem)",
    core: "var(--c-stage-core)",
    light: "var(--c-stage-core)",
    awake: "var(--c-stage-awake)",
  }[key] ?? "var(--c-hairline2)";
}

/* ------------------------------------------------------------- status strip */

function StatusStrip({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const live = o.integration_status.some((i) => i.status === "active");
  const devices = o.integration_status
    .filter((i) => i.status === "active")
    .map((i) => i.provider)
    .join(" + ") || t("overview.no_devices");
  return (
    <Card pad={false} className="rounded-card">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <span className="flex items-center gap-2">
          <span
            className={`relative flex h-2 w-2 ${live ? "" : "opacity-40"}`}
          >
            {live && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60" />
            )}
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${live ? "bg-positive" : "bg-hairline2"}`}
            />
          </span>
          <span className="eyebrow !text-[10px]">
            {t("overview.telemetry_state")}:{" "}
            <span className={live ? "text-positiveText" : "text-muted"}>
              {live ? t("overview.live") : t("overview.paused")}
            </span>
          </span>
        </span>
        <span className="num flex items-center gap-1.5 text-[11px] text-muted">
          <Link2 size={11} />
          {devices}
        </span>
        {o.anchor_is_today ? (
          <Badge tone="positive">{t("overview.validated")}</Badge>
        ) : (
          <Badge tone="warning">{t("overview.showing_history")}</Badge>
        )}
        <span className="num ml-auto hidden text-[10px] tracking-[0.08em] text-faint md:inline">
          {t("overview.epoch")} {o.date}
        </span>
      </div>
    </Card>
  );
}

/* ---------------------------------------------------------------- hero */

function ScoreHero({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const readiness = o.readiness.value;
  const sleep = o.sleep_score.value;
  const readinessLabel =
    readiness === null
      ? "—"
      : readiness >= 75
        ? t("common.optimal")
        : readiness >= 50
          ? t("common.good")
          : t("common.fair");

  return (
    <Card className="col-span-12 xl:col-span-8">
      <CardHeader
        eyebrow={t("overview.adaptive_readiness")}
        title={readinessLabel}
        right={<DeltaChip delta={o.readiness.delta_7d} unit="pts" compact />}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-card border border-hairline bg-surface2 p-4">
          <div className="flex items-center justify-between">
            <div className="eyebrow">{t("overview.system_readiness")}</div>
            <Badge tone={scoreTone(readiness) === "positive" ? "positive" : "neutral"}>
              {readiness !== null && readiness >= 75 ? t("overview.peak_zone") : t("overview.zone")}
            </Badge>
          </div>
          <BigStat value={fmtNum(readiness)} unit="/100" size="xl" className="mt-2" />
          <div className="mt-3">
            <ScoreBar value={readiness ?? 0} tone={scoreTone(readiness)} />
          </div>
          <div className="num mt-2 flex justify-between text-[10px] text-faint">
            <span>{t("overview.floor")}: {fmtNum(Math.max(0, (readiness ?? 0) - 14))}</span>
            <span>{t("overview.avg7")}: {fmtNum(readiness === null ? null : Math.round(readiness))}</span>
            <span>{t("overview.cap")}: {fmtNum(Math.min(100, (readiness ?? 0) + 8))}</span>
          </div>
        </div>
        <div className="rounded-card border border-hairline bg-surface2 p-4">
          <div className="flex items-center justify-between">
            <div className="eyebrow">{t("overview.sleep_score")}</div>
            <DeltaChip delta={o.sleep_score.delta_7d} unit="pts" compact />
          </div>
          <BigStat value={fmtNum(sleep)} unit="/100" size="xl" className="mt-2" />
          <div className="mt-3">
            <ScoreBar value={sleep ?? 0} tone={scoreTone(sleep)} />
          </div>
          <div className="num mt-2 flex justify-between text-[10px] text-faint">
            <span>{fmtHours(o.sleep_hours ? o.sleep_hours * 3600 : null)}</span>
            <span>
              {t("stage.deep")} {fmtNum(o.sleep?.stages.deep_s ? o.sleep.stages.deep_s / 3600 : null, 1)}h
            </span>
            <span>
              {t("stage.rem")} {fmtNum(o.sleep?.stages.rem_s ? o.sleep.stages.rem_s / 3600 : null, 1)}h
            </span>
          </div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-hairline pt-3">
        <MiniStat
          label="CTL"
          value={`${fmtNum(o.chronic_load === null || o.chronic_load === undefined ? null : o.chronic_load / 7, 0)}`}
          unit="TSS/d"
        />
        <MiniStat
          label={t("overview.hrv_norm")}
          value={fmtNum(o.hrv_ms)}
          unit="ms"
          delta={
            o.hrv_baseline_ms && o.hrv_ms
              ? ((o.hrv_ms - o.hrv_baseline_ms) / o.hrv_baseline_ms) * 100
              : null
          }
        />
        <MiniStat
          label={t("overview.freshness")}
          value={
            o.chronic_load && o.acute_load
              ? `${fmtNum(o.chronic_load - o.acute_load / 7, 0)}`
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

/* --------------------------------------------------------- synthesis (AI) */

function SynthesisCard({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const readiness = o.readiness.value;
  const acwr = o.acwr;
  const hrvDelta =
    o.hrv_baseline_ms && o.hrv_ms ? o.hrv_ms - o.hrv_baseline_ms : null;
  const level = readiness === null ? "unknown" : readiness >= 75 ? "optimal" : readiness >= 50 ? "good" : "low";
  const acwrPart =
    acwr === null
      ? t("synth.no_load")
      : acwr > 1.3
        ? t("synth.acwr_high")
        : acwr < 0.8
          ? t("synth.acwr_low")
          : t("synth.acwr_ok");
  const hrvPart =
    hrvDelta === null ? "" : hrvDelta >= 0 ? t("synth.hrv_up") : t("synth.hrv_down");
  const ceiling =
    o.chronic_load !== null && o.chronic_load !== undefined
      ? Math.round((o.chronic_load / 7) * 1.3)
      : null;

  return (
    <Card className="col-span-12 xl:col-span-4">
      <CardHeader
        eyebrow={t("synth.title")}
        right={<Badge tone="neutral">{t("synth.badge")}</Badge>}
      />
      <p className="text-[13px] leading-relaxed text-ink2">
        <span className="font-semibold text-ink">{t(`synth.level_${level}`)}</span>{" "}
        {t("synth.body_prefix")} {acwrPart} {hrvPart}
      </p>
      <div className="mt-4 flex items-center justify-between rounded-card border border-hairline bg-surface2 px-3 py-2">
        <span className="eyebrow">{t("synth.load_ceiling")}</span>
        <span className="num text-[13px] font-semibold text-positiveText">
          {fmtNum(ceiling, 0)} <span className="text-[10px] font-normal text-muted">TSS</span>
        </span>
      </div>
      <Link
        to="/app/coach"
        className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-primaryText hover:underline"
      >
        {t("nav.coach")} <ArrowRight size={11} />
      </Link>
    </Card>
  );
}

/* -------------------------------------------------------------- ACWR block */

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
    grid: { left: 42, right: 42, top: 26, bottom: 22 },
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
      data: [t("overview.acute_load"), t("overview.chronic_load")],
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
    yAxis: [
      {
        type: "value",
        splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
        axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
      },
      {
        type: "value",
        min: 0,
        max: 2.5,
        splitLine: { show: false },
        axisLabel: { show: false },
      },
    ],
    series: [
      {
        name: t("overview.acute_load"),
        type: "bar",
        data: points.map((p) => p.value),
        barMaxWidth: 7,
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
      {
        name: "ACWR",
        type: "line",
        yAxisIndex: 1,
        data: dates.map((_d: string, i: number) => {
          const a = points[i]?.value;
          const ch = chronicPoints[i]?.value;
          return a !== null && a !== undefined && ch ? +(a / (ch * 7 || 1)).toFixed(3) : null;
        }),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: c.warning, width: 1.2, type: "dashed", opacity: 0.8 },
        itemStyle: { color: c.warning },
        markArea: {
          silent: true,
          itemStyle: { color: c.positive, opacity: 0.07 },
          data: [[{ yAxis: 0.8 }, { yAxis: 1.3 }]],
        },
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

/* ------------------------------------------------------------- biomarkers */

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
          zones={[
            { from: 38, to: 50, color: "rgba(34,197,94,0.35)" },
            { from: 50, to: 58, color: "rgba(234,179,8,0.25)" },
            { from: 58, to: 62, color: "rgba(239,68,68,0.25)" },
          ]}
        />
        <Biomarker
          label={t("overview.spo2")}
          value={fmtNum(o.spo2_avg, 1)}
          unit="%"
          delta={o.spo2_delta_7d}
          goodWhen="up"
          range={[92, 100]}
          marker={o.spo2_avg ?? undefined}
          zones={[
            { from: 92, to: 95, color: "rgba(239,68,68,0.25)" },
            { from: 95, to: 98, color: "rgba(234,179,8,0.25)" },
            { from: 98, to: 100, color: "rgba(34,197,94,0.35)" },
          ]}
        />
        <Biomarker
          label={t("overview.respiration")}
          value={fmtNum(o.respiration_avg, 1)}
          unit="br/min"
          range={[11, 17]}
          marker={o.respiration_avg ?? undefined}
          zones={[
            { from: 11, to: 13, color: "rgba(34,197,94,0.35)" },
            { from: 13, to: 16, color: "rgba(234,179,8,0.25)" },
            { from: 16, to: 17, color: "rgba(239,68,68,0.25)" },
          ]}
        />
        <Biomarker
          label={t("biometrics.weight")}
          value={fmtNum(o.weight_kg, 1)}
          unit="kg"
          range={[60, 90]}
          marker={o.weight_kg ?? undefined}
          zones={[
            { from: 60, to: 75, color: "rgba(34,197,94,0.35)" },
            { from: 75, to: 85, color: "rgba(234,179,8,0.25)" },
            { from: 85, to: 90, color: "rgba(239,68,68,0.25)" },
          ]}
        />
        <Biomarker
          label={t("biometrics.vo2max")}
          value={fmtNum(o.vo2max, 1)}
          unit="ml/kg/min"
          range={[30, 65]}
          marker={o.vo2max ?? undefined}
          zones={[
            { from: 30, to: 40, color: "rgba(239,68,68,0.25)" },
            { from: 40, to: 50, color: "rgba(234,179,8,0.25)" },
            { from: 50, to: 65, color: "rgba(34,197,94,0.35)" },
          ]}
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
  zones,
}: {
  label: string;
  value: string;
  unit: string;
  delta?: number | null;
  goodWhen?: "up" | "down";
  range: [number, number];
  marker?: number;
  zones?: { from: number; to: number; color: string }[];
}) {
  return (
    <div className="rounded-card border border-hairline bg-surface2 p-3">
      <div className="flex items-center justify-between">
        <div className="eyebrow truncate">{label}</div>
        <DeltaChip delta={delta} unit={unit === "%" ? "%" : undefined} goodWhen={goodWhen} compact />
      </div>
      <BigStat value={value} unit={unit} size="md" className="mt-1" />
      <div className="mt-2.5">
        <RangeBar min={range[0]} max={range[1]} marker={marker} zones={zones} />
        <div className="num mt-1 flex justify-between text-[9px] text-faint">
          <span>{range[0]}</span>
          <span>{range[1]}</span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------ calibrated activities */

function Metric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="eyebrow truncate">{label}</div>
      <div className="num mt-0.5 text-[13px] font-semibold text-ink">
        {value}
        {unit && <span className="ml-0.5 text-[9px] font-normal text-muted">{unit}</span>}
      </div>
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

/* -------------------------------------------------- parasympathetic (HRV) */

function HrvToneStrip({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const norm30 = o.hrv_norm_30d ?? null;
  return (
    <Card className="col-span-12 xl:col-span-8">
      <CardHeader
        eyebrow={t("overview.para_tone")}
        right={
          <span className="num text-[10px] tracking-[0.08em] text-faint">
            rMSSD · {t("overview.sleep_epochs")}
          </span>
        }
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatPod
          label={t("overview.last_night")}
          value={fmtNum(o.hrv_ms)}
          unit="ms"
          sub={
            o.hrv_baseline_ms && o.hrv_ms
              ? `${o.hrv_ms >= o.hrv_baseline_ms ? "+" : ""}${(o.hrv_ms - o.hrv_baseline_ms).toFixed(1)} ${t("overview.vs_mean")}`
              : undefined
          }
          tone={o.hrv_baseline_ms && o.hrv_ms && o.hrv_ms >= o.hrv_baseline_ms ? "positive" : "ink"}
        />
        <StatPod
          label={t("overview.baseline7")}
          value={fmtNum(o.hrv_baseline_ms)}
          unit="ms"
          sub={`${t("overview.rolling")}`}
        />
        <StatPod
          label={t("overview.norm30")}
          value={fmtNum(norm30)}
          unit="ms"
          sub={`${t("overview.band")}: ${fmtNum(norm30 === null ? null : norm30 - 5, 0)}–${fmtNum(norm30 === null ? null : norm30 + 5, 0)} ms`}
        />
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------- page */

export default function OverviewPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const date = params.get("date") ?? undefined;
  const { data, isLoading, isError } = useQuery({
    queryKey: ["overview", date ?? "latest"],
    queryFn: () =>
      api.get<Overview>(`/dashboard/overview${date ? `?date=${date}` : ""}`),
    refetchInterval: 5 * 60_000,
  });

  if (isLoading) return <Loading />;
  if (isError || !data) return <ErrorNote />;

  const shift = (days: number) => {
    const base = data.date + "T00:00:00";
    const d = new Date(base);
    d.setDate(d.getDate() + days);
    const iso = d.toISOString().slice(0, 10);
    setParams(iso === new Date().toISOString().slice(0, 10) ? {} : { date: iso });
  };
  const isToday = data.anchor_is_today;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("overview.title")}
        subtitle={t("overview.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <div className="num flex items-center gap-1 rounded-control border border-hairline bg-surface px-1">
              <button
                type="button"
                aria-label={t("common.prev_day")}
                onClick={() => shift(-1)}
                className="flex h-7 w-7 items-center justify-center text-muted hover:text-ink"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="min-w-[110px] text-center text-[11px] text-ink2">
                {new Date(data.date + "T00:00:00").toLocaleDateString(undefined, {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                })}
              </span>
              <button
                type="button"
                aria-label={t("common.next_day")}
                disabled={isToday}
                onClick={() => shift(1)}
                className="flex h-7 w-7 items-center justify-center text-muted hover:text-ink disabled:opacity-30"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        }
      />

      <StatusStrip o={data} />

      {!isToday && (
        <div className="flex items-center gap-2 rounded-card border border-warning/30 bg-warningSoft px-3 py-2 text-[12px] text-warningText">
          <Zap size={13} />
          {t("overview.history_notice", { date: data.date })}
        </div>
      )}

      {/* full-empty state: nothing recorded for the anchor day at all */}
      {data.readiness.value === null &&
        data.resting_hr === null &&
        data.hrv_ms === null &&
        data.sleep === null &&
        data.activities.length === 0 && (
          <Card>
            <Empty
              action={
                <Link
                  to="/app/settings"
                  className="inline-flex h-8 items-center gap-2 rounded-control bg-primary px-3 text-[13px] font-medium text-white hover:brightness-110"
                >
                  <Link2 size={13} /> {t("overview.connect_cta")}
                </Link>
              }
            >
              {t("overview.empty_body")}
            </Empty>
          </Card>
        )}

      <div className="grid grid-cols-12 gap-4">
        <ScoreHero o={data} />
        <SynthesisCard o={data} />
        <AcwrBlock o={data} />
        <BiomarkerStrip o={data} />
        <HrvToneStrip o={data} />
        <div className="col-span-12 xl:col-span-4">
          <ActivityLogColumn o={data} />
        </div>
        <SleepStripCol o={data} />
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

/* Wrapper keeping the mockup's 4/8 split inside a 12-col grid: activities
   right column, HRV strip left, sleep strip full width. */

function ActivityLogColumn({ o }: { o: Overview }) {
  const { t } = useTranslation();
  return (
    <Card className="h-full">
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
                <div className="flex min-w-0 items-center gap-2 text-[13px] font-semibold text-ink">
                  <SportIcon discipline={a.discipline} className="shrink-0 text-muted" />
                  <span className="truncate">{friendlyDiscipline(a.discipline, t)}</span>
                </div>
                <span className="num shrink-0 rounded-sm bg-hairline px-1.5 py-0.5 text-[10px] text-muted">
                  {fmtDuration(a.duration_s)}
                </span>
              </div>
              <div className="num mt-1 text-[10px] text-faint">
                {timeAgo(a.start_time)} {t("activities.ago")}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <Metric label={t("activities.distance")} value={`${fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)}`} unit="km" />
                <Metric label={t("activities.avg_hr")} value={`${fmtNum(a.avg_hr)}`} unit="bpm" />
                <Metric label={t("overview.load")} value={fmtNum(a.training_load, 0)} unit="TSS" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function SleepStripCol({ o }: { o: Overview }) {
  const { t } = useTranslation();
  const stages = o.sleep?.stages;
  const parts = stages
    ? [
        { key: "deep", label: "stage.deep", v: stages.deep_s ?? 0 },
        { key: "rem", label: "stage.rem", v: stages.rem_s ?? 0 },
        { key: "light", label: "stage.core", v: stages.light_s ?? 0 },
        { key: "awake", label: "stage.awake", v: stages.awake_s ?? 0 },
      ].filter((p) => p.v > 0)
    : [];
  const total = parts.reduce((a, p) => a + p.v, 0);
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
            <Link
              to={`/app/sleep/${o.sleep.start_time.slice(0, 10)}`}
              className="text-[11px] font-medium text-primaryText hover:underline"
            >
              {t("sleep.night_detail")} <ArrowRight size={10} className="inline" />
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
            <BigStat value={fmtClock(o.sleep.total_sleep_s)} className="mt-1" />
          </div>
          <div className="col-span-2">
            <div className="eyebrow mb-2">{t("sleep.architecture")}</div>
            <ZoneBar
              parts={parts.map((p) => ({
                key: p.key,
                value: p.v,
                color: stageColor(p.key),
                label: t(p.label),
              }))}
            />
            <div className="num mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted">
              {parts.map((p) => (
                <span key={p.key} className="flex items-center gap-1">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ background: stageColor(p.key) }}
                  />
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
