"use client";

/**
 * Apex Health — Metric detail.
 *
 * Route purpose: "How has this metric changed?"
 *
 * The detail view shows one metric across a selectable time window (7 / 28 /
 * 90 days) with a hero stat + 7d/28d deltas, a four-up stat pod row, an inline
 * SVG line chart (with baseline reference and Y / X axes), a calm context
 * panel that frames the latest value against the personal 28-day baseline,
 * and a footer carrying source provenance and a data-completeness note.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Download } from "lucide-react";
import { useT, useI18n } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { metricCatalog, getMetricTrend } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  StatPod,
  DeltaChip,
  SourcePill,
  BackLink,
  Segmented,
  Eyebrow,
  ApexButton,
} from "@/components/apex/kit";
import { fmtNum, fmtDate, fmtDelta } from "@/lib/apex/format";
import type { MetricTrend } from "@/lib/apex/types";
import { exportCsv } from "@/lib/apex/csv";

/* ----------------------------------------------------- metric meta helpers */

/** Per-metric semantic direction — what counts as "good". */
const GOOD_WHEN: Record<string, "up" | "down" | "none"> = {
  hrv: "up",
  spo2: "up",
  vo2max: "up",
  readiness: "up",
  sleep_score: "up",
  sleep_efficiency: "up",
  deep_sleep: "up",
  rem_sleep: "up",
  total_sleep: "up",
  hrv_norm: "up",
  resting_hr: "down",
  acwr: "down",
  respiration: "down",
  weight: "down",
  skin_temp: "none",
};

function decimalsFor(key: string): number {
  if (["weight", "acwr", "skin_temp", "respiration"].includes(key)) return 2;
  if (["spo2", "sleep_efficiency"].includes(key)) return 1;
  return 0;
}

function colorForGroup(group: string): string {
  switch (group) {
    case "recovery":
      return "var(--c-positive)";
    case "performance":
      return "var(--c-positive)";
    case "cardio":
      return "var(--c-primary)";
    case "sleep":
      return "var(--c-primary)";
    case "body":
      return "var(--c-text-faint)";
    case "lab":
      return "var(--c-text-faint)";
    default:
      return "var(--c-primary)";
  }
}

type RangeKey = "7" | "28" | "90";

function daysFor(r: RangeKey): number {
  return r === "7" ? 7 : r === "28" ? 28 : 90;
}

/* ----------------------------------------------------------- MetricChart */

