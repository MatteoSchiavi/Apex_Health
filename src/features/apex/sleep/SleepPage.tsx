"use client";

/**
 * Apex Health — Sleep list (re-skin per ui-language/RULES.md).
 *
 * Reference: OverviewPage.tsx — sentence-case labels, status dots not
 * coloured numbers, rows not cards, one chart per principle 8.
 *
 * Layout:
 *   - Page title "Sleep" + a page sentence derived from the avg score.
 *   - Summary row (no bordered tiles): avg duration · avg score · regularity
 *     · sleep debt. Each is a 14px sentence-case label, a 40px text-ink
 *     number, and a StatusDot.
 *   - Sleep score trend: InteractiveLineChart wrapped in ChartFrame. The
 *     "your normal" band is the 30-day mean; the latest point is marked.
 *   - Nights list: compact rows. Each row = date · bed→wake · duration ·
 *     score (with StatusDot) · stage mini-bar. No borders.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApexUi } from "@/lib/apex";
import {
  Card,
  Section,
  StatusDot,
  PageSentence,
  ChartFrame,
  BigStat,
  PageHeader,
  Empty,
  Loading,
  Segmented,
  ApexButton,
  scoreTone,
  type DataTone,
} from "@/components/apex/kit";
import { InteractiveLineChart, ChartInfoBadge, ChartLegend } from "@/components/apex/charts";
import { fmtHours, fmtNum, fmtClock, fmtDateLong } from "@/lib/apex/format";
import {
  STAGE_VARS,
  DEFAULT_SLEEP_TARGET_S,
  timeAsleepS,
  type StageKey,
} from "@/lib/apex/sleepHelpers";

type RangeKey = "7d" | "30d" | "90d";
const RANGE_DAYS: Record<RangeKey, number> = { "7d": 7, "30d": 30, "90d": 90 };
const PAGE_SIZE = 20;

/** Short date label "12 Sep" for chart x-axis ticks. */
function shortDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

interface SessionItem {
  local_date: string;
  start_time: string;
  end_time: string;
  total_sleep_s: number | null;
  deep_s: number | null;
  light_s: number | null;
  rem_s: number | null;
  awake_s: number | null;
  sleep_score: number | null;
  respiration_avg: number | null;
  spo2_avg: number | null;
  restlessness: number | null;
  sources: string[];
  resting_hr: number | null;
  hrv_ms: number | null;
  hrv_deviation_ms: number | null;
  hrv_deviation_sd: number | null;
}

interface VitalStats {
  mean: number | null;
  sd: number | null;
  low: number | null;
  high: number | null;
  count: number;
}

interface BaselineBlock {
  window_days: number;
  target_s: number;
  sleep_scores: {
    p33: number | null;
    p66: number | null;
    mean: number | null;
    sd: number | null;
    count: number;
  };
  stages: Record<
    StageKey,
    { mean_s: number | null; mean_pct: number | null }
  >;
  vitals: {
    resting_hr: VitalStats;
    hrv_ms: VitalStats;
    spo2_avg: VitalStats;
    respiration_avg: VitalStats;
  };
}

interface SleepListResponse {
  ok: boolean;
  error?: string;
  items: SessionItem[];
  count: number;
  baseline: BaselineBlock;
  all_dates: string[];
}

interface SleepSummaryResponse {
  ok: boolean;
  error?: string;
  window_days: number;
  count: number;
  avg_duration_s: number | null;
  avg_score: number | null;
  target_s: number;
  regularity_bed_sd_min: number | null;
  regularity_wake_sd_min: number | null;
  median_bedtime: number | null;
  median_wake: number | null;
  sleep_debt_s: number;
}

