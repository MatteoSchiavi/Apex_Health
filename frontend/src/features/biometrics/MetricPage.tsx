/**
 * Metric detail — the generic per-metric telemetry page (mockup
 * "heart_rate_telemetry_analysis" pattern): hero stat + delta, range
 * segmented control, full trend chart with range band, stats table.
 *
 * The route param is the metric KEY (same catalog as GET /metrics), so the
 * page renders itself for any metric — no per-metric bespoke code.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api, type MetricTrend } from "../../app/api";
import {
  Card,
  CardHeader,
  DeltaChip,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  Segmented,
  StatPod,
  fmtNum,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

const LABEL_KEYS: Record<string, string> = {
  readiness: "biometrics.readiness_metric",
  recovery: "biometrics.recovery_metric",
  strain: "biometrics.strain_metric",
  sleep_score: "biometrics.readiness_metric",
  acwr: "biometrics.acwr_metric",
  acute_load: "biometrics.acute_load_metric",
  chronic_load: "biometrics.chronic_load_metric",
  hrv_deviation: "biometrics.hrv",
  illness_risk: "biometrics.illness_risk",
  injury_risk: "biometrics.injury_risk",
  resting_hr: "biometrics.resting_hr",
  weight: "biometrics.weight",
  body_fat: "biometrics.body_fat",
  vo2max: "biometrics.vo2max",
  steps: "biometrics.steps",
  floors: "biometrics.floors",
  spo2: "biometrics.spo2",
  hydration: "biometrics.hydration",
  sleep_duration: "biometrics.sleep_duration",
  sleep_deep: "biometrics.sleep_deep_metric",
  sleep_rem: "biometrics.sleep_rem_metric",
  sleep_light: "biometrics.sleep_light_metric",
  respiration: "biometrics.respiration_metric",
  restlessness: "biometrics.restlessness_metric",
};

const RANGES = ["7d", "30d", "90d", "180d", "365d"] as const;
type Range = (typeof RANGES)[number];

const RANGE_DAYS: Record<Range, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
  "180d": 180,
  "365d": 365,
};

export default function MetricPage() {
  const { key = "" } = useParams();
  const { t } = useTranslation();
  const c = useChartTheme();
  const [range, setRange] = useState<Range>("90d");

  const catalog = useQuery({
    queryKey: ["metrics-catalog"],
    queryFn: () => api.get<Record<string, { unit: string; direction: string }>>("/metrics"),
  });
  const trend = useQuery({
    queryKey: ["metric", key, range],
    queryFn: () => api.get<MetricTrend>(`/metrics/${key}?days=${RANGE_DAYS[range]}`),
    enabled: !!key,
  });

  if (trend.isLoading || catalog.isLoading) return <Loading />;
  if (trend.isError || !trend.data) return <ErrorNote />;
  const data = trend.data;
  const meta = catalog.data?.[key];
  const goodWhen = meta?.direction ?? "up";
  const labelKey = LABEL_KEYS[key] ?? "biometrics.title";

  const points = data.points;
  const hasData = points.some((p) => p.value !== null);
  const values = points.filter((p) => p.value !== null).map((p) => p.value!) as number[];
  const latest = values.at(-1) ?? null;

  const stats = data.stats ?? {};
  const delta = stats.delta_30d as number | null | undefined;

  const option = {
    grid: { left: 42, right: 12, top: 20, bottom: 26 },
    tooltip: {
      trigger: "axis",
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
    },
    xAxis: {
      type: "time",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
    },
    series: [
      {
        type: "line",
        data: points.map((p) => [p.date, p.value]),
        showSymbol: false,
        smooth: true,
        lineStyle: { color: c.primary, width: 2 },
        itemStyle: { color: c.primary },
        areaStyle: { color: c.primary, opacity: 0.08 },
        markArea:
          stats.min != null && stats.max != null
            ? {
                silent: true,
                itemStyle: { color: c.primary, opacity: 0.04 },
                data: [[{ yAxis: stats.min }, { yAxis: stats.max }]],
              }
            : undefined,
        markLine:
          stats.mean != null
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: c.muted, type: "dashed", width: 1 },
                label: { show: false },
                data: [{ yAxis: stats.mean }],
              }
            : undefined,
      },
    ],
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t(labelKey)}
        subtitle={t("biometrics.page_subtitle", { unit: data.unit })}
        actions={
          <Segmented
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ value: r, label: t(`biometrics.${r}`) }))}
          />
        }
      />

      {!hasData ? (
        <Empty>{t("biometrics.no_data")}</Empty>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <StatPod
              label={t("biometrics.latest")}
              value={fmtNum(latest, 1)}
              unit={data.unit}
              right={
                <DeltaChip
                  delta={delta}
                  unit=""
                  goodWhen={goodWhen === "down" ? "down" : "up"}
                  compact
                />
              }
            />
            <StatPod label={t("biometrics.mean")} value={fmtNum(stats.mean as number, 1)} unit={data.unit} />
            <StatPod label={t("biometrics.min")} value={fmtNum(stats.min as number, 1)} unit={data.unit} />
            <StatPod label={t("biometrics.max")} value={fmtNum(stats.max as number, 1)} unit={data.unit} />
            <StatPod label={t("biometrics.count")} value={fmtNum(stats.count as number, 0)} unit="" />
          </div>

          <Card>
            <CardHeader
              eyebrow={t("biometrics.trend")}
              right={
                <span className="num text-[11px] text-faint">
                  {data.start_date} → {data.end_date}
                </span>
              }
            />
            <EChart option={option} height={320} />
          </Card>
        </>
      )}
    </div>
  );
}
