"use client";

/**
 * Apex Health — Biometrics hub / catalog.
 *
 * Route purpose: "What are my measurements doing?"
 *
 * A directory/explorer of every metric the backend exposes, grouped by
 * physiological domain. The catalog is read dynamically from the data layer
 * (no hard-coded list) so adding a metric to the backend surfaces it here
 * automatically. A search input filters by label as the user types.
 *
 * Below the metric catalog: a Lab Panel section — visually separated to
 * communicate the seriousness of clinical bloodwork. Each marker carries
 * its reference range and a status badge (normal / low / high / borderline).
 * The footer carries the medical disclaimer.
 */

import { useEffect, useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { metricCatalog, labMarkers, getMetricTrend } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  DeltaChip,
  Badge,
  SectionHeader,
  Empty,
  SourcePill,
  Sparkline,
  Hairline,
} from "@/components/apex/kit";
import { fmtNum, fmtDate } from "@/lib/apex/format";
import type { LabMarker, MetricCatalogItem } from "@/lib/apex/types";

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

/** Display decimals by metric key (mirrors the data layer's rounding logic). */
function decimalsFor(key: string): number {
  if (["weight", "acwr", "skin_temp", "respiration"].includes(key)) return 2;
  if (["spo2", "sleep_efficiency"].includes(key)) return 1;
  return 0;
}

/** Sparkline / chart color by metric group. */
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

/** Catalog group order — recovery first (the hero signal), lab last. */
const GROUP_ORDER: Array<MetricCatalogItem["group"]> = [
  "recovery",
  "cardio",
  "sleep",
  "body",
  "performance",
];

/* ----------------------------------------------------------- LabPanel row */

function LabRow({ marker, t }: { marker: LabMarker; t: (p: string) => string }) {
  const toneMap: Record<
    LabMarker["status"],
    "positive" | "alert" | "warning" | "neutral"
  > = {
    normal: "positive",
    low: "alert",
    high: "alert",
    borderline: "warning",
    unknown: "neutral",
  };
  const statusLabel: Record<LabMarker["status"], string> = {
    normal: t("biometrics.status_normal"),
    low: t("biometrics.status_low"),
    high: t("biometrics.status_high"),
    borderline: t("biometrics.status_borderline"),
    unknown: t("biometrics.status_unknown"),
  };
  const dp = labDecimals(marker.value);
  return (
    <tr className="border-b border-hairline last:border-0 hover:bg-surface2/40">
      <td className="px-4 py-2.5 font-medium text-ink">{marker.label}</td>
      <td className="px-4 py-2.5 text-right">
        <span className="mono text-ink">
          {fmtNum(marker.value, dp)}
        </span>
        <span className="ml-1 text-[11px] text-faint">{marker.unit}</span>
      </td>
      <td className="px-4 py-2.5 text-right">
        <span className="mono text-muted">
          {fmtNum(marker.ref_low, dp)}–{fmtNum(marker.ref_high, dp)}
        </span>
      </td>
      <td className="px-4 py-2.5 text-right">
        <Badge tone={toneMap[marker.status]} dot>
          {statusLabel[marker.status]}
        </Badge>
      </td>
    </tr>
  );
}

function labDecimals(v: number | null): number {
  if (v === null || Number.isInteger(v)) return 0;
  const frac = v.toString().split(".")[1] ?? "";
  return Math.min(frac.length, 2);
}

/* ----------------------------------------------------------- BiometricsPage */

