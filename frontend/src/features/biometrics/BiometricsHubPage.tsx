import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { api, type MetricTrend } from "../../app/api";
import {
  Badge,
  Card,
  ErrorNote,
  Loading,
  PageHeader,
  Sparkline,
  fmtNum,
} from "../../components/kit";
import { Tabs } from "../../components/Tabs";
import { assess, METRIC_LABELS, useUnits } from "../../components/data";
import { LabsPanel } from "./LabsPanel";

const GROUPS = [
  {
    value: "signals",
    label: "design.body_signals",
    keys: ["resting_hr", "hrv_deviation", "spo2", "respiration"],
  },
  {
    value: "recovery",
    label: "design.recovery_sleep",
    keys: [
      "readiness",
      "recovery",
      "sleep_score",
      "sleep_duration",
      "sleep_deep",
      "sleep_rem",
      "sleep_light",
      "restlessness",
    ],
  },
  {
    value: "load",
    label: "design.load_risk",
    keys: [
      "strain",
      "acwr",
      "acute_load",
      "chronic_load",
      "illness_risk",
      "injury_risk",
    ],
  },
  {
    value: "body",
    label: "design.body_activity",
    keys: ["weight", "body_fat", "vo2max", "steps", "floors", "hydration"],
  },
];
function MetricRow({ metricKey, unit }: { metricKey: string; unit: string }) {
  const { t } = useTranslation();
  const units = useUnits();
  const trend = useQuery({
    queryKey: ["metric", metricKey, 60],
    queryFn: () => api.get<MetricTrend>("/metrics/" + metricKey + "?days=60"),
  });
  const points = trend.data?.points ?? [];
  const latest = [...points].reverse().find((p) => p.value != null);
  const status = assess(metricKey, latest?.value ?? null);
  const label = METRIC_LABELS[metricKey]
    ? t(METRIC_LABELS[metricKey])
    : metricKey.replaceAll("_", " ");
  return (
    <Link to={"/app/biometrics/" + metricKey} className="metric-row">
      <div>
        <p className="text-[14px] font-medium">{label}</p>
        <p className="mt-1 text-[12px] text-muted">
          {latest?.date ?? t("design.no_measurements")}
        </p>
      </div>
      <div className="num whitespace-nowrap text-[24px] font-medium tracking-[-.04em]">
        {trend.isLoading
          ? "…"
          : fmtNum(
              units.metric(metricKey, latest?.value ?? null),
              ["steps", "floors"].includes(metricKey) ? 0 : 1,
            )}
        <span className="ml-1.5 text-[12px] font-normal tracking-normal text-muted">
          {units.metricUnit(metricKey, unit)}
        </span>
      </div>
      <div className="metric-status">
        <Badge tone={trend.isError ? "alert" : status.tone}>
          {trend.isError
            ? t("design.unavailable")
            : trend.isLoading
              ? t("common.loading")
              : t(status.key)}
        </Badge>
      </div>
      <div className="metric-trend">
        <Sparkline
          points={points.map((p) => p.value)}
          color="var(--c-text-muted)"
          height={30}
        />
      </div>
      <ArrowUpRight size={17} className="metric-arrow text-muted" />
    </Link>
  );
}
export default function BiometricsHubPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const catalog = useQuery({
    queryKey: ["metrics-catalog"],
    queryFn: () =>
      api.get<Record<string, { unit: string; direction: string }>>("/metrics"),
  });
  const extra = Object.keys(catalog.data ?? {}).filter(
    (k) => !GROUPS.some((g) => g.keys.includes(k)),
  );
  const groups = extra.length
    ? [
        ...GROUPS,
        { value: "other", label: "design.other_metrics", keys: extra },
      ]
    : GROUPS;
  const tab = params.get("tab") ?? "signals";
  const active = [...groups.map((g) => g.value), "labs"].includes(tab)
    ? tab
    : "signals";
  const selected = groups.find((g) => g.value === active);
  const keys = (
    search ? Object.keys(catalog.data ?? {}) : (selected?.keys ?? [])
  ).filter((key) => {
    const label = METRIC_LABELS[key]
      ? t(METRIC_LABELS[key])
      : key.replaceAll("_", " ");
    return (
      catalog.data?.[key] && label.toLowerCase().includes(search.toLowerCase())
    );
  });
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("biometrics.title")}
        subtitle={t("design.metrics_sub")}
      />
      <Tabs
        value={active}
        onChange={(v) => {
          setParams({ tab: v });
          setSearch("");
        }}
        label={t("design.metric_groups")}
        options={[
          ...groups.map((g) => ({ value: g.value, label: t(g.label) })),
          { value: "labs", label: t("biometrics.labs") },
        ]}
      />
      {active === "labs" ? (
        <LabsPanel />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-[13px] text-muted">
              {t("design.metric_count", { count: keys.length })} ·{" "}
              {t("design.latest60")}
            </p>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label={t("design.find_metric")}
              placeholder={t("design.find_metric")}
              className="h-10 w-full border-b border-hairline bg-transparent text-[13px] outline-none sm:w-64"
            />
          </div>
          {catalog.isLoading ? (
            <Loading />
          ) : catalog.isError ? (
            <ErrorNote />
          ) : (
            <Card className="!px-5 !py-0 md:!px-8">
              <div className="metric-row !py-4 text-[12px] text-muted max-md:hidden">
                <span>{t("design.metric")}</span>
                <span>{t("biometrics.latest")}</span>
                <span>{t("design.status")}</span>
                <span>{t("biometrics.trend")} · 60d</span>
                <span />
              </div>
              {keys.map((key) => (
                <MetricRow
                  key={key}
                  metricKey={key}
                  unit={catalog.data![key].unit}
                />
              ))}
              {keys.length === 0 && (
                <p className="py-12 text-center text-muted">
                  {t("search.no_results")}
                </p>
              )}
            </Card>
          )}
          <p className="text-[12px] text-muted">{t("design.metric_note")}</p>
        </>
      )}
    </div>
  );
}