function MetricChart({
  trend,
  color,
  dp,
  baselineLabel,
  emptyLabel,
}: {
  trend: MetricTrend;
  color: string;
  dp: number;
  baselineLabel: string;
  emptyLabel: string;
}) {
  const { locale } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(760);
  const H = 260;
  const pad = { top: 16, right: 24, bottom: 32, left: 56 };

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setW(Math.max(320, Math.floor(r.width)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const plotW = Math.max(1, w - pad.left - pad.right);
  const plotH = H - pad.top - pad.bottom;
  const pts = trend.points;

  const validIdxs: number[] = [];
  for (let i = 0; i < pts.length; i++) {
    if (pts[i].value !== null && Number.isFinite(pts[i].value as number)) {
      validIdxs.push(i);
    }
  }

  if (validIdxs.length < 2) {
    return (
      <div
        ref={ref}
        className="flex items-center justify-center text-[12px] text-muted"
        style={{ height: H }}
      >
        {emptyLabel}
      </div>
    );
  }

  const validVals = validIdxs.map((i) => pts[i].value as number);
  let minV = Math.min(...validVals);
  let maxV = Math.max(...validVals);
  const span = maxV - minV || 1;
  minV -= span * 0.1;
  maxV += span * 0.1;
  const range = maxV - minV || 1;

  const n = pts.length;
  const xFor = (i: number) => pad.left + (n === 1 ? 0 : (i / (n - 1)) * plotW);
  const yFor = (v: number) => pad.top + plotH - ((v - minV) / range) * plotH;

  // Line + area paths
  let lineD = "";
  let firstX = 0;
  let lastX = 0;
  let lastY = 0;
  validIdxs.forEach((idx, k) => {
    const x = xFor(idx);
    const y = yFor(pts[idx].value as number);
    if (k === 0) {
      lineD += `M${x.toFixed(1)},${y.toFixed(1)}`;
      firstX = x;
    } else {
      lineD += ` L${x.toFixed(1)},${y.toFixed(1)}`;
    }
    lastX = x;
    lastY = y;
  });
  const areaD = `${lineD} L${lastX.toFixed(1)},${(pad.top + plotH).toFixed(
    1
  )} L${firstX.toFixed(1)},${(pad.top + plotH).toFixed(1)} Z`;

  // Baseline reference (28d-equivalent baseline from stats)
  const baseline = trend.stats.baseline;
  const baselineY =
    baseline !== null && baseline >= minV && baseline <= maxV
      ? yFor(baseline)
      : null;

  // Y axis ticks: max, mid, min
  const yTicks = [
    { v: maxV, y: pad.top },
    { v: (maxV + minV) / 2, y: pad.top + plotH / 2 },
    { v: minV, y: pad.top + plotH },
  ];

  // X axis ticks: start, middle, end
  const midIdx = Math.floor((n - 1) / 2);
  const xTicks = [
    { i: 0, anchor: "start" as const, label: fmtDate(pts[0].date, locale) },
    {
      i: midIdx,
      anchor: "middle" as const,
      label: fmtDate(pts[midIdx].date, locale),
    },
    {
      i: n - 1,
      anchor: "end" as const,
      label: fmtDate(pts[n - 1].date, locale),
    },
  ];

  return (
    <div ref={ref} className="w-full" style={{ height: H }}>
      <svg
        width={w}
        height={H}
        viewBox={`0 0 ${w} ${H}`}
        className="block"
        aria-label={`${trend.label} trend`}
        role="img"
      >
        {/* Y axis grid + labels */}
        {yTicks.map((yt, i) => (
          <g key={`y-${i}`}>
            <line
              x1={pad.left}
              x2={w - pad.right}
              y1={yt.y}
              y2={yt.y}
              stroke="var(--c-hairline)"
              strokeWidth={1}
              shapeRendering="crispEdges"
            />
            <text
              x={pad.left - 8}
              y={yt.y + 3.5}
              textAnchor="end"
              fontSize={10}
              className="mono"
              fill="var(--c-text-muted)"
            >
              {fmtNum(yt.v, dp)}
            </text>
          </g>
        ))}

        {/* Baseline reference line */}
        {baselineY !== null && (
          <g>
            <line
              x1={pad.left}
              x2={w - pad.right}
              y1={baselineY}
              y2={baselineY}
              stroke={color}
              strokeWidth={1}
              strokeDasharray="4 4"
              opacity={0.55}
            />
            <text
              x={w - pad.right}
              y={baselineY - 5}
              textAnchor="end"
              fontSize={9}
              className="eyebrow"
              fill="var(--c-text-muted)"
            >
              {baselineLabel}
            </text>
          </g>
        )}

        {/* Area fill */}
        <path d={areaD} fill={color} fillOpacity={0.07} stroke="none" />

        {/* Trend line */}
        <path
          d={lineD}
          fill="none"
          stroke={color}
          strokeWidth={1.75}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Last point */}
        <circle
          cx={lastX}
          cy={lastY}
          r={3.25}
          fill={color}
          stroke="var(--c-surface)"
          strokeWidth={1.5}
        />

        {/* X axis tick labels */}
        {xTicks.map((xt, i) => (
          <text
            key={`x-${i}`}
            x={xFor(xt.i)}
            y={H - pad.bottom + 18}
            textAnchor={xt.anchor}
            fontSize={10}
            className="mono"
            fill="var(--c-text-muted)"
          >
            {xt.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

/* ----------------------------------------------------------- MetricPage */

export function MetricPage() {
  const t = useT();
  const ui = useApexUi();
  const [range, setRange] = useState<RangeKey>("90");
  const key = ui.selectedMetricKey ?? "hrv";

  const meta = useMemo(
    () => metricCatalog.find((m) => m.key === key) ?? metricCatalog[0],
    [key]
  );
  const days = daysFor(range);
  const trend = useMemo(() => getMetricTrend(key, days), [key, days]);

  const goodWhen = GOOD_WHEN[key] ?? "up";
  const color = colorForGroup(meta.group);
  const last = trend.stats.last;
  const baseline = trend.stats.baseline;
  const dp = decimalsFor(key);

  // Personal-baseline framing
  const vsBaseline =
    last !== null && baseline !== null ? last - baseline : null;

  // Data completeness — count of non-null points / total
  const dataCount = trend.points.filter((p) => p.value !== null).length;
  const totalDays = trend.points.length;

  return (
    <div className="mx-auto max-w-[1240px] px-1 py-2">
      <div className="mb-4">
        <BackLink onClick={() => ui.setView("biometrics")}>
          {t("biometrics.back_to_catalog")}
        </BackLink>
      </div>

      <PageHeader
        title={meta.label}
        subtitle={
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <SourcePill>{meta.source}</SourcePill>
            <span className="eyebrow">{t(`biometrics.group_${meta.group}`)}</span>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">{t("activities.export")}</span>
            </ApexButton>
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => {
                exportCsv(
                  `apex-metric-${meta.key}-${range}d`,
                  ["Date", `${meta.label} (${meta.unit})`],
                  trend.points.map((p) => [p.date, p.value ?? ""])
                );
              }}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">CSV</span>
            </ApexButton>
            <Segmented<RangeKey>
              value={range}
              onChange={(v) => setRange(v)}
              options={[
                { value: "7", label: t("biometrics.range_7d") },
                { value: "28", label: t("biometrics.range_28d") },
                { value: "90", label: t("biometrics.range_90d") },
              ]}
            />
          </div>
        }
      />

      {/* Hero block */}
      <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
        <Card className="flex flex-col justify-between">
          <Eyebrow>{t("biometrics.last")}</Eyebrow>
          <div className="mt-2 flex items-end gap-4">
            <BigStat
              size="xl"
              value={fmtNum(last, dp)}
              unit={meta.unit}
              tone="ink"
            />
            <div className="mb-1.5 flex flex-col gap-1.5">
              <DeltaChip
                delta={trend.stats.delta_7d}
                goodWhen={goodWhen}
                suffix={t("overview.vs7d")}
              />
              <DeltaChip
                delta={trend.stats.delta_28d}
                goodWhen={goodWhen}
                suffix={t("overview.vs28d")}
              />
            </div>
          </div>
          {vsBaseline !== null && (
            <div className="mt-3 flex items-center gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-1.5">
              <DeltaChip
                delta={vsBaseline}
                goodWhen={goodWhen}
                compact
                showSuffix={false}
              />
              <span className="num text-[11px] text-muted">
                {t("overview.vs_baseline")}
              </span>
            </div>
          )}
        </Card>

        {/* Stats grid — 4 pods */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
          <StatPod
            label={t("biometrics.mean")}
            value={fmtNum(trend.stats.mean, dp)}
            unit={meta.unit}
          />
          <StatPod
            label={t("biometrics.min")}
            value={fmtNum(trend.stats.min, dp)}
            unit={meta.unit}
          />
          <StatPod
            label={t("biometrics.max")}
            value={fmtNum(trend.stats.max, dp)}
            unit={meta.unit}
          />
          <StatPod
            label={t("biometrics.baseline")}
            value={fmtNum(trend.stats.baseline, dp)}
            unit={meta.unit}
          />
        </div>
      </div>

      {/* Main chart */}
      <Card className="mt-4" pad={false}>
        <div className="flex items-center justify-between gap-3 px-4 pt-3.5">
          <Eyebrow>
            {t(`biometrics.range_${range}d`)} · {meta.label}
          </Eyebrow>
          <span className="num text-[11px] text-faint">
            {fmtDate(trend.start_date)} → {fmtDate(trend.end_date)}
          </span>
        </div>
        <div className="px-2 pb-2">
          <MetricChart
            trend={trend}
            color={color}
            dp={dp}
            baselineLabel={t("biometrics.baseline")}
            emptyLabel={t("biometrics.no_data")}
          />
        </div>
      </Card>

      {/* Context panel */}
      <Card className="mt-4">
        <CardHeader eyebrow={t("biometrics.view_trend")} title={meta.label} />
        <p className="text-[13px] leading-[20px] text-ink2">
          {meta.description}
        </p>
        {vsBaseline !== null && (
          <div className="mt-3 flex items-center gap-2 text-[12px] text-muted">
            <span className="num font-semibold text-ink2">
              {fmtDelta(vsBaseline, meta.unit, dp)}
            </span>
            <span>{t("overview.vs_baseline")}</span>
          </div>
        )}
      </Card>

      {/* Footer — provenance + data completeness */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3 text-[11px] text-muted">
        <div className="flex items-center gap-2">
          <SourcePill>{meta.source}</SourcePill>
          <span className="eyebrow">{t("biometrics.source")}</span>
        </div>
        <div className="num flex items-center gap-2">
          <span>
            {dataCount} / {totalDays}
          </span>
          <span className="text-faint">·</span>
          <span>{t(`biometrics.range_${range}d`)}</span>
        </div>
      </div>
    </div>
  );
}