export function SleepPage() {
  const ui = useApexUi();
  const [range, setRange] = useState<RangeKey>("30d");
  const [items, setItems] = useState<SessionItem[]>([]);
  const [baseline, setBaseline] = useState<BaselineBlock | null>(null);
  const [allDates, setAllDates] = useState<string[]>([]);
  const [shown, setShown] = useState(PAGE_SIZE);
  const [summary, setSummary] = useState<SleepSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const days = RANGE_DAYS[range];

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listRes, sumRes] = await Promise.all([
        fetch(`/api/sleep?days=${days}`),
        fetch(`/api/sleep/summary?days=${days}`),
      ]);
      const list: SleepListResponse = await listRes.json();
      if (!list.ok) throw new Error(list.error || "Failed to load sleep");
      setItems(list.items);
      setBaseline(list.baseline);
      setAllDates(list.all_dates);
      setShown(PAGE_SIZE);
      const sum: SleepSummaryResponse = await sumRes.json();
      setSummary(sum.ok ? sum : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const loadMore = useCallback(() => {
    setLoadingMore(true);
    setTimeout(() => {
      setShown((s) => Math.min(items.length, s + PAGE_SIZE));
      setLoadingMore(false);
    }, 80);
  }, [items.length]);

  // ─────────────────────────────────────────────────────────────── derived
  const chartItems = useMemo(() => [...items].reverse(), [items]);
  const visibleItems = useMemo(() => items.slice(0, shown), [items, shown]);

  // Page sentence (principle 1) — derived from the avg score.
  const pageSentence = useMemo(() => {
    const avg = summary?.avg_score ?? null;
    const count = summary?.count ?? 0;
    if (count === 0) return "No sleep data in this range yet. Sync a source to see your nights.";
    if (avg === null) return `You have ${count} ${count === 1 ? "night" : "nights"} here, but none are scored yet.`;
    const tone = scoreTone(avg);
    if (tone === "positive") return `Your sleep is holding up — averaging ${fmtNum(avg, 0)}/100 across ${count} nights.`;
    if (tone === "warning") return `Your sleep is fair — averaging ${fmtNum(avg, 0)}/100. A consistent bedtime would lift it.`;
    return `Your sleep is below your norm — averaging ${fmtNum(avg, 0)}/100. Prioritise an earlier bedtime.`;
  }, [summary]);

  // ─────────────────────────────────────────────────────────────────── render
  if (loading && !items.length) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <PageHeader title="Sleep" />
        <div className="mt-6">
          <Loading label="Loading sleep…" />
        </div>
      </div>
    );
  }

  if (error && !items.length) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <PageHeader title="Sleep" />
        <div className="mt-6">
          <Empty title={error} body="Try reloading the page." />
        </div>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <PageHeader title="Sleep" />
        <PageSentence className="mt-2">No sleep data in this range yet.</PageSentence>
        <div className="mt-6">
          <Empty
            title={"No sleep data in this range"}
            body={"Connect a source (Garmin, Whoop, Oura) to see your nights here."}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ====== Header (principle 1: page title + page sentence) ====== */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="page-title">Sleep</h1>
          <PageSentence className="mt-2">{pageSentence}</PageSentence>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Segmented<RangeKey>
            value={range}
            onChange={setRange}
            options={[
              { value: "7d", label: "7d" },
              { value: "30d", label: "30d" },
              { value: "90d", label: "90d" },
            ]}
          />
        </div>
      </div>

      {/* ====== Summary row (principle 9: rows, not bordered tiles) ====== */}
      <Card>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryStat
            label="Avg duration"
            value={fmtHours(summary?.avg_duration_s ?? null)}
            status={
              <StatusDot
                tone={durationTone(summary?.avg_duration_s ?? null, summary?.target_s ?? DEFAULT_SLEEP_TARGET_S)}
                label={durationWord(summary?.avg_duration_s ?? null, summary?.target_s ?? DEFAULT_SLEEP_TARGET_S)}
              />
            }
            foot={`Target ${fmtHours(summary?.target_s ?? DEFAULT_SLEEP_TARGET_S)}`}
          />
          <SummaryStat
            label="Avg sleep score"
            value={fmtNum(summary?.avg_score ?? null, 0)}
            status={
              <StatusDot
                tone={scoreToDot(scoreTone(summary?.avg_score ?? null))}
                label={scoreWord(scoreTone(summary?.avg_score ?? null))}
              />
            }
            foot={
              baseline?.sleep_scores.count
                ? `${baseline.sleep_scores.count} nights scored`
                : "No scored nights"
            }
          />
          <SummaryStat
            label="Regularity"
            value={`${fmtNum(combinedSD(summary), 0)}m`}
            status={
              <StatusDot
                tone={regularityTone(combinedSD(summary))}
                label={regularityWord(combinedSD(summary))}
              />
            }
            foot={
              <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-0.5">
                <span>
                  <span className="text-ink3">Bed</span>{" "}
                  <span className="num font-semibold text-ink2">±{fmtNum(summary?.regularity_bed_sd_min ?? null, 0)}m</span>
                </span>
                <span>
                  <span className="text-ink3">Wake</span>{" "}
                  <span className="num font-semibold text-ink2">±{fmtNum(summary?.regularity_wake_sd_min ?? null, 0)}m</span>
                </span>
              </span>
            }
          />
          <SummaryStat
            label="Sleep debt"
            value={formatDebtHours(summary?.sleep_debt_s ?? 0)}
            status={
              <StatusDot
                tone={debtTone(summary?.sleep_debt_s ?? 0)}
                label={debtWord(summary?.sleep_debt_s ?? 0)}
              />
            }
            foot={`Last 7 nights vs ${fmtHours(summary?.target_s ?? DEFAULT_SLEEP_TARGET_S)}`}
          />
        </div>
      </Card>

      {/* ====== Sleep score trend (principle 8: one line + baseline band) ====== */}
      <Card>
        <Section label="Sleep score trend">
          {chartItems.length >= 2 ? (
            <ChartFrame
              title="Nightly score"
              info={
                <ChartInfoBadge
                  text={
                    <span>
                      <strong className="text-ink2">Sleep score</strong> is a 0–100 synthesis of
                      duration and deep+REM ratio. The dashed line is your 30-day mean.
                    </span>
                  }
                />
              }
            >
              <InteractiveLineChart
                categories={chartItems.map((it) => ({ label: shortDate(it.local_date) }))}
                series={[
                  {
                    name: "Sleep score",
                    color: "var(--c-accent)",
                    values: chartItems.map((it) => it.sleep_score),
                  },
                ]}
                baseline={baseline?.sleep_scores.mean ?? null}
                baselineLabel="30-day mean"
                height={160}
                formatValue={(v) => (v === null ? "—" : `${Math.round(v)} / 100`)}
              />
              <ChartLegend
                className="mt-3"
                items={[
                  { name: "Sleep score", color: "var(--c-accent)" },
                ]}
              />
            </ChartFrame>
          ) : (
            <div className="text-[14px] text-ink2">
              Need at least 2 nights of scored sleep to draw the trend.
            </div>
          )}
        </Section>
      </Card>

      {/* ====== Nights list (principle 9: rows, not cards) ====== */}
      <Card pad={false}>
        <div className="px-7 pt-7 pb-3">
          <div className="text-[14px] font-medium text-ink2">Nights</div>
        </div>
        <div className="px-7">
          {visibleItems.map((it) => (
            <NightRow
              key={it.local_date}
              item={it}
              onOpen={() => {
                ui.selectSleepDate(it.local_date);
                ui.setView("sleep-night");
              }}
            />
          ))}
        </div>
        {shown < items.length && (
          <div className="flex items-center justify-center px-7 pb-7 pt-4">
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={loadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading…" : `Load more (${items.length - shown} left)`}
            </ApexButton>
          </div>
        )}
      </Card>
    </div>
  );
}

