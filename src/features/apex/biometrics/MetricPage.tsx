"use client";

/**
 * Apex Health — Metric detail (re-skin per ui-language/RULES.md).
 *
 * Reference: OverviewPage.tsx — hero + StatusDot + InteractiveLineChart +
 * rows for stats.
 *
 * Layout:
 *   - BackLink, page title = metric name (with InfoButton), a page
 *     sentence ("Your HRV over the last 30 days"), range Segmented, CSV /
 *     print buttons.
 *   - Hero card: the current value at 40px text-ink + a StatusDot + two
 *     DeltaChips (7d, 28d).
 *   - Chart card: InteractiveLineChart with the baseline band + the latest
 *     point marked. ChartInfoBadge next to the title.
 *   - Stats card: rows (Mean, Min, Max, Baseline) — no bordered tiles.
 *   - Context panel: a calm paragraph framing the latest value against
 *     the personal baseline.
 *   - Footer: source + data completeness.
 */

import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { metricCatalog, getMetricTrend } from "@/lib/apex/data";
import {
  Card,
  Section,
  StatusDot,
  Row,
  PageSentence,
  ChartFrame,
  BigStat,
  BackLink,
  Segmented,
  DeltaChip,
  ApexButton,
  InfoButton,
  MetricInfoContent,
  scoreTone,
  rangeTone,
  acwrTone,
  toneFor,
  type DataTone,
} from "@/components/apex/kit";
import { InteractiveLineChart, ChartInfoBadge, ChartLegend } from "@/components/apex/charts";
import { fmtNum, fmtDate, fmtDelta } from "@/lib/apex/format";
import { getMetricExplanation } from "@/lib/apex/metricInfo";
import { exportCsv } from "@/lib/apex/csv";

/* ----------------------------------------------------- metric meta helpers */

const GOOD_WHEN: Record<string, "up" | "down" | "none"> = {
  hrv: "up",
  hrv_norm: "up",
  spo2: "up",
  vo2max: "up",
  readiness: "up",
  sleep_score: "up",
  sleep_efficiency: "up",
  deep_sleep: "up",
  rem_sleep: "up",
  total_sleep: "up",
  resting_hr: "down",
  acwr: "down",
  respiration: "down",
  weight: "down",
  skin_temp: "none",
};

const LABEL_GUARD: Record<string, string> = {
  sleep_score: "Sleep Score",
  readiness: "Readiness Score",
};

function decimalsFor(key: string): number {
  if (["weight", "acwr", "skin_temp", "respiration"].includes(key)) return 2;
  if (["spo2", "sleep_efficiency"].includes(key)) return 1;
  return 0;
}

/** State-based chart color. Per RULES principle 5, the data color reflects
 *  state (good / watch / alert), not the accent. The accent is reserved
 *  for non-data UI. Returns a CSS `var(--c-…)` token. */
function stateColorFor(key: string, value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "var(--c-text-3)";
  let tone: DataTone;
  switch (key) {
    case "readiness":
    case "recovery":
    case "sleep_score":
      tone = scoreTone(value);
      break;
    case "acwr":
      tone = acwrTone(value);
      break;
    case "spo2":
      tone = rangeTone(value, 95, 100);
      break;
    case "respiration":
      tone = rangeTone(value, 12, 20);
      break;
    case "sleep_efficiency":
      tone = rangeTone(value, 85, 100);
      break;
    case "vo2max":
      tone = "positive";
      break;
    case "skin_temp":
      tone = "muted";
      break;
    default:
      tone = "muted";
  }
  switch (tone) {
    case "positive":
      return "var(--c-ok)";
    case "warning":
      return "var(--c-watch)";
    case "alert":
      return "var(--c-alert)";
    default:
      return "var(--c-text-3)";
  }
}

/** Map a metric value to a DataTone for the hero StatusDot. */
function stateToneFor(key: string, value: number | null): DataTone {
  if (value === null || !Number.isFinite(value)) return "muted";
  switch (key) {
    case "readiness":
    case "recovery":
    case "sleep_score":
      return scoreTone(value);
    case "acwr":
      return acwrTone(value);
    case "spo2":
      return rangeTone(value, 95, 100);
    case "respiration":
      return rangeTone(value, 12, 20);
    case "sleep_efficiency":
      return rangeTone(value, 85, 100);
    case "vo2max":
      return "positive";
    case "skin_temp":
      return "muted";
    default:
      return "muted";
  }
}

function statusWord(t: DataTone): string {
  return t === "positive" ? "Good" : t === "warning" ? "Watch" : t === "alert" ? "Alert" : "—";
}

function statusDot(t: DataTone): "neutral" | "ok" | "watch" | "alert" {
  return t === "positive" ? "ok" : t === "warning" ? "watch" : t === "alert" ? "alert" : "neutral";
}

type RangeKey = "7" | "28" | "90";

function daysFor(r: RangeKey): number {
  return r === "7" ? 7 : r === "28" ? 28 : 90;
}

function rangeLabel(r: RangeKey): string {
  return r === "7" ? "7 days" : r === "28" ? "28 days" : "90 days";
}

/* ----------------------------------------------------------- MetricPage */

