"use client";

/**
 * Apex Health — Biometrics hub (re-skin per ui-language/RULES.md).
 *
 * Reference: OverviewPage.tsx — "Body signals" title, a page sentence,
 * grouped rows (label · value · status dot · sparkline), no 24-card grid.
 *
 * Layout:
 *   - Page title "Body signals" + a page sentence + the search input.
 *   - Today vs baseline: a focus row of compact tiles — HRV, Resting HR,
 *     Sleep score, SpO₂ — each = label · value · StatusDot · sparkline.
 *     No borders.
 *   - Grouped rows (Recovery, Cardiovascular, Sleep, Body, Performance)
 *     with the `Row` primitive. No cards, no "LOW" chip, no source badge.
 *   - Lab Panel table at the bottom (unchanged shape, sentence-case
 *     headers).
 */

import { useEffect, useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { metricCatalog, labMarkers, getMetricTrend } from "@/lib/apex/data";
import {
  Card,
  Section,
  StatusDot,
  PageSentence,
  Sparkline,
  InfoButton,
  MetricInfoContent,
  Hairline,
} from "@/components/apex/kit";
import { fmtNum, fmtDate } from "@/lib/apex/format";
import { getMetricExplanation } from "@/lib/apex/metricInfo";
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

function decimalsFor(key: string): number {
  if (["weight", "acwr", "skin_temp", "respiration"].includes(key)) return 2;
  if (["spo2", "sleep_efficiency"].includes(key)) return 1;
  return 0;
}

/** Catalog group order — recovery first (the hero signal), lab last. */
const GROUP_ORDER: Array<MetricCatalogItem["group"]> = [
  "recovery",
  "cardio",
  "sleep",
  "body",
  "performance",
];

const GROUP_LABEL: Record<MetricCatalogItem["group"], string> = {
  recovery: "Recovery",
  cardio: "Cardiovascular",
  sleep: "Sleep",
  body: "Body composition",
  performance: "Performance",
  lab: "Lab panels",
};

/** The four "today vs baseline" focus metrics — one Row each. */
const FOCUS_KEYS = ["hrv", "resting_hr", "sleep_score", "spo2"] as const;

/* ----------------------------------------------------------- LabPanel row */

function LabRow({ marker }: { marker: LabMarker }) {
  const toneMap: Record<
    LabMarker["status"],
    "ok" | "watch" | "alert" | "neutral"
  > = {
    normal: "ok",
    low: "alert",
    high: "alert",
    borderline: "watch",
    unknown: "neutral",
  };
  const statusLabel: Record<LabMarker["status"], string> = {
    normal: "Normal",
    low: "Low",
    high: "High",
    borderline: "Borderline",
    unknown: "—",
  };
  const dp = labDecimals(marker.value);
  return (
    <tr className="border-b border-hairline last:border-0 hover:bg-surface2/40">
      <td className="px-4 py-2.5 text-[14px] font-medium text-ink">{marker.label}</td>
      <td className="px-4 py-2.5 text-right">
        <span className="num text-ink">{fmtNum(marker.value, dp)}</span>
        <span className="ml-1 text-[12px] text-ink3">{marker.unit}</span>
      </td>
      <td className="px-4 py-2.5 text-right">
        <span className="num text-ink3">
          {fmtNum(marker.ref_low, dp)}–{fmtNum(marker.ref_high, dp)}
        </span>
      </td>
      <td className="px-4 py-2.5 text-right">
        <StatusDot tone={toneMap[marker.status]} label={statusLabel[marker.status]} />
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
  const ui = useApexUi();
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-recent-metrics");
      if (raw) setRecent(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

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
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ====== Header ====== */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="page-title">Body signals</h1>
          <PageSentence className="mt-2">
            Your measurements, compared against your own 30-day baseline.
          </PageSentence>
        </div>
        <div className="relative w-full max-w-[240px]">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter metrics…"
            aria-label="Filter metrics"
            className="num h-9 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 text-[14px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
          />
        </div>
      </div>

      {/* ====== Today vs baseline — the focus row (no borders) ====== */}
      {!query && (
        <Card>
          <Section label="Today vs baseline">
            <div className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
              {FOCUS_KEYS.map((k) => {
                const m = metricCatalog.find((it) => it.key === k);
                if (!m) return null;
                return (
                  <FocusRow
                    key={k}
                    m={m}
                    onSelect={() => selectMetric(k)}
                  />
                );
              })}
            </div>
          </Section>
        </Card>
      )}

      {/* ====== Recently viewed (rows) ====== */}
      {!query && recent.length > 0 && (
        <Card pad={false}>
          <div className="px-7 pt-7">
            <div className="mb-3 flex items-center gap-1.5 text-[14px] font-medium text-ink2">
              <Clock size={13} />
              Recently viewed
            </div>
          </div>
          <div className="px-7">
            {recent
              .map((key) => metricCatalog.find((m) => m.key === key))
              .filter((m): m is MetricCatalogItem => !!m)
              .map((m) => (
                <MetricRow
                  key={`recent-${m.key}`}
                  m={m}
                  onSelect={() => selectMetric(m.key)}
                />
              ))}
          </div>
        </Card>
      )}

      {/* ====== Metric groups (rows, not cards) ====== */}
      {GROUP_ORDER.map((g) => {
        const items = grouped.get(g);
        if (!items || items.length === 0) return null;
        return (
          <Card pad={false} key={g}>
            <div className="px-7 pt-7 pb-3">
              <div className="text-[14px] font-medium text-ink2">{GROUP_LABEL[g]}</div>
            </div>
            <div className="px-7 pb-7 divide-y divide-[var(--c-divider)]">
              {items.map((m) => (
                <MetricRow
                  key={m.key}
                  m={m}
                  onSelect={() => selectMetric(m.key)}
                />
              ))}
            </div>
          </Card>
        );
      })}

      {visibleCount === 0 && (
        <Card>
          <div className="text-[14px] text-ink2">
            No metrics match <span className="num">{query}</span>.
          </div>
        </Card>
      )}

      {/* ====== Lab Panel ====== */}
      <Card pad={false}>
        <div className="px-7 pt-7 pb-3 flex flex-wrap items-end justify-between gap-3">
          <div className="text-[14px] font-medium text-ink2">{GROUP_LABEL.lab}</div>
          {labDate && (
            <div className="num text-[12px] text-ink3">
              Drawn {fmtDate(labDate)}
            </div>
          )}
        </div>
        <div className="px-7 pb-4 overflow-x-auto scroll-area">
          <table className="w-full min-w-[560px] text-[14px]">
            <thead>
              <tr className="border-b border-hairline text-left">
                <th className="px-1 py-2.5 text-[14px] font-medium text-ink2">Marker</th>
                <th className="px-1 py-2.5 text-right text-[14px] font-medium text-ink2">Last</th>
                <th className="px-1 py-2.5 text-right text-[14px] font-medium text-ink2">Reference range</th>
                <th className="px-1 py-2.5 text-right text-[14px] font-medium text-ink2">Status</th>
              </tr>
            </thead>
            <tbody>
              {labMarkers.map((m) => (
                <LabRow key={m.key} marker={m} />
              ))}
            </tbody>
          </table>
        </div>
        <Hairline />
        <div className="flex items-start gap-2 px-7 py-3">
          <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-alert/60" aria-hidden />
          <div className="text-[12px] leading-[16px] text-ink3">
            Lab interpretation is informational only — consult a clinician before acting.
          </div>
        </div>
      </Card>
    </div>
  );
}

/* ----------------------------------------------------- Focus row (today vs baseline)
 * A compact tile (not bordered) for the 4 hero metrics: label · value ·
 * StatusDot · sparkline. */
function FocusRow({
  m,
  onSelect,
}: {
  m: MetricCatalogItem;
  onSelect: () => void;
}) {
  const trend = getMetricTrend(m.key, 30);
  const last = trend.stats.last;
  const mean = trend.stats.mean;
  const sd = standardDeviation(trend.points.map((p) => p.value));
  const status = computeMetricStatus(last, mean, sd);
  const sparkData = trend.points.slice(-14).map((p) => p.value);
  const sparkColor =
    status.tone === "ok"
      ? "var(--c-ok)"
      : status.tone === "alert"
      ? "var(--c-alert)"
      : "var(--c-text-3)";

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-4 py-3 text-left transition-colors hover:bg-surface2 -mx-2 px-2 rounded-[var(--radius-control)]"
    >
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-medium text-ink2">{m.label}</div>
        <div className="mt-1">
          <StatusDot tone={status.tone} label={status.label} />
        </div>
      </div>
      <div className="shrink-0">
        <Sparkline data={sparkData} color={sparkColor} width={90} height={32} />
      </div>
      <div className="num flex shrink-0 items-baseline gap-1 text-ink">
        <span className="text-[24px] font-semibold">{fmtNum(last, decimalsFor(m.key))}</span>
        <span className="text-[13px] text-ink2">{m.unit}</span>
      </div>
    </button>
  );
}

/* ----------------------------------------------------- Metric row (grouped)
 * A div-based row (the kit `Row` renders as a `<button>` when onClick is
 * passed, but we need a nested `<InfoButton>` which is also a `<button>` —
 * and you can't nest buttons). So we use a div with role="button".
 * Layout: label · sparkline · StatusDot · value. No borders, no "LOW"
 * chip, no source badge. */
function MetricRow({
  m,
  onSelect,
}: {
  m: MetricCatalogItem;
  onSelect: () => void;
}) {
  const trend = getMetricTrend(m.key, 30);
  const last = trend.stats.last;
  const mean = trend.stats.mean;
  const sd = standardDeviation(trend.points.map((p) => p.value));
  const status = computeMetricStatus(last, mean, sd);
  const sparkData = trend.points.slice(-14).map((p) => p.value);
  const sparkColor =
    status.tone === "ok"
      ? "var(--c-ok)"
      : status.tone === "alert"
      ? "var(--c-alert)"
      : "var(--c-text-3)";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="flex w-full items-center gap-4 py-3 text-left transition-colors hover:bg-surface2 -mx-2 px-2 rounded-[var(--radius-control)] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 cursor-pointer"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <span className="text-[14px] font-medium text-ink2">{m.label}</span>
          <span
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            className="inline-flex"
          >
            <InfoButton title={m.label}>
              <MetricInfoContent {...getMetricExplanation(m.key)} />
            </InfoButton>
          </span>
        </div>
      </div>
      <div className="shrink-0">
        <Sparkline data={sparkData} color={sparkColor} width={90} height={32} />
      </div>
      <div className="shrink-0">
        <StatusDot tone={status.tone} label={status.label} />
      </div>
      <div className="num flex shrink-0 items-baseline gap-1 text-ink">
        <span className="text-[20px] font-semibold">{fmtNum(last, decimalsFor(m.key))}</span>
        <span className="text-[13px] text-ink2">{m.unit}</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------- helpers */
function standardDeviation(values: (number | null)[]): number | null {
  const valid = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (valid.length < 2) return null;
  const mean = valid.reduce((s, v) => s + v, 0) / valid.length;
  const variance = valid.reduce((s, v) => s + (v - mean) ** 2, 0) / valid.length;
  return Math.sqrt(variance);
}

/** Computed status from the latest value vs a personal band (30-day mean
 *  ± 1 SD). When there's no usable baseline, returns a neutral "—". */
function computeMetricStatus(
  last: number | null,
  mean: number | null,
  sd: number | null,
): { label: string; tone: "neutral" | "ok" | "watch" | "alert" } {
  if (last === null || mean === null) return { label: "—", tone: "neutral" };
  if (sd === null || sd === 0) return { label: "—", tone: "neutral" };
  if (last < mean - sd) return { label: "Low", tone: "alert" };
  if (last > mean + sd) return { label: "High", tone: "alert" };
  return { label: "In range", tone: "ok" };
}
