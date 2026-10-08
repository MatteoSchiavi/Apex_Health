import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Star } from "lucide-react";
import { api, type MetricTrend } from "../../app/api";
import {
  Badge,
  Card,
  ErrorNote,
  Loading,
  PageHeader,
  Segmented,
  Sparkline,
  fmtHours,
  fmtNum,
} from "../../components/kit";
import { Tabs } from "../../components/Tabs";
import { assess, METRIC_LABELS, useUnits } from "../../components/data";
import { LabsPanel } from "./LabsPanel";
import { MetricDirection, PersonalRange, RANGE_METRICS } from "../../components/MetricInterpretation";

import { METRIC_GROUPS, LEGACY_METRIC_TABS } from "./groups";
import { useAction, useLab, useToday } from "../lab/shared";

function MetricRow({ metricKey, unit, range, favorite, toggle, pending }: { metricKey: string; unit: string; range: string; favorite: boolean; toggle: () => void; pending: boolean }) {
  const { t } = useTranslation();
  const units = useUnits();
  const trend = useQuery({
    queryKey: ["metric", metricKey, range],
    queryFn: () => api.get<MetricTrend>("/metrics/" + metricKey + "?days=" + range),
  });
  const points = trend.data?.points ?? [];
  const latest = [...points].reverse().find((p) => p.value != null);
  const status = assess(metricKey, latest?.value ?? null);
  const label = METRIC_LABELS[metricKey]
    ? t(METRIC_LABELS[metricKey])
    : metricKey.replaceAll("_", " ");
  return (
    <div className="relative">
    <Link to={"/app/biometrics/" + metricKey} className="metric-row pr-12">
      <div>
        <p className="text-[14px] font-medium">{label}</p>
        <p className="mt-1 text-[12px] text-muted">
          {latest?.date ?? t("design.no_measurements")}
        </p>
      </div>
      <div className="num whitespace-nowrap text-[24px] font-medium tracking-[-.04em]">
        {trend.isLoading
          ? "…"
          : unit === "h" ? fmtHours(latest?.value == null ? null : latest.value * 3600) : fmtNum(
              units.metric(metricKey, latest?.value ?? null),
              ["steps", "floors"].includes(metricKey) ? 0 : 1,
            )}
        <span className="ml-1.5 text-[12px] font-normal tracking-normal text-muted">
          {unit === "h" ? "" : units.metricUnit(metricKey, unit)}
        </span>
      </div>
      <div className="metric-status">
        {RANGE_METRICS.has(metricKey) && trend.data && !trend.isError ? <PersonalRange trend={trend.data} compact /> : <Badge tone={trend.isError ? "alert" : status.tone}>
          {trend.isError
            ? t("design.unavailable")
            : trend.isLoading
              ? t("common.loading")
              : t(status.key)}
        </Badge>}
      </div>
      <div className="metric-trend">
        <Sparkline
          points={points.map((p) => p.value)}
          color="var(--c-text-muted)"
          height={30}
        />
        <MetricDirection metric={metricKey} points={points} />
      </div>
      <span />
    </Link>
    <button type="button" aria-label={t(favorite ? "completion.unstar" : "completion.star", { metric: label })} aria-pressed={favorite} disabled={pending} onClick={toggle} className="absolute right-0 top-1/2 -translate-y-1/2 p-3 text-muted hover:text-ink"><Star size={18} fill={favorite ? "currentColor" : "none"} /></button>
    </div>
  );
}
export default function BiometricsHubPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [range, setRange] = useState("28");
  const catalog = useQuery({
    queryKey: ["metrics-catalog"],
    queryFn: () =>
      api.get<Record<string, { unit: string; direction: string }>>("/metrics"),
  });
  const favoritesQuery = useLab<{ payload: { metrics: string[] } }[]>("/lab/entries?kind=metric_favorites");
  const save = useAction();
  const today = useToday();
  const favorites = favoritesQuery.data?.[0]?.payload.metrics ?? [];
  const requested = params.get("tab") ?? "favorites";
  const legacy = LEGACY_METRIC_TABS[requested];
  const active = legacy?.tab ?? (["favorites", "health", "training", "labs"].includes(requested) ? requested : "favorites");
  const category = METRIC_GROUPS.find(g => g.value === active);
  const groupValue = params.get("group") ?? legacy?.group ?? category?.groups[0].value;
  const subgroup = category?.groups.find(g => g.value === groupValue) ?? category?.groups[0];
  const known = new Set(METRIC_GROUPS.flatMap(c => c.groups.flatMap(g => g.keys)));
  const other = Object.keys(catalog.data ?? {}).filter(k => !known.has(k));
  const selected = active === "favorites" ? favorites : [...(subgroup?.keys ?? []), ...(subgroup?.value === "signals" ? other : [])];
  const keys = (search ? Object.keys(catalog.data ?? {}) : selected).filter(key => {
    const label = METRIC_LABELS[key] ? t(METRIC_LABELS[key]) : key.replaceAll("_", " ");
    return catalog.data?.[key] && (label + " " + key).toLowerCase().includes(search.toLowerCase());
  });
  const toggle = (metric: string) => save.mutate({ path: "/lab/entries", body: { entry: { kind: "metric_favorites", date: today, metrics: favorites.includes(metric) ? favorites.filter(k => k !== metric) : [...favorites, metric] } } });
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("biometrics.title")}
        subtitle={t("design.metrics_sub")}
        actions={<Segmented value={range} onChange={setRange} options={[7, 28, 180].map((days) => ({ value: String(days), label: t("metricView.days" + days) }))} />}
      />
      {subgroup?.value === "estimates" && <p className="text-[13px] text-muted">{t("metricView.estimates_note")}</p>}
      <Tabs
        value={active}
        onChange={(v) => {
          setParams({ tab: v });
          setSearch("");
        }}
        label={t("design.metric_groups")}
        options={[
          { value: "favorites", label: t("completion.favorites") },
          ...METRIC_GROUPS.map((g) => ({ value: g.value, label: t(g.label) })),
          { value: "labs", label: t("biometrics.labs") },
        ]}
      />
      {category && <Segmented value={subgroup!.value} onChange={group => setParams({ tab: active, group })} options={category.groups.map(g => ({ value: g.value, label: t(g.label) }))} />}
      {(save.isError || favoritesQuery.isError) && <ErrorNote />}
      {active === "labs" ? (
        <LabsPanel />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-[13px] text-muted">
              {t("design.metric_count", { count: keys.length })} ·{" "}
              {t("metricView.period", { days: range })}
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
                <span>{t("biometrics.trend")} · {range}d</span>
                <span />
              </div>
              {keys.map((key) => (
                <MetricRow
                  key={key}
                  metricKey={key}
                  unit={catalog.data![key].unit}
                  range={range}
                  favorite={favorites.includes(key)}
                  toggle={() => toggle(key)}
                  pending={save.isPending || favoritesQuery.isLoading || favoritesQuery.isError}
                />
              ))}
              {keys.length === 0 && (
                <p className="py-12 text-center text-muted">
                  {t(active === "favorites" && !search ? "completion.favorites_empty" : "search.no_results")}
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