export function MetricPage({
  range: rangeProp,
  setRange: setRangeProp,
}: {
  range?: RangeKey;
  setRange?: (r: RangeKey) => void;
} = {}) {
  const ui = useApexUi();
  const [internalRange, setInternalRange] = useState<RangeKey>("90");
  const range = rangeProp ?? internalRange;
  const setRange = setRangeProp ?? setInternalRange;

  const key = ui.selectedMetricKey ?? "hrv";

  const meta = useMemo(() => {
    const found = metricCatalog.find((m) => m.key === key) ?? metricCatalog[0];
    const guard = LABEL_GUARD[key];
    return guard && found.label !== guard ? { ...found, label: guard } : found;
  }, [key]);
  const trend = useMemo(() => getMetricTrend(key, daysFor(range)), [key, range]);

  const goodWhen = GOOD_WHEN[key] ?? "up";
  const last = trend.stats.last;
  const baseline = trend.stats.baseline;
  const dp = decimalsFor(key);

  const chartColor = stateColorFor(key, last);
  const heroTone = stateToneFor(key, last);

  const vsBaseline = last !== null && baseline !== null ? last - baseline : null;

  const dataCount = trend.points.filter((p) => p.value !== null).length;
  const totalDays = trend.points.length;

  const pageSentence = `${meta.label} over the last ${rangeLabel(range).toLowerCase()}`;

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ====== Header ====== */}
      <div>
        <BackLink onClick={() => ui.setView("biometrics")}>Back to body signals</BackLink>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="page-title flex items-center gap-2">
              <span>{meta.label}</span>
              <InfoButton title={meta.label}>
                <MetricInfoContent {...getMetricExplanation(key)} />
              </InfoButton>
            </h1>
            <PageSentence className="mt-2">{pageSentence}</PageSentence>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">Print</span>
            </ApexButton>
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => {
                exportCsv(
                  `apex-metric-${meta.key}-${range}d`,
                  ["Date", `${meta.label} (${meta.unit})`],
                  trend.points.map((p) => [p.date, p.value ?? ""]),
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
                { value: "7", label: "7d" },
                { value: "28", label: "28d" },
                { value: "90", label: "90d" },
              ]}
            />
          </div>
        </div>
      </div>

      {/* ====== Hero — current value (40px text-ink) + StatusDot ====== */}
      <Card>
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-[14px] font-medium text-ink2">Latest reading</div>
            <div className="num mt-2 flex items-baseline gap-2 text-ink">
              <span className="text-[40px] font-semibold leading-none">{fmtNum(last, dp)}</span>
              <span className="text-[16px] text-ink2">{meta.unit}</span>
            </div>
            <div className="mt-3">
              <StatusDot tone={statusDot(heroTone)} label={statusWord(heroTone)} />
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            <DeltaChip
              delta={trend.stats.delta_7d}
              goodWhen={goodWhen}
              suffix="vs 7d"
            />
            <DeltaChip
              delta={trend.stats.delta_28d}
              goodWhen={goodWhen}
              suffix="vs 28d"
            />
            {vsBaseline !== null && (
              <div className="num text-[14px] text-ink3">
                {fmtDelta(vsBaseline, meta.unit, dp)} vs baseline
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* ====== Chart (principle 8: one line + baseline + latest point) ====== */}
      <Card>
        <Section label={`${rangeLabel(range)} · ${meta.label}`}>
          <ChartFrame
            info={
              <ChartInfoBadge
                text={
                  <span>
                    <strong className="text-ink2">{meta.label}</strong> over the last {rangeLabel(range).toLowerCase()}.
                    {" "}The dashed line is your 28-day baseline; the latest point is marked.
                  </span>
                }
              />
            }
          >
            <InteractiveLineChart
              categories={trend.points.map((p) => ({ label: fmtDate(p.date, ui.locale) }))}
              series={[
                {
                  name: meta.label,
                  color: chartColor,
                  values: trend.points.map((p) => p.value),
                },
              ]}
              baseline={baseline}
              baselineLabel="28-day baseline"
              height={220}
              formatValue={(v) => (v === null ? "—" : `${fmtNum(v, dp)} ${meta.unit}`)}
            />
            <ChartLegend
              className="mt-3"
              items={[
                { name: meta.label, color: chartColor },
              ]}
            />
            <div className="num mt-2 text-[12px] text-ink3">
              {fmtDate(trend.start_date, ui.locale)} → {fmtDate(trend.end_date, ui.locale)}
            </div>
          </ChartFrame>
        </Section>
      </Card>

      {/* ====== Stats — rows, not bordered tiles ====== */}
      <Card pad={false}>
        <div className="px-7 pt-7 pb-3">
          <div className="text-[14px] font-medium text-ink2">Summary</div>
        </div>
        <div className="px-7 pb-7 divide-y divide-[var(--c-divider)]">
          <Row label="Mean" value={fmtNum(trend.stats.mean, dp)} unit={meta.unit} />
          <Row label="Min" value={fmtNum(trend.stats.min, dp)} unit={meta.unit} />
          <Row label="Max" value={fmtNum(trend.stats.max, dp)} unit={meta.unit} />
          <Row label="Baseline" value={fmtNum(trend.stats.baseline, dp)} unit={meta.unit} />
        </div>
      </Card>

      {/* ====== Context panel ====== */}
      <Card>
        <Section label="What this measures">
          <p className="text-[14px] leading-[22px] text-ink2">
            {meta.description}
          </p>
          {vsBaseline !== null && (
            <div className="mt-3 flex items-center gap-2 text-[14px] text-ink2">
              <span className="num font-semibold text-ink">
                {fmtDelta(vsBaseline, meta.unit, dp)}
              </span>
              <span>vs your baseline</span>
            </div>
          )}
        </Section>
      </Card>

      {/* ====== Footer — provenance + data completeness ====== */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4 text-[14px] text-ink3">
        <div className="flex items-center gap-2">
          <span>Source</span>
          <span className="num font-medium text-ink2">{meta.source}</span>
        </div>
        <div className="num flex items-center gap-2">
          <span>{dataCount} / {totalDays} days</span>
          <span>·</span>
          <span>{rangeLabel(range)}</span>
        </div>
      </div>
    </div>
  );
}