/* --------------------------------------------------------------- Summary stat
 * A bordered-tile-free stat: 14px sentence-case label, a 28px text-ink
 * number (BigStat size md), and a StatusDot underneath. No borders. */
function SummaryStat({
  label,
  value,
  status,
  foot,
}: {
  label: string;
  value: string;
  status: React.ReactNode;
  foot?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[14px] font-medium text-ink2">{label}</div>
      <BigStat value={value} size="md" />
      <div>{status}</div>
      {foot && <div className="num text-[12px] text-ink3">{foot}</div>}
    </div>
  );
}

/* --------------------------------------------------------------- Night row
 * A flat row: date · bed→wake · duration · score (with StatusDot) · stage
 * mini-bar. No borders — principle 3 + 9. */
function NightRow({
  item,
  onOpen,
}: {
  item: SessionItem;
  onOpen: () => void;
}) {
  const ui = useApexUi();
  const asleepS = timeAsleepS(item);
  const scoreT = scoreTone(item.sleep_score);
  const dotTone = scoreT === "positive" ? "ok" : scoreT === "warning" ? "watch" : scoreT === "alert" ? "alert" : "neutral";
  const word = scoreT === "positive" ? "Good" : scoreT === "warning" ? "Fair" : scoreT === "alert" ? "Low" : "—";

  const stages: { key: StageKey; secs: number; color: string }[] = [
    { key: "deep", secs: item.deep_s ?? 0, color: STAGE_VARS.deep },
    { key: "light", secs: item.light_s ?? 0, color: STAGE_VARS.light },
    { key: "rem", secs: item.rem_s ?? 0, color: STAGE_VARS.rem },
  ];

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-4 py-3 text-left transition-colors hover:bg-surface2 -mx-2 px-2 rounded-[var(--radius-control)]"
    >
      {/* Date */}
      <div className="w-[120px] shrink-0">
        <div className="num text-[14px] font-semibold text-ink">
          {fmtDateLong(item.local_date, ui.locale)}
        </div>
        <div className="num text-[12px] text-ink3">
          {fmtClock(item.start_time, ui.locale)} → {fmtClock(item.end_time, ui.locale)}
        </div>
      </div>

      {/* Duration */}
      <div className="w-[80px] shrink-0">
        <div className="num text-[20px] font-semibold text-ink">
          {fmtHours(item.total_sleep_s)}
        </div>
      </div>

      {/* Score (white number + StatusDot) */}
      <div className="flex shrink-0 items-center gap-2">
        <span className="num text-[20px] font-semibold text-ink">
          {fmtNum(item.sleep_score, 0)}
        </span>
        <StatusDot tone={dotTone} label={word} />
      </div>

      {/* Stage mini-bar */}
      <div className="ml-auto hidden min-w-0 flex-1 sm:block">
        <StageStackBar stages={stages} total={asleepS} />
      </div>
    </button>
  );
}