export function BiometricsPage() {
  const t = useT();
  const ui = useApexUi();
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]); // recently-viewed metric keys

  // Load recent metrics from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-recent-metrics");
      if (raw) setRecent(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  // Wrap ui.selectMetric to also persist the key
  const selectMetric = (key: string) => {
    setRecent((cur) => {
      const next = [key, ...cur.filter((x) => x !== key)].slice(0, 6);
      try {
        window.localStorage.setItem("apex-recent-metrics", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
    ui.selectMetric(key);
    ui.setView("metric");
  };

  /** Group catalog by `group`, filtered by the live search query. */
  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? metricCatalog.filter((m) => m.label.toLowerCase().includes(q))
      : metricCatalog;
    const map = new Map<string, MetricCatalogItem[]>();
    for (const m of filtered) {
      if (!map.has(m.group)) map.set(m.group, []);
      map.get(m.group)!.push(m);
    }
    return map;
  }, [query]);

  const visibleCount = Array.from(grouped.values()).reduce((s, xs) => s + xs.length, 0);
  const labDate = labMarkers[0]?.date;

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader
        title={t("biometrics.title")}
        subtitle={t("biometrics.hub_subtitle")}
        actions={
          <div className="relative w-full max-w-[240px]">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("biometrics.search")}
              aria-label={t("biometrics.search")}
              className="num h-9 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
          </div>
        }
      />

      {/* Metric catalog — clean grid, no huge spacing */}
      <div className="mt-4 space-y-6">
        {/* Recent metrics */}
        {!query && recent.length > 0 && (
          <section>
            <SectionHeader eyebrow={
              <span className="flex items-center gap-1.5">
                <Clock size={11} className="text-primaryText" />
                Recently viewed
              </span>
            } />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {recent
                .map((key) => metricCatalog.find((m) => m.key === key))
                .filter((m): m is MetricCatalogItem => !!m)
                .map((m) => (
                  <MetricCard key={`recent-${m.key}`} m={m} t={t} onSelect={selectMetric} />
                ))}
            </div>
          </section>
        )}

        {/* Metric groups */}
        {GROUP_ORDER.map((g) => {
          const items = grouped.get(g);
          if (!items || items.length === 0) return null;
          return (
            <section key={g}>
              <SectionHeader eyebrow={t(`biometrics.group_${g}`)} />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {items.map((m) => (
                  <MetricCard key={m.key} m={m} t={t} onSelect={selectMetric} />
                ))}
              </div>
            </section>
          );
        })}

        {visibleCount === 0 && (
          <Empty title={t("biometrics.no_data")} body={<span className="mono">{query}</span>} />
        )}
      </div>

      {/* Lab Panel */}
      <section className="mt-8">
        <SectionHeader
          eyebrow={t("biometrics.group_lab")}
          title={t("biometrics.lab_panel_title")}
          right={
            labDate && (
              <div className="num text-[11px] text-muted">
                {t("biometrics.lab_drawn")} · {fmtDate(labDate)}
              </div>
            )
          }
        />
        <Card pad={false} className="overflow-hidden">
          <div className="overflow-x-auto scroll-area">
            <table className="w-full min-w-[560px] text-[13px]">
              <thead>
                <tr className="border-b border-hairline text-left">
                  <th className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                    {t("overview.biomarkers")}
                  </th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                    {t("biometrics.last")}
                  </th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                    {t("biometrics.ref_range")}
                  </th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                    {t("settings.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {labMarkers.map((m) => (
                  <LabRow key={m.key} marker={m} t={t} />
                ))}
              </tbody>
            </table>
          </div>
          <Hairline />
          <div className="flex items-start gap-2 px-4 py-2.5">
            <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-alert/60" aria-hidden />
            <div className="text-[11px] leading-[16px] text-alert/70">
              {t("biometrics.lab_disclaimer")}
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}

/* ----------------------------------------------------- Metric card (cell) */

/**
 * Plan §5 finding: the hub's "Low / High / Fair" badge used to come from the
 * catalog's `direction` field (which says whether lower-or-higher is better),
 * NOT whether the current value is low or high. This helper COMPUTES a status
 * from the latest value vs a personal band (30-day mean ± 1 SD). When there is
 * no usable baseline (no data, or zero variance) it returns a neutral "—"
 * instead of a misleading Low/High.
 */
function computeMetricStatus(
  last: number | null,
  mean: number | null,
  sd: number | null,
  t: (p: string) => string,
): { label: string; tone: "neutral" | "positive" | "alert" } {
  if (last === null || mean === null) return { label: "—", tone: "neutral" };
  if (sd === null || sd === 0) return { label: "—", tone: "neutral" };
  if (last < mean - sd) return { label: t("biometrics.status_low"), tone: "alert" };
  if (last > mean + sd) return { label: t("biometrics.status_high"), tone: "alert" };
  // TODO i18n — main agent will add a biometrics.in_range key
  return { label: "In range", tone: "positive" };
}

function MetricCard({
  m,
  t,
  onSelect,
}: {
  m: MetricCatalogItem;
  t: (p: string) => string;
  onSelect: (key: string) => void;
}) {
  const trend = getMetricTrend(m.key, 30);
  const last = trend.stats.last;
  const mean = trend.stats.mean;
  const delta7 = trend.stats.delta_7d;
  const sparkData = trend.points.slice(-14).map((p) => p.value);
  const goodWhen = GOOD_WHEN[m.key] ?? "up";
  const color = colorForGroup(m.group);

  // Plan §5: computed status from latest vs personal band (mean ± 1 SD).
  const validVals = trend.points
    .map((p) => p.value)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const sd =
    validVals.length > 1 && mean !== null
      ? Math.sqrt(
          validVals.reduce((s, v) => s + (v - mean) ** 2, 0) / validVals.length,
        )
      : null;
  const status = computeMetricStatus(last, mean, sd, t);

  return (
    <button
      type="button"
      onClick={() => onSelect(m.key)}
      className="group flex w-full flex-col gap-2 rounded-[var(--radius-card)] border border-hairline bg-surface p-4 text-left transition-all hover:border-hairline2 hover:bg-surface2"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[13px] font-semibold text-ink">{m.label}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone={status.tone} dot>
            {status.label}
          </Badge>
          <SourcePill>{m.source}</SourcePill>
        </div>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="num text-[24px] font-bold tracking-[-0.02em] text-ink">
            {fmtNum(last, decimalsFor(m.key))}
            <span className="text-[11px] font-medium text-muted"> {m.unit}</span>
          </div>
          <div className="mt-1">
            <DeltaChip delta={delta7} goodWhen={goodWhen} suffix={t("overview.vs7d")} compact />
          </div>
        </div>
        <Sparkline data={sparkData} color={color} width={100} height={36} />
      </div>
    </button>
  );
}
