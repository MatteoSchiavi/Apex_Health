"use client";

/**
 * Apex Health — Sleep list (strict redesign per plan §4).
 *
 * Layout:
 *   Header: title + range Segmented (7 / 30 / 90 days)
 *   Row 1, Summary (col-12): four stats for the range —
 *     - avg duration with a DeltaChip against the sleep target (default 8h)
 *     - avg sleep score (scoreTone)
 *     - regularity: circular SD of bedtime + wake (minutes), with the two
 *       SDs broken out in the subtitle
 *     - sleep debt: cumulative shortfall vs target over the last 7 nights
 *   Row 2, Duration & timing (col-12 xl:col-8 + col-12 xl:col-4)
 *     - Left: nightly duration bars + target line (8h) + sleep-score line
 *       on a second axis. Toggle switches bars to stacked stage
 *       composition (deep / light / REM).
 *     - Right: timing card — bedtime → wake time per night as floating-bar
 *       (range) chart over the date axis, with median bedtime, median wake
 *       and spread in the header. Hidden under 5 nights.
 *   Row 3, Nights (col-12): compact TABLE — date, bed → wake, duration,
 *     score, stage bar, resting HR and HRV deviation per night.
 *     "Load more" button below.
 *
 * All numbers are server-computed (or shipped as part of the response):
 *   - /api/sleep?days=N           → items (each with resting_hr + hrv_deviation_ms)
 *                                  + baseline block (30-day stats)
 *   - /api/sleep/summary?days=N   → averages, regularity SDs, median bed/wake,
 *                                  sleep debt, target_s
 *
 * Coherence law: every visual element is composed from the shared kit
 * (Card, BigStat, DeltaChip, Segmented, Badge, Eyebrow, Empty, Loading,
 * ApexButton, Hairline, InfoButton, MetricInfoContent). Data tone comes
 * from scoreTone() / rangeTone() / hrvDevTone() / toneFor() — never bg-primary
 * on a data value or graph.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  DeltaChip,
  Badge,
  Eyebrow,
  Empty,
  Loading,
  Segmented,
  ApexButton,
  scoreTone,
  hrvDevTone,
  toneFor,
  type DataTone,
} from "@/components/apex/kit";
import { fmtHours, fmtNum, fmtClock, fmtDateLong } from "@/lib/apex/format";
import {
  STAGE_VARS,
  DEFAULT_SLEEP_TARGET_S,
  minutesOfDayUTC,
  timeAsleepS,
  sleepWindowS,
  fmtMinutes,
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
  const t = useT();
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
    // No additional fetch — the list is already fully loaded for the
    // window. "Load more" just expands the rendered slice. This keeps
    // the table compact while preserving every night in the window.
    setTimeout(() => {
      setShown((s) => Math.min(items.length, s + PAGE_SIZE));
      setLoadingMore(false);
    }, 80);
  }, [items.length]);

  // ─────────────────────────────────────────────────────────────── derived
  // Items are most-recent-first from the API; the chart wants oldest →
  // newest (left → right) so reverse a copy.
  const chartItems = useMemo(
    () => [...items].reverse(),
    [items],
  );

  const visibleItems = useMemo(
    () => items.slice(0, shown),
    [items, shown],
  );

  // ─────────────────────────────────────────────────────────────────── render
  if (loading && !items.length) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <HeaderShell range={range} setRange={setRange} />
        <div className="mt-6">
          <Loading label="Loading sleep…" />
        </div>
      </div>
    );
  }

  if (error && !items.length) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <HeaderShell range={range} setRange={setRange} />
        <div className="mt-6">
          <Empty title={error} body="Try reloading the page." />
        </div>
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <HeaderShell range={range} setRange={setRange} />
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
    <div className="mx-auto max-w-[1240px]">
      <HeaderShell range={range} setRange={setRange} />

      {/* ───────────────────────────────────────── Row 1 — Summary stats */}
      <div className="mt-6">
        <SummaryRow
          summary={summary}
          baseline={baseline}
        />
      </div>

      {/* ───────────────────────────────── Row 2 — Duration + Timing */}
      <div className="mt-3 grid grid-cols-12 gap-3">
        <div className="col-span-12 xl:col-span-8">
          <DurationScoreCard
            items={chartItems}
            baseline={baseline}
          />
        </div>
        <div className="col-span-12 xl:col-span-4">
          {chartItems.length >= 5 ? (
            <TimingCard items={chartItems} summary={summary} />
          ) : (
            <Card className="h-full">
              <CardHeader eyebrow={"Timing"} title={"Bedtime & wake"} />
              <Empty
                title={"Fewer than 5 nights"}
                body={"Timing regularity needs at least 5 nights of data to render."}
              />
            </Card>
          )}
        </div>
      </div>

      {/* ─────────────────────────────────────── Row 3 — Nights table */}
      <div className="mt-3">
        <NightsTable
          items={visibleItems}
          baseline={baseline}
          onOpen={(date) => {
            ui.selectSleepDate(date);
            ui.setView("sleep-night");
          }}
        />
        {shown < items.length && (
          <div className="mt-3 flex items-center justify-center">
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
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- Header shell */
function HeaderShell({
  range,
  setRange,
}: {
  range: RangeKey;
  setRange: (r: RangeKey) => void;
}) {
  const t = useT();
  return (
    <PageHeader
      title={t("sleep.title")}
      subtitle={"Am I sleeping enough, and regularly?" /* TODO i18n */}
      actions={
        <Segmented<RangeKey>
          value={range}
          onChange={setRange}
          options={[
            { value: "7d", label: "7d" },
            { value: "30d", label: "30d" },
            { value: "90d", label: "90d" },
          ]}
        />
      }
    />
  );
}

/* --------------------------------------------------------------- Row 1: Summary */
function SummaryRow({
  summary,
  baseline,
}: {
  summary: SleepSummaryResponse | null;
  baseline: BaselineBlock | null;
}) {
  const t = useT();
  const targetS = summary?.target_s ?? DEFAULT_SLEEP_TARGET_S;

  const avgDur = summary?.avg_duration_s ?? null;
  const avgScore = summary?.avg_score ?? null;
  const bedSD = summary?.regularity_bed_sd_min ?? null;
  const wakeSD = summary?.regularity_wake_sd_min ?? null;

  // Sleep debt: positive = owe sleep. Display with tone based on sign/magnitude.
  const debtS = summary?.sleep_debt_s ?? 0;
  const debtH = debtS / 3600;
  const debtTone: DataTone =
    debtS <= 0
      ? "positive"
      : debtS <= 2 * 3600
      ? "warning"
      : "alert";

  // Avg-duration delta vs target (goodWhen="up").
  const durDeltaMin =
    avgDur !== null ? Math.round((avgDur - targetS) / 60) : null;

  // Combined regularity headline — plan §4 says "spread of bedtime and
  // wake time (standard deviation in minutes)". Headline = the larger SD,
  // subtitle breaks both out.
  const combinedSD =
    bedSD !== null && wakeSD !== null
      ? Math.sqrt(bedSD ** 2 + wakeSD ** 2)
      : bedSD ?? wakeSD ?? null;

  return (
    <Card pad={false} className="px-5 py-4">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {/* Avg duration */}
        <SummaryStat
          eyebrow={t("sleep.avg_total")}
          value={
            <BigStat
              value={fmtHours(avgDur)}
              size="lg"
              tone={toneFor(rangeToneForDuration(avgDur, targetS))}
            />
          }
          chip={
            <DeltaChip
              delta={durDeltaMin}
              unit="min"
              goodWhen="up"
              suffix={"vs target"}
            />
          }
          foot={`Target ${fmtHours(targetS)}`}
        />

        {/* Avg score */}
        <SummaryStat
          eyebrow={t("sleep.avg_score")}
          value={
            <BigStat
              value={fmtNum(avgScore, 0)}
              unit="/100"
              size="lg"
              tone={toneFor(scoreTone(avgScore))}
            />
          }
          chip={null}
          foot={
            baseline && baseline.sleep_scores.count
              ? `${baseline.sleep_scores.count} nights scored`
              : "No scored nights"
          }
        />

        {/* Regularity */}
        <SummaryStat
          eyebrow={"Regularity" /* TODO i18n */}
          value={
            <BigStat
              value={fmtNum(combinedSD, 0)}
              unit="min"
              size="lg"
              tone={toneFor(combinedSD === null ? "muted" : combinedSD <= 20 ? "positive" : combinedSD <= 45 ? "warning" : "alert")}
            />
          }
          chip={null}
          foot={
            <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-0.5">
              <span>
                <span className="text-faint">Bed</span>{" "}
                <span className="num font-semibold text-ink2">
                  ±{fmtNum(bedSD, 0)}m
                </span>
              </span>
              <span>
                <span className="text-faint">Wake</span>{" "}
                <span className="num font-semibold text-ink2">
                  ±{fmtNum(wakeSD, 0)}m
                </span>
              </span>
            </span>
          }
        />

        {/* Sleep debt */}
        <SummaryStat
          eyebrow={"Sleep debt" /* TODO i18n */}
          value={
            <BigStat
              value={debtH > 0 ? `+${fmtNum(debtH, 1)}h` : fmtNum(debtH, 1) + "h"}
              size="lg"
              tone={toneFor(debtTone)}
            />
          }
          chip={
            <Badge tone={debtS <= 0 ? "positive" : debtS <= 2 * 3600 ? "warning" : "alert"} dot>
              {debtS <= 0 ? "On track" : debtS <= 2 * 3600 ? "Slight" : "Owed"}
              {/* TODO i18n */}
            </Badge>
          }
          foot={`Last 7 nights vs ${fmtHours(targetS)}`}
        />
      </div>
    </Card>
  );
}

/** Tone for a sleep duration against the target (good/borderline/bad). */
function rangeToneForDuration(
  dur: number | null,
  targetS: number,
): DataTone {
  if (dur === null || !Number.isFinite(dur)) return "muted";
  // <70% of target = alert; 70–90% = warning; ≥90% = positive.
  const ratio = dur / targetS;
  if (ratio >= 0.9) return "positive";
  if (ratio >= 0.7) return "warning";
  return "alert";
}

function SummaryStat({
  eyebrow,
  value,
  chip,
  foot,
}: {
  eyebrow: React.ReactNode;
  value: React.ReactNode;
  chip: React.ReactNode;
  foot: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Eyebrow>{eyebrow}</Eyebrow>
      <div className="flex items-end gap-2">{value}</div>
      {chip && <div>{chip}</div>}
      <div className="num text-[11px] text-faint">{foot}</div>
    </div>
  );
}

/* ------------------------------------------------ Row 2 left: Duration & score */
function DurationScoreCard({
  items,
  baseline,
}: {
  items: SessionItem[];
  baseline: BaselineBlock | null;
}) {
  const t = useT();
  const [stacked, setStacked] = useState(false);
  const targetS = baseline?.target_s ?? DEFAULT_SLEEP_TARGET_S;

  // Chart geometry (SVG, viewBox-scaled).
  const W = 1000;
  const H = 280;
  const padLeft = 44;
  const padRight = 44;
  const padTop = 16;
  const padBottom = 28;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;

  // Y-left: hours (0 to 10h). Y-right: score (0–100).
  const yMaxHours = 10;
  const yMaxScore = 100;
  const xStep = items.length > 1 ? plotW / (items.length - 1) : 0;

  // Target line Y on the hours axis.
  const targetY =
    padTop + plotH - (Math.min(targetS / 3600, yMaxHours) / yMaxHours) * plotH;

  const hourToY = (h: number) =>
    padTop + plotH - (Math.min(h, yMaxHours) / yMaxHours) * plotH;
  const scoreToY = (s: number) => padTop + plotH - (s / yMaxScore) * plotH;

  // Score line path (skips nulls).
  const scorePath = items
    .map((it, i) => {
      if (it.sleep_score === null) return null;
      const x = padLeft + i * xStep;
      const y = scoreToY(it.sleep_score);
      return `${i === 0 || items[i - 1].sleep_score === null ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");

  // X-axis ticks: ~5 evenly-spaced dates.
  const xTickCount = Math.min(5, items.length);
  const xTicks = Array.from({ length: xTickCount }, (_, i) => {
    const idx = Math.round((i * (items.length - 1)) / (xTickCount - 1 || 1));
    return { idx, date: items[idx]?.local_date ?? "" };
  });

  return (
    <Card className="h-full">
      <CardHeader
        eyebrow={"Duration & score" /* TODO i18n */}
        title={"Nightly trend"}
        right={
          <Segmented<"duration" | "stages">
            value={stacked ? "stages" : "duration"}
            onChange={(v) => setStacked(v === "stages")}
            size="sm"
            options={[
              { value: "duration", label: "Duration" },
              { value: "stages", label: "Stages" },
            ]}
          />
        }
      />

      {/* Legend */}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-muted">
        {stacked ? (
          <>
            <LegendDot color={STAGE_VARS.deep} label={t("sleep.deep")} />
            <LegendDot color={STAGE_VARS.light} label={t("sleep.light")} />
            <LegendDot color={STAGE_VARS.rem} label={t("sleep.rem")} />
          </>
        ) : (
          <LegendDot color="var(--c-text-muted)" label={"Duration"} />
        )}
        <LegendDot color="var(--c-primary)" label={t("sleep.score")} />
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-0 w-4 border-t border-dashed"
            style={{ borderColor: "var(--c-text-faint)" }}
          />
          <span>Target {fmtHours(targetS)}</span>
        </span>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: 480 }}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Sleep duration and score"
        >
          {/* Y-left grid (hours) */}
          {[0, 2, 4, 6, 8, 10].map((h) => {
            const y = hourToY(h);
            return (
              <g key={h}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={padLeft + plotW}
                  y2={y}
                  stroke="var(--c-hairline)"
                  strokeWidth={1}
                />
                <text
                  x={padLeft - 6}
                  y={y + 3}
                  textAnchor="end"
                  style={{
                    fontSize: 10,
                    fill: "var(--c-text-faint)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {h}h
                </text>
              </g>
            );
          })}

          {/* Y-right axis (score) */}
          {[0, 50, 100].map((s) => {
            const y = scoreToY(s);
            return (
              <text
                key={s}
                x={padLeft + plotW + 6}
                y={y + 3}
                textAnchor="start"
                style={{
                  fontSize: 10,
                  fill: "var(--c-text-faint)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {s}
              </text>
            );
          })}

          {/* Target line (8h) */}
          <line
            x1={padLeft}
            y1={targetY}
            x2={padLeft + plotW}
            y2={targetY}
            stroke="var(--c-text-faint)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />

          {/* Bars (duration or stacked) */}
          {items.map((it, i) => {
            const x = padLeft + i * xStep;
            const barW = Math.max(2, Math.min(14, xStep * 0.6));
            if (stacked) {
              const deepS = it.deep_s ?? 0;
              const lightS = it.light_s ?? 0;
              const remS = it.rem_s ?? 0;
              const totalAsleepH = (deepS + lightS + remS) / 3600;
              if (totalAsleepH <= 0) return null;
              const baseY = padTop + plotH; // bottom of plot
              let accH = 0;
              const segs = [
                { secs: deepS, color: STAGE_VARS.deep },
                { secs: lightS, color: STAGE_VARS.light },
                { secs: remS, color: STAGE_VARS.rem },
              ];
              return segs.map((seg, j) => {
                const segH = (seg.secs / 3600 / yMaxHours) * plotH;
                const y = baseY - segH - accH;
                accH += segH;
                return (
                  <rect
                    key={`${i}-${j}`}
                    x={x - barW / 2}
                    y={y}
                    width={barW}
                    height={segH}
                    fill={seg.color}
                  />
                );
              });
            }
            const durH = (it.total_sleep_s ?? 0) / 3600;
            if (durH <= 0) return null;
            const tone = scoreTone(it.sleep_score);
            const barColor = toneToVar(tone);
            const h = (durH / yMaxHours) * plotH;
            return (
              <rect
                key={i}
                x={x - barW / 2}
                y={padTop + plotH - h}
                width={barW}
                height={h}
                fill={barColor}
                opacity={0.85}
              />
            );
          })}

          {/* Score line */}
          {scorePath && (
            <path
              d={scorePath}
              fill="none"
              stroke="var(--c-primary)"
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}
          {/* Score dots */}
          {items.map((it, i) => {
            if (it.sleep_score === null) return null;
            const x = padLeft + i * xStep;
            const y = scoreToY(it.sleep_score);
            return (
              <circle
                key={`dot-${i}`}
                cx={x}
                cy={y}
                r={2.2}
                fill="var(--c-primary)"
              />
            );
          })}

          {/* X-axis baseline */}
          <line
            x1={padLeft}
            y1={padTop + plotH}
            x2={padLeft + plotW}
            y2={padTop + plotH}
            stroke="var(--c-hairline-strong)"
            strokeWidth={1}
          />

          {/* X-axis date ticks */}
          {xTicks.map(({ idx, date }, i) => {
            const x = padLeft + idx * xStep;
            return (
              <text
                key={i}
                x={x}
                y={padTop + plotH + 18}
                textAnchor="middle"
                style={{
                  fontSize: 10,
                  fill: "var(--c-text-muted)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {shortDate(date)}
              </text>
            );
          })}
        </svg>
      </div>
    </Card>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color }}
      />
      <span>{label}</span>
    </span>
  );
}

/** Map a DataTone to a CSS color variable. */
function toneToVar(tone: DataTone): string {
  return {
    positive: "var(--c-positive)",
    warning: "var(--c-warning)",
    alert: "var(--c-alert)",
    muted: "var(--c-hairline2)",
  }[tone];
}

/* ------------------------------------------------- Row 2 right: Timing card */
function TimingCard({
  items,
  summary,
}: {
  items: SessionItem[];
  summary: SleepSummaryResponse | null;
}) {
  // Y-axis: time-of-day from 18:00 (top) to 09:00 next day (bottom).
  // Each night's bar starts at bedtime_offset_from_18 and ends at
  // wake_offset_from_18 (modulo 24h) so bars never wrap.
  const bedOffsets = items.map((it) => {
    const m = minutesOfDayUTC(it.start_time);
    if (!Number.isFinite(m)) return NaN;
    return ((m - 18 * 60 + 1440) % 1440);
  });
  const wakeOffsets = items.map((it) => {
    const m = minutesOfDayUTC(it.end_time);
    if (!Number.isFinite(m)) return NaN;
    return ((m - 18 * 60 + 1440) % 1440);
  });

  // Window = 15 hours (18:00 → 09:00). If a wake offset is smaller than a
  // bed offset (which can happen when wake is before 18:00 — unusual but
  // possible), add 1440 so the bar still renders continuously.
  const WINDOW_MIN = 15 * 60;

  const medianBed = summary?.median_bedtime ?? null;
  const medianWake = summary?.median_wake ?? null;
  const bedSD = summary?.regularity_bed_sd_min ?? null;
  const wakeSD = summary?.regularity_wake_sd_min ?? null;

  // Chart geometry
  const W = 1000;
  const H = 280;
  const padLeft = 44;
  const padRight = 16;
  const padTop = 16;
  const padBottom = 28;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;
  const xStep = items.length > 1 ? plotW / (items.length - 1) : 0;

  const minToY = (off: number) =>
    padTop + (off / WINDOW_MIN) * plotH;

  // Y-axis ticks every 3h from 18:00 → 09:00.
  const yTicks = Array.from({ length: 6 }, (_, i) => {
    const off = (i * 3 * 60) % (24 * 60);
    const h24 = (18 + i * 3) % 24;
    const label = `${String(h24).padStart(2, "0")}:00`;
    return { off, label };
  });

  // Median lines (mapped through the same 18:00 offset).
  const medianBedOff =
    medianBed !== null
      ? ((medianBed - 18 * 60 + 1440) % 1440)
      : null;
  const medianWakeOff =
    medianWake !== null
      ? ((medianWake - 18 * 60 + 1440) % 1440)
      : null;

  // X-axis date ticks.
  const xTickCount = Math.min(5, items.length);
  const xTicks = Array.from({ length: xTickCount }, (_, i) => {
    const idx = Math.round((i * (items.length - 1)) / (xTickCount - 1 || 1));
    return { idx, date: items[idx]?.local_date ?? "" };
  });

  return (
    <Card className="h-full">
      <CardHeader
        eyebrow={"Timing" /* TODO i18n */}
        title={"Bedtime & wake"}
        right={
          <div className="text-right">
            <div className="num text-[11px] text-muted">
              Bed {medianBed !== null ? fmtMinutes(medianBed) : "—"}{" "}
              <span className="text-faint">±{fmtNum(bedSD, 0)}m</span>
            </div>
            <div className="num text-[11px] text-muted">
              Wake {medianWake !== null ? fmtMinutes(medianWake) : "—"}{" "}
              <span className="text-faint">±{fmtNum(wakeSD, 0)}m</span>
            </div>
          </div>
        }
      />

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: 320 }}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Bedtime and wake per night"
        >
          {/* Y-axis grid + labels */}
          {yTicks.map((tk, i) => {
            const y = minToY(tk.off);
            return (
              <g key={i}>
                <line
                  x1={padLeft}
                  y1={y}
                  x2={padLeft + plotW}
                  y2={y}
                  stroke="var(--c-hairline)"
                  strokeWidth={1}
                />
                <text
                  x={padLeft - 6}
                  y={y + 3}
                  textAnchor="end"
                  style={{
                    fontSize: 10,
                    fill: "var(--c-text-faint)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {tk.label}
                </text>
              </g>
            );
          })}

          {/* Median bedtime line */}
          {medianBedOff !== null && (
            <line
              x1={padLeft}
              y1={minToY(medianBedOff)}
              x2={padLeft + plotW}
              y2={minToY(medianBedOff)}
              stroke="var(--c-text-faint)"
              strokeWidth={1.2}
              strokeDasharray="3 3"
            />
          )}
          {/* Median wake line */}
          {medianWakeOff !== null && (
            <line
              x1={padLeft}
              y1={minToY(medianWakeOff)}
              x2={padLeft + plotW}
              y2={minToY(medianWakeOff)}
              stroke="var(--c-text-faint)"
              strokeWidth={1.2}
              strokeDasharray="3 3"
            />
          )}

          {/* Floating bars: bedtime → wake */}
          {items.map((it, i) => {
            const x = padLeft + i * xStep;
            const barW = Math.max(3, Math.min(12, xStep * 0.55));
            const bOff = bedOffsets[i];
            const wOff = wakeOffsets[i];
            if (!Number.isFinite(bOff) || !Number.isFinite(wOff)) return null;
            // Handle the rare case where wake is "before" bedtime on the
            // 18:00-relative axis — push it +24h so the bar is continuous.
            let top = bOff;
            let bot = wOff;
            if (bot < top) bot += 1440;
            // Clamp to window for safety.
            top = Math.min(top, WINDOW_MIN - 1);
            bot = Math.min(bot, WINDOW_MIN);
            const yTop = minToY(top);
            const yBot = minToY(bot);
            const tone = scoreTone(it.sleep_score);
            return (
              <rect
                key={i}
                x={x - barW / 2}
                y={yTop}
                width={barW}
                height={Math.max(1, yBot - yTop)}
                fill={toneToVar(tone)}
                opacity={0.85}
              />
            );
          })}

          {/* X-axis baseline */}
          <line
            x1={padLeft}
            y1={padTop + plotH}
            x2={padLeft + plotW}
            y2={padTop + plotH}
            stroke="var(--c-hairline-strong)"
            strokeWidth={1}
          />

          {/* X-axis date ticks */}
          {xTicks.map(({ idx, date }, i) => {
            const x = padLeft + idx * xStep;
            return (
              <text
                key={i}
                x={x}
                y={padTop + plotH + 18}
                textAnchor="middle"
                style={{
                  fontSize: 10,
                  fill: "var(--c-text-muted)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {shortDate(date)}
              </text>
            );
          })}
        </svg>
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------- Row 3: Table */
function NightsTable({
  items,
  baseline,
  onOpen,
}: {
  items: SessionItem[];
  baseline: BaselineBlock | null;
  onOpen: (date: string) => void;
}) {
  const t = useT();
  // 30-day HRV sd (for hrvDevTone).
  const hrvSd = baseline?.vitals.hrv_ms.sd ?? null;

  return (
    <Card pad={false} className="overflow-hidden">
      {/* Header row */}
      <div className="hidden grid-cols-12 gap-3 border-b border-hairline bg-surface2/40 px-4 py-2 md:grid">
        <Eyebrow className="col-span-2">{"Date" /* TODO i18n */}</Eyebrow>
        <Eyebrow className="col-span-2">{"Bed → Wake" /* TODO i18n */}</Eyebrow>
        <Eyebrow className="col-span-2">{t("sleep.total")}</Eyebrow>
        <Eyebrow className="col-span-1">{t("sleep.score")}</Eyebrow>
        <Eyebrow className="col-span-3">{"Stages" /* TODO i18n */}</Eyebrow>
        <Eyebrow className="col-span-1">{t("sleep.resting_hr")}</Eyebrow>
        <Eyebrow className="col-span-1">{"HRV Δ" /* TODO i18n */}</Eyebrow>
      </div>
      <div className="divide-y divide-hairline">
        {items.map((it) => (
          <NightRow
            key={it.local_date}
            item={it}
            hrvSd={hrvSd}
            onOpen={() => onOpen(it.local_date)}
          />
        ))}
      </div>
    </Card>
  );
}

function NightRow({
  item,
  hrvSd,
  onOpen,
}: {
  item: SessionItem;
  hrvSd: number | null;
  onOpen: () => void;
}) {
  const t = useT();
  const ui = useApexUi();

  const stages: { key: StageKey; secs: number; color: string }[] = [
    { key: "deep", secs: item.deep_s ?? 0, color: STAGE_VARS.deep },
    { key: "light", secs: item.light_s ?? 0, color: STAGE_VARS.light },
    { key: "rem", secs: item.rem_s ?? 0, color: STAGE_VARS.rem },
  ];
  const asleepS = timeAsleepS(item);

  // HRV deviation tone
  const hrvTone = hrvDevTone(item.hrv_deviation_ms, hrvSd);
  const hrvToneCls = toneTextClass(hrvTone);

  // Resting HR — show as a flat value; tone via scoreTone isn't appropriate
  // for HR. Leave as ink.

  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full grid-cols-1 items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface2/40 md:grid-cols-12"
    >
      {/* Date */}
      <div className="col-span-2">
        <div className="num text-[12.5px] font-semibold text-ink">
          {fmtDateLong(item.local_date, ui.locale)}
        </div>
      </div>

      {/* Bed → Wake */}
      <div className="col-span-2 num mono text-[12px] text-muted">
        {fmtClock(item.start_time, ui.locale)} → {fmtClock(item.end_time, ui.locale)}
      </div>

      {/* Total sleep */}
      <div className="col-span-2">
        <div className="num text-[14px] font-semibold text-ink">
          {fmtHours(item.total_sleep_s)}
        </div>
        <div className="num text-[10px] text-faint">
          window {fmtHours(sleepWindowS(item))}
        </div>
      </div>

      {/* Sleep score */}
      <div className="col-span-1">
        <div
          className={`num text-[16px] font-bold ${toneTextClass(scoreTone(item.sleep_score))}`}
        >
          {fmtNum(item.sleep_score, 0)}
        </div>
      </div>

      {/* Stage bar */}
      <div className="col-span-3">
        <StageStackBar
          stages={stages}
          total={asleepS}
        />
        <div className="num mt-1 flex items-center gap-2 text-[10px] text-faint">
          <span>
            <span style={{ color: STAGE_VARS.deep }}>●</span> {fmtHours(item.deep_s)}
          </span>
          <span>
            <span style={{ color: STAGE_VARS.light }}>●</span> {fmtHours(item.light_s)}
          </span>
          <span>
            <span style={{ color: STAGE_VARS.rem }}>●</span> {fmtHours(item.rem_s)}
          </span>
        </div>
      </div>

      {/* Resting HR */}
      <div className="col-span-1 num text-[13px] font-semibold text-ink2">
        {item.resting_hr !== null ? `${item.resting_hr}` : "—"}
        {item.resting_hr !== null && (
          <span className="ml-0.5 text-[10px] font-medium text-faint">bpm</span>
        )}
      </div>

      {/* HRV deviation */}
      <div className={`col-span-1 num text-[13px] font-semibold ${hrvToneCls}`}>
        {item.hrv_deviation_ms !== null
          ? `${item.hrv_deviation_ms >= 0 ? "+" : "−"}${fmtNum(Math.abs(item.hrv_deviation_ms), 0)}`
          : "—"}
        {item.hrv_deviation_ms !== null && (
          <span className="ml-0.5 text-[10px] font-medium text-faint">ms</span>
        )}
      </div>
    </button>
  );
}

/** Horizontal stacked stage bar (deep / light / rem) using time asleep as
 *  the denominator. Plan §4 fixes the unit bug — denominator is
 *  consistently seconds / time asleep. */
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
            title={`${t_label(s.key)}: ${fmtHours(s.secs)} (${Math.round(pct)}% of time asleep)`}
          />
        );
      })}
    </div>
  );
}

function t_label(k: StageKey): string {
  // The label is only used in the title tooltip — the visible label uses
  // t("sleep.*") in the parent. Keeping a single English fallback here
  // avoids prop-drilling t() into the bar component.
  const en: Record<StageKey, string> = {
    deep: "Deep",
    light: "Light",
    rem: "REM",
    awake: "Awake",
  };
  return en[k];
}

/** Convert a DataTone to a tailwind text color class. */
function toneTextClass(tone: DataTone): string {
  return {
    positive: "text-positiveText",
    warning: "text-warningText",
    alert: "text-alertText",
    muted: "text-muted",
  }[tone];
}