/** Horizontal stacked stage bar (deep / light / rem) using time asleep as
 *  the denominator. */
function StageStackBar({
  stages,
  total,
}: {
  stages: { key: StageKey; secs: number; color: string }[];
  total: number;
}) {
  if (total <= 0) {
    return <div className="h-2 w-full rounded-full bg-surface3" aria-hidden />;
  }
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface3">
      {stages.map((s) => {
        const pct = (s.secs / total) * 100;
        if (pct <= 0) return null;
        return (
          <div
            key={s.key}
            style={{ width: `${pct}%`, background: s.color }}
            title={`${s.key}: ${fmtHours(s.secs)}`}
          />
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------- tone helpers */
function durationTone(dur: number | null, targetS: number): "neutral" | "ok" | "watch" | "alert" {
  if (dur === null || !Number.isFinite(dur)) return "neutral";
  const ratio = dur / targetS;
  if (ratio >= 0.9) return "ok";
  if (ratio >= 0.7) return "watch";
  return "alert";
}

function durationWord(dur: number | null, targetS: number): string {
  if (dur === null || !Number.isFinite(dur)) return "—";
  const ratio = dur / targetS;
  if (ratio >= 0.9) return "On target";
  if (ratio >= 0.7) return "Slightly short";
  return "Short";
}

function scoreToDot(t: DataTone): "neutral" | "ok" | "watch" | "alert" {
  return t === "positive" ? "ok" : t === "warning" ? "watch" : t === "alert" ? "alert" : "neutral";
}

function scoreWord(t: DataTone): string {
  return t === "positive" ? "Good" : t === "warning" ? "Fair" : t === "alert" ? "Low" : "—";
}

function combinedSD(summary: SleepSummaryResponse | null): number | null {
  const bed = summary?.regularity_bed_sd_min ?? null;
  const wake = summary?.regularity_wake_sd_min ?? null;
  if (bed !== null && wake !== null) return Math.sqrt(bed ** 2 + wake ** 2);
  return bed ?? wake ?? null;
}

function regularityTone(sd: number | null): "neutral" | "ok" | "watch" | "alert" {
  if (sd === null) return "neutral";
  if (sd <= 20) return "ok";
  if (sd <= 45) return "watch";
  return "alert";
}

function regularityWord(sd: number | null): string {
  if (sd === null) return "—";
  if (sd <= 20) return "Consistent";
  if (sd <= 45) return "Variable";
  return "Irregular";
}

function debtTone(debtS: number): "neutral" | "ok" | "watch" | "alert" {
  if (debtS <= 0) return "ok";
  if (debtS <= 2 * 3600) return "watch";
  return "alert";
}

function debtWord(debtS: number): string {
  if (debtS <= 0) return "On track";
  if (debtS <= 2 * 3600) return "Slight";
  return "Owed";
}

function formatDebtHours(debtS: number): string {
  const h = debtS / 3600;
  if (h === 0) return "0h";
  return h > 0 ? `+${fmtNum(h, 1)}h` : `${fmtNum(h, 1)}h`;
}
