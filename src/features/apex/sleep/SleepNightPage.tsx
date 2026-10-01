"use client";

/**
 * Apex Health — Sleep night (re-skin per ui-language/RULES.md).
 *
 * Reference: OverviewPage.tsx — one hero, status dots, rows not cards,
 * sentence-case labels, no borders.
 *
 * Layout:
 *   - BackLink + date title + a page sentence ("You slept 7h29 — 31 min
 *     under your target.") + prev/next arrows.
 *   - ONE hero: the sleep score as a ring (like the Overview) + a
 *     StatusDot below.
 *   - Duration analysis: 4 compact stats (no bordered tiles, no duplicate
 *     composition bar).
 *   - Stages: estimated hypnogram + ONE composition bar + table.
 *   - Vitals: `Row` primitives, not bordered tiles.
 *   - HRV: InteractiveLineChart with baseline band.
 *   - In context: previous 7 nights + today's readiness/recovery.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ArrowRight } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import {
  Card,
  Section,
  StatusDot,
  PageSentence,
  ChartFrame,
  BigStat,
  BackLink,
  RangeBar,
  InfoButton,
  MetricInfoContent,
  ApexButton,
  Hairline,
  scoreTone,
  rangeTone,
  hrvDevTone,
  toneFor,
  type DataTone,
} from "@/components/apex/kit";
import { InteractiveLineChart, ChartInfoBadge } from "@/components/apex/charts";
import { getMetricExplanation } from "@/lib/apex/metricInfo";
import { fmtHours, fmtNum, fmtClock, fmtDateLong } from "@/lib/apex/format";
import {
  STAGE_VARS,
  TYPICAL_STAGE_RANGE,
  DEFAULT_SLEEP_TARGET_S,
  minutesOfDayUTC,
  timeAsleepS,
  sleepWindowS,
  sleepEfficiencyPct,
  fmtMinutes,
  type StageKey,
} from "@/lib/apex/sleepHelpers";

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

interface HrvReadingOut {
  timestamp: string;
  hrv_ms: number;
  rolling_baseline_ms: number | null;
}

interface BiometricsOut {
  date: string;
  resting_hr: number | null;
  hrv_ms: number | null;
  spo2_avg: number | null;
  respiration_avg: number | null;
  skin_temp_c: number | null;
}

interface NightDetailResponse {
  ok: boolean;
  error?: string;
  session: SessionItem | null;
  biometrics: BiometricsOut | null;
  hrv_readings: HrvReadingOut[];
  baseline: BaselineBlock;
}

interface ListResponse {
  ok: boolean;
  error?: string;
  items: SessionItem[];
  all_dates: string[];
}

interface DashboardResponse {
  ok: boolean;
  error?: string;
  overview?: {
    date: string;
    readiness?: { value: number | null; delta_7d: number | null };
    recovery?: { value: number | null; delta_7d: number | null };
  };
}

const LIST_DAYS_FOR_NAV = 365;

export function SleepNightPage() {
  const ui = useApexUi();
  const sessionDate = ui.selectedSleepDate;

  const [detail, setDetail] = useState<NightDetailResponse | null>(null);
  const [list, setList] = useState<ListResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listReq, dashReq] = await Promise.all([
        fetch(`/api/sleep?days=${LIST_DAYS_FOR_NAV}`),
        fetch("/api/dashboard").then((r) => r.json() as Promise<DashboardResponse>).catch(() => null),
      ]);
      const listJson: ListResponse = await listReq.json();
      if (!listJson.ok) throw new Error(listJson.error || "Failed to load sleep list");

      const initialDate = sessionDate ?? listJson.items[0]?.local_date ?? null;
      if (!initialDate) {
        setList(listJson);
        setLoading(false);
        return;
      }
      if (!sessionDate) ui.selectSleepDate(initialDate);

      const detailReq = await fetch(`/api/sleep?date=${encodeURIComponent(initialDate)}`);
      const detailRes: NightDetailResponse = await detailReq.json();
      if (!detailRes.ok) throw new Error(detailRes.error || "Failed to load night");

      setList(listJson);
      setDetail(detailRes);
      if (dashReq) {
        const dash = await dashReq;
        if (dash && dash.ok) setDashboard(dash);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [sessionDate, ui]);

  useEffect(() => {
    fetchAll();
  }, [sessionDate, fetchAll]);

  // ──────────────────────────────────────────────────────────── prev / next
  const allDates = useMemo(() => list?.all_dates ?? [], [list]);
  const currentIndex = useMemo(
    () => (sessionDate ? allDates.indexOf(sessionDate) : -1),
    [allDates, sessionDate],
  );
  const prevDate = currentIndex > 0 ? allDates[currentIndex - 1] : null;
  const nextDate =
    currentIndex >= 0 && currentIndex < allDates.length - 1
      ? allDates[currentIndex + 1]
      : null;

  if (loading && !detail) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <BackLink onClick={() => ui.setView("sleep")}>Back to sleep</BackLink>
        <div className="mt-6 text-[14px] text-ink2">Loading night…</div>
      </div>
    );
  }

  if (error || !detail || !detail.session) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <BackLink onClick={() => ui.setView("sleep")}>Back to sleep</BackLink>
        <div className="mt-6 text-[14px] text-ink2">
          {error ?? "No sleep data for this date."}
        </div>
      </div>
    );
  }

  const session = detail.session;
  const bio = detail.biometrics;
  const hrvReadings = detail.hrv_readings;
  const baseline = detail.baseline;
  const targetS = baseline?.target_s ?? DEFAULT_SLEEP_TARGET_S;
  const score = session.sleep_score;
  const asleepS = session.total_sleep_s ?? timeAsleepS(session);
  const winS = sleepWindowS(session);
  const effPct = sleepEfficiencyPct(session);

  // Page sentence: duration vs target.
  const deltaVsTargetMin = Math.round((asleepS - targetS) / 60);
  const pageSentence = deltaVsTargetMin === 0
    ? `You slept ${fmtHours(asleepS)} — exactly on your target.`
    : deltaVsTargetMin > 0
    ? `You slept ${fmtHours(asleepS)} — ${Math.abs(deltaVsTargetMin)} min over your target.`
    : `You slept ${fmtHours(asleepS)} — ${Math.abs(deltaVsTargetMin)} min under your target.`;

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ====== Header ====== */}
      <div>
        <BackLink onClick={() => ui.setView("sleep")}>Back to sleep</BackLink>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="page-title">{fmtDateLong(session.local_date, ui.locale)}</h1>
            <PageSentence className="mt-2">{pageSentence}</PageSentence>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => prevDate && ui.selectSleepDate(prevDate)}
              disabled={!prevDate}
              aria-label="Previous night"
            >
              <ChevronLeft size={14} />
            </ApexButton>
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => nextDate && ui.selectSleepDate(nextDate)}
              disabled={!nextDate}
              aria-label="Next night"
            >
              <ChevronRight size={14} />
            </ApexButton>
          </div>
        </div>
      </div>

      {/* ====== Hero — the sleep score (principle 2: one hero) ====== */}
      <Card>
        <div className="flex flex-col gap-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-8">
            <ScoreRing value={score} tone={scoreTone(score)} />
            <div>
              <div className="text-[14px] font-medium text-ink2">Sleep score</div>
              <div className="mt-2">
                <StatusDot
                  tone={scoreToDot(scoreTone(score))}
                  label={scoreBandWord(score, baseline)}
                />
              </div>
              <div className="mt-2 text-[14px] text-ink2">
                {scoreTone(score) === "positive" && "A good night — your stages and duration are in your range."}
                {scoreTone(score) === "warning" && "A fair night — a bit short on the most restorative stages."}
                {scoreTone(score) === "alert" && "Below your norm — short or light on deep+REM."}
                {scoreTone(score) === "muted" && "Sync a source to see your sleep score."}
              </div>
            </div>
          </div>
          <div className="flex gap-6 sm:gap-8">
            <MiniFact label="Efficiency" value={`${fmtNum(effPct, 0)}%`} />
            <MiniFact label="Sleep window" value={fmtHours(winS)} />
          </div>
        </div>
      </Card>

      {/* ====== Duration analysis (4 compact stats, no borders) ====== */}
      <Card>
        <Section label="Duration analysis">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <DurationStat
              label="Total sleep"
              value={fmtHours(asleepS)}
              foot={`Target ${fmtHours(targetS)}`}
              status={
                <StatusDot
                  tone={durationTone(asleepS, targetS)}
                  label={durationWord(asleepS, targetS)}
                />
              }
            />
            <DurationStat
              label="Deep + REM"
              value={fmtHours((session.deep_s ?? 0) + (session.rem_s ?? 0))}
              foot={`${fmtNum(((session.deep_s ?? 0) + (session.rem_s ?? 0)) / (asleepS || 1) * 100, 0)}% of sleep`}
              status={<StatusDot tone="neutral" label="Restorative" />}
            />
            <DurationStat
              label="Awake"
              value={fmtHours(session.awake_s ?? 0)}
              foot={`${fmtNum((session.awake_s ?? 0) / (winS || 1) * 100, 0)}% of window`}
              status={
                <StatusDot
                  tone={(session.awake_s ?? 0) / (winS || 1) < 0.1 ? "ok" : (session.awake_s ?? 0) / (winS || 1) < 0.2 ? "watch" : "alert"}
                  label={(session.awake_s ?? 0) / (winS || 1) < 0.1 ? "Low" : (session.awake_s ?? 0) / (winS || 1) < 0.2 ? "Some" : "High"}
                />
              }
            />
            <DurationStat
              label="Bedtime"
              value={fmtClock(session.start_time, ui.locale)}
              foot={`Wake ${fmtClock(session.end_time, ui.locale)}`}
              status={<StatusDot tone="neutral" label={fmtMinutes(minutesOfDayUTC(session.start_time))} />}
            />
          </div>
        </Section>
      </Card>

      {/* ====== Stages — hypnogram + ONE composition bar + table ====== */}
      <Card>
        <Section label="Stages">
          {/* Hypnogram (estimated) */}
          <Hypnogram session={session} />

          <Hairline className="my-6" />

          {/* ONE horizontal stacked bar — deep / light / REM. Denominator =
              time asleep so the three stages sum to 100%. */}
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface3">
            {([
              { key: "deep", secs: session.deep_s ?? 0, color: STAGE_VARS.deep },
              { key: "light", secs: session.light_s ?? 0, color: STAGE_VARS.light },
              { key: "rem", secs: session.rem_s ?? 0, color: STAGE_VARS.rem },
            ] as const).map((s) => {
              const pct = asleepS > 0 ? (s.secs / asleepS) * 100 : 0;
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

          {/* Stage legend underneath the bar */}
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
            <StageLegendItem color={STAGE_VARS.deep} label="Deep" value={session.deep_s ?? 0} total={asleepS} />
            <StageLegendItem color={STAGE_VARS.light} label="Light" value={session.light_s ?? 0} total={asleepS} />
            <StageLegendItem color={STAGE_VARS.rem} label="REM" value={session.rem_s ?? 0} total={asleepS} />
            <StageLegendItem color={STAGE_VARS.awake} label="Awake" value={session.awake_s ?? 0} total={winS} />
          </div>

          {/* Composition table: stage, duration, % of sleep, 30-day average,
              typical range. */}
          <div className="mt-6 overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse">
              <thead>
                <tr className="border-b border-hairline text-left">
                  <th className="py-2 pr-3 text-[14px] font-medium text-ink2">Stage</th>
                  <th className="py-2 pr-3 text-[14px] font-medium text-ink2">Duration</th>
                  <th className="py-2 pr-3 text-[14px] font-medium text-ink2">% of sleep</th>
                  <th className="py-2 pr-3 text-[14px] font-medium text-ink2">30-day avg</th>
                  <th className="py-2 text-[14px] font-medium text-ink2">Typical range</th>
                </tr>
              </thead>
              <tbody>
                {([
                  { key: "deep", label: "Deep", secs: session.deep_s ?? 0, color: STAGE_VARS.deep },
                  { key: "light", label: "Light", secs: session.light_s ?? 0, color: STAGE_VARS.light },
                  { key: "rem", label: "REM", secs: session.rem_s ?? 0, color: STAGE_VARS.rem },
                  { key: "awake", label: "Awake", secs: session.awake_s ?? 0, color: STAGE_VARS.awake },
                ] as const).map((s) => {
                  const pctOfSleep = (s.secs / (asleepS || 1)) * 100;
                  const avgS = baseline?.stages[s.key]?.mean_s ?? null;
                  const avgPct = baseline?.stages[s.key]?.mean_pct ?? null;
                  const typical = TYPICAL_STAGE_RANGE[s.key];
                  return (
                    <tr key={s.key} className="border-b border-hairline last:border-0">
                      <td className="py-2 pr-3">
                        <span className="inline-flex items-center gap-2 text-[14px] font-medium text-ink">
                          <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
                          {s.label}
                        </span>
                      </td>
                      <td className="num py-2 pr-3 text-[14px] text-ink2">{fmtHours(s.secs)}</td>
                      <td className="num py-2 pr-3 text-[14px] text-ink2">{fmtNum(pctOfSleep, 0)}%</td>
                      <td className="num py-2 pr-3 text-[14px] text-ink3">
                        {avgS !== null ? `${fmtHours(avgS)} (${fmtNum(avgPct ?? 0, 0)}%)` : "—"}
                      </td>
                      <td className="num py-2 text-[14px] text-ink3">
                        {s.key === "awake" ? "—" : `${typical.low}–${typical.high}%`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      </Card>

      {/* ====== Vitals (rows, not bordered tiles) + HRV chart ====== */}
      <div className="grid grid-cols-1 gap-8 xl:grid-cols-2">
        <Card>
          <Section label="Vitals against baseline">
            <div className="divide-y divide-[var(--c-divider)]">
              <VitalRow
                k="resting_hr"
                label="Resting heart rate"
                value={bio?.resting_hr ?? null}
                unit="bpm"
                stats={baseline?.vitals.resting_hr ?? null}
              />
              <VitalRow
                k="spo2_avg"
                label="SpO₂"
                value={bio?.spo2_avg ?? session.spo2_avg ?? null}
                unit="%"
                stats={baseline?.vitals.spo2_avg ?? null}
              />
              <VitalRow
                k="respiration_avg"
                label="Respiration"
                value={bio?.respiration_avg ?? session.respiration_avg ?? null}
                unit="brpm"
                stats={baseline?.vitals.respiration_avg ?? null}
              />
              <VitalRow
                k="skin_temp"
                label="Skin temperature"
                value={bio?.skin_temp_c ?? null}
                unit="°C"
                stats={null}
              />
            </div>
          </Section>
        </Card>

        <Card>
          <Section label="HRV">
            <HrvBlock
              readings={hrvReadings}
              hrvMs={bio?.hrv_ms ?? null}
              hrvStats={baseline?.vitals.hrv_ms ?? null}
              listItems={list?.items ?? []}
              selectedDate={session.local_date}
            />
          </Section>
        </Card>
      </div>

      {/* ====== In context (last 7 nights + today) ====== */}
      <Card>
        <Section label="In context">
          <InContextBlock
            listItems={list?.items ?? []}
            selectedDate={session.local_date}
            dashboard={dashboard}
            onOverview={() => ui.setView("overview")}
          />
        </Section>
      </Card>
    </div>
  );
}

/* --------------------------------------------------------------- Score ring
 * The hero — a 120px ring with the score number inside, like the Overview's
 * readiness ring. Color = state. Number stays text-ink (RULES principle 5). */
function ScoreRing({
  value,
  tone,
}: {
  value: number | null;
  tone: "positive" | "warning" | "alert" | "muted";
}) {
  const v = value ?? 0;
  const r = 54;
  const c = 2 * Math.PI * r;
  const color =
    tone === "positive"
      ? "var(--c-ok)"
      : tone === "warning"
      ? "var(--c-watch)"
      : tone === "alert"
      ? "var(--c-alert)"
      : "var(--c-text-3)";
  return (
    <div className="relative h-[120px] w-[120px] shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--c-surface-2)" strokeWidth="8" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - v / 100)}
          style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-[40px] font-semibold leading-none text-ink">
          {value !== null ? Math.round(value) : "—"}
        </span>
        <span className="text-[12px] text-ink2">/ 100</span>
      </div>
    </div>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[14px] text-ink2">{label}</div>
      <div className="num mt-1 text-[20px] font-semibold text-ink">{value}</div>
    </div>
  );
}

function DurationStat({
  label,
  value,
  foot,
  status,
}: {
  label: string;
  value: string;
  foot?: string;
  status: React.ReactNode;
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

function StageLegendItem({
  color,
  label,
  value,
  total,
}: {
  color: string;
  label: string;
  value: number;
  total: number;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <span className="inline-flex items-center gap-1.5 text-ink2">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label} {fmtHours(value)} · {pct}%
    </span>
  );
}

/* --------------------------------------------------------------- Vitals row
 * A `Row` primitive with a RangeBar sparkline. No borders. */
function VitalRow({
  k,
  label,
  value,
  unit,
  stats,
}: {
  k: string;
  label: string;
  value: number | null;
  unit: string;
  stats: VitalStats | null;
}) {
  const expl = getMetricExplanation(k);
  const mean = stats?.mean ?? null;
  const low = stats?.low ?? null;
  const high = stats?.high ?? null;
  const tone = rangeTone(value, low, high);
  const dotTone =
    tone === "positive" ? "ok" : tone === "warning" ? "watch" : tone === "alert" ? "alert" : "neutral";
  const word = tone === "positive" ? "In range" : tone === "warning" ? "Borderline" : tone === "alert" ? "Out of range" : "—";
  const decimals = unit === "%" || unit === "°C" ? 1 : 0;

  return (
    <div className="py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <span className="text-[14px] font-medium text-ink2">{label}</span>
          <InfoButton title={label}>
            <MetricInfoContent
              whatItMeasures={expl.whatItMeasures}
              whyItMatters={expl.whyItMatters}
              whatInfluencesIt={expl.whatInfluencesIt}
              howToReadIt={expl.howToReadIt}
            />
          </InfoButton>
        </div>
        <div className="flex items-center gap-3">
          <StatusDot tone={dotTone} label={word} />
          <div className="num flex items-baseline gap-1 text-ink">
            <span className="text-[20px] font-semibold">
              {value !== null ? fmtNum(value, decimals) : "—"}
            </span>
            {value !== null && <span className="text-[13px] text-ink2">{unit}</span>}
          </div>
        </div>
      </div>
      {low !== null && high !== null && value !== null ? (
        <div className="mt-3">
          <RangeBar
            value={value}
            low={low}
            high={high}
            tone={toneFor(tone)}
            unit={unit}
            height={4}
          />
          <div className="num mt-1 flex items-center justify-between text-[12px] text-ink3">
            <span>Low {fmtNum(low, decimals)}</span>
            <span>30-day band</span>
            <span>High {fmtNum(high, decimals)}</span>
          </div>
        </div>
      ) : (
        <div className="num mt-2 text-[12px] text-ink3">
          {mean !== null ? `30-day mean ${fmtNum(mean, decimals)}` : "No 30-day baseline yet"}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- HRV block
 * Overnight HRV InteractiveLineChart with baseline band + 30-day
 * deviation trend below. */
function HrvBlock({
  readings,
  hrvMs,
  hrvStats,
  listItems,
  selectedDate,
}: {
  readings: HrvReadingOut[];
  hrvMs: number | null;
  hrvStats: VitalStats | null;
  listItems: SessionItem[];
  selectedDate: string;
}) {
  const hrvMean = hrvStats?.mean ?? null;
  const hrvSd = hrvStats?.sd ?? null;
  const hrvDev = hrvMs !== null && hrvMean !== null ? hrvMs - hrvMean : null;
  const hrvT = hrvDevTone(hrvDev, hrvSd);
  const dotTone =
    hrvT === "positive" ? "ok" : hrvT === "warning" ? "watch" : hrvT === "alert" ? "alert" : "neutral";
  const word = hrvT === "positive" ? "On baseline" : hrvT === "warning" ? "Slightly off" : hrvT === "alert" ? "Below baseline" : "—";

  // 30-day deviation trend: list of hrv_deviation_ms values from the
  // last 30 sleep sessions, oldest → newest.
  const trendItems = useMemo(() => {
    return [...listItems]
      .slice(0, 30)
      .reverse()
      .map((it) => ({
        date: it.local_date,
        dev: it.hrv_deviation_ms,
        isCurrent: it.local_date === selectedDate,
      }));
  }, [listItems, selectedDate]);

  return (
    <div>
      {/* HRV value + StatusDot */}
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="num flex items-baseline gap-1 text-ink">
            <span className="text-[40px] font-semibold leading-none">{fmtNum(hrvMs, 0)}</span>
            <span className="text-[16px] text-ink2">ms</span>
          </div>
          <div className="mt-2">
            <StatusDot tone={dotTone} label={word} />
          </div>
        </div>
        {hrvMean !== null && (
          <div className="num text-[14px] text-ink3">
            30d mean {fmtNum(hrvMean, 0)} ms · ±{fmtNum(hrvSd, 0)} sd
          </div>
        )}
      </div>

      {readings.length > 0 ? (
        <div className="mt-6">
          <ChartFrame
            title="Overnight HRV"
            info={<ChartInfoBadge text={<span>HRV sampled overnight. The dashed line is your rolling baseline; the shaded band is mean ± 1 SD.</span>} />}
          >
            <OvernightHrvChart readings={readings} hrvStats={hrvStats} />
          </ChartFrame>
        </div>
      ) : (
        <div className="mt-6 text-[14px] text-ink2">
          Your source didn't push overnight HRV readings for this night.
        </div>
      )}

      <Hairline className="my-6" />

      {/* 30-day deviation trend */}
      <div className="text-[14px] font-medium text-ink2">30-day deviation</div>
      {trendItems.some((it) => it.dev !== null) ? (
        <HrvDeviationTrend items={trendItems} hrvSd={hrvSd} />
      ) : (
        <div className="num mt-2 text-[14px] text-ink3">
          No HRV history yet — the deviation trend fills in once you have overnight HRV data.
        </div>
      )}
    </div>
  );
}

/** Overnight HRV chart — InteractiveLineChart with the rolling baseline
 *  as the dashed reference line. The chart's own `baseline` prop gives us
 *  the dashed line + baseline label. */
function OvernightHrvChart({
  readings,
  hrvStats,
}: {
  readings: HrvReadingOut[];
  hrvStats: VitalStats | null;
}) {
  const baseline = hrvStats?.mean ?? null;
  return (
    <InteractiveLineChart
      categories={readings.map((r) => ({
        label: new Date(r.timestamp).toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }),
      }))}
      series={[
        {
          name: "HRV",
          color: "var(--c-accent)",
          values: readings.map((r) => r.hrv_ms),
        },
      ]}
      baseline={baseline}
      baselineLabel="30d baseline"
      height={180}
      formatValue={(v) => (v === null ? "—" : `${Math.round(v)} ms`)}
    />
  );
}

/** 30-day HRV deviation trend — a small SVG bar chart with a zero line.
 *  Each bar is one night's hrv_deviation_ms; positive (above baseline)
 *  renders above the zero line, negative below. Color via hrvDevTone. */
function HrvDeviationTrend({
  items,
  hrvSd,
}: {
  items: { date: string; dev: number | null; isCurrent: boolean }[];
  hrvSd: number | null;
}) {
  const W = 1000;
  const H = 120;
  const padLeft = 8;
  const padRight = 8;
  const padTop = 8;
  const padBottom = 16;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;
  const midY = padTop + plotH / 2;

  const valid = items
    .map((it) => it.dev)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  if (!valid.length) {
    return <div className="num mt-2 text-[14px] text-ink3">No HRV history yet.</div>;
  }
  const maxAbs = Math.max(...valid.map((v) => Math.abs(v)), 1);
  const xStep = items.length > 1 ? plotW / (items.length - 1) : 0;
  const barW = Math.max(2, Math.min(10, xStep * 0.5));

  return (
    <div className="mt-3 overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: 480 }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="30-day HRV deviation trend"
      >
        {/* Zero line */}
        <line
          x1={padLeft}
          y1={midY}
          x2={padLeft + plotW}
          y2={midY}
          stroke="var(--c-divider-strong)"
          strokeWidth={1}
        />
        {/* ±1 SD reference band (optional, only when we have SD). */}
        {hrvSd !== null && hrvSd > 0 && (
          <>
            <line
              x1={padLeft}
              y1={midY - (hrvSd / maxAbs) * (plotH / 2)}
              x2={padLeft + plotW}
              y2={midY - (hrvSd / maxAbs) * (plotH / 2)}
              stroke="var(--c-text-3)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <line
              x1={padLeft}
              y1={midY + (hrvSd / maxAbs) * (plotH / 2)}
              x2={padLeft + plotW}
              y2={midY + (hrvSd / maxAbs) * (plotH / 2)}
              stroke="var(--c-text-3)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          </>
        )}

        {/* Bars — color by hrvDevTone(dev, hrvSd). */}
        {items.map((it, i) => {
          if (it.dev === null || !Number.isFinite(it.dev)) {
            const x = padLeft + i * xStep;
            return (
              <line
                key={i}
                x1={x}
                y1={midY - 2}
                x2={x}
                y2={midY + 2}
                stroke="var(--c-divider-strong)"
                strokeWidth={1}
              />
            );
          }
          const x = padLeft + i * xStep;
          const h = (Math.abs(it.dev) / maxAbs) * (plotH / 2);
          const y = it.dev >= 0 ? midY - h : midY;
          const tone = hrvDevTone(it.dev, hrvSd);
          const color =
            tone === "positive"
              ? "var(--c-ok)"
              : tone === "warning"
              ? "var(--c-watch)"
              : tone === "alert"
              ? "var(--c-alert)"
              : "var(--c-divider-strong)";
          return (
            <rect
              key={i}
              x={x - barW / 2}
              y={y}
              width={barW}
              height={h}
              fill={color}
              opacity={it.isCurrent ? 1 : 0.7}
              stroke={it.isCurrent ? "var(--c-text)" : "none"}
              strokeWidth={it.isCurrent ? 1 : 0}
            />
          );
        })}
      </svg>
      <div className="num mt-1 flex items-center justify-between text-[12px] text-ink3">
        <span>−{fmtNum(maxAbs, 0)} ms</span>
        <span>0 · baseline</span>
        <span>+{fmtNum(maxAbs, 0)} ms</span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- In context */
function InContextBlock({
  listItems,
  selectedDate,
  dashboard,
  onOverview,
}: {
  listItems: SessionItem[];
  selectedDate: string;
  dashboard: DashboardResponse | null;
  onOverview: () => void;
}) {
  // Most recent 7 nights (newest-first from API), reverse for left → right.
  const recent = useMemo(() => listItems.slice(0, 7).reverse(), [listItems]);

  const isMostRecent = listItems.length > 0 && listItems[0].local_date === selectedDate;
  const readiness = dashboard?.overview?.readiness?.value ?? null;
  const recovery = dashboard?.overview?.recovery?.value ?? null;
  const showTodayStrip = isMostRecent && (readiness !== null || recovery !== null);

  if (!recent.length) return null;

  const maxDur = Math.max(
    ...recent.map((it) => it.total_sleep_s ?? 0).filter((v) => Number.isFinite(v)),
    1,
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Mini bars: previous 7 nights with this night highlighted. */}
      <div className="lg:col-span-2">
        <div className="flex items-end gap-2">
          {recent.map((it) => {
            const dur = it.total_sleep_s ?? 0;
            const hPct = (dur / maxDur) * 100;
            const isCurrent = it.local_date === selectedDate;
            const tone = scoreTone(it.sleep_score);
            const color =
              tone === "positive"
                ? "var(--c-ok)"
                : tone === "warning"
                ? "var(--c-watch)"
                : tone === "alert"
                ? "var(--c-alert)"
                : "var(--c-divider-strong)";
            return (
              <div key={it.local_date} className="flex flex-1 flex-col items-center gap-1">
                <div className="num text-[12px] text-ink3">{fmtHours(dur)}</div>
                <div className="flex h-20 w-full items-end justify-center">
                  <div
                    className={`w-full max-w-[28px] rounded-[var(--radius-control)] ${isCurrent ? "ring-1 ring-ink" : ""}`}
                    style={{
                      height: `${Math.max(4, hPct)}%`,
                      background: color,
                      opacity: isCurrent ? 1 : 0.7,
                    }}
                    title={`${it.local_date}: ${fmtHours(dur)} · score ${fmtNum(it.sleep_score, 0)}`}
                  />
                </div>
                <div className="num text-[12px] text-ink3">{shortDate(it.local_date)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* "What this meant for today" */}
      <div className="lg:border-l lg:border-hairline lg:pl-6">
        <div className="text-[14px] font-medium text-ink2">What this meant for today</div>
        {showTodayStrip ? (
          <div className="mt-3 space-y-3">
            <TodayStat label="Readiness" value={readiness} tone={scoreTone(readiness)} />
            <TodayStat label="Recovery" value={recovery} tone={scoreTone(recovery)} />
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={onOverview}
              iconRight={<ArrowRight size={12} />}
            >
              Open Overview
            </ApexButton>
          </div>
        ) : (
          <div className="num mt-2 text-[14px] text-ink3">
            {isMostRecent
              ? "Today's readiness and recovery aren't available yet — connect a source or sync to see how last night affected today."
              : "This strip shows today's readiness and recovery only for the most recent night."}
          </div>
        )}
      </div>
    </div>
  );
}

function TodayStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone: DataTone;
}) {
  const dotTone = tone === "positive" ? "ok" : tone === "warning" ? "watch" : tone === "alert" ? "alert" : "neutral";
  const word = tone === "positive" ? "Good" : tone === "warning" ? "Moderate" : tone === "alert" ? "Low" : "—";
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[14px] text-ink2">{label}</span>
      <div className="flex items-center gap-2">
        <StatusDot tone={dotTone} label={word} />
        <span className="num text-[20px] font-semibold text-ink">
          {value !== null ? fmtNum(value, 0) : "—"}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------- Hypnogram (estimated) —
 * The DB stores only 4 stage TOTALS per night (deep_s / light_s / rem_s /
 * awake_s — NO real stage timeline). We synthesise a plausible sleep
 * architecture from the 4 totals — clearly labelled as an ESTIMATE.
 *
 * Algorithm: 3–5 cycles of ~90 min. Within each cycle: Light (descent) →
 * Deep → Light (ascent) → REM. Deep is front-loaded, REM back-loaded,
 * Light spread evenly. Awake time is scattered as short wake episodes
 * BETWEEN cycles, biased toward later in the night.
 */
type HypnogramSeg = {
  stage: StageKey;
  startMs: number;
  endMs: number;
  durS: number;
};

function buildHypnogramSegments(session: SessionItem): HypnogramSeg[] {
  const deep = session.deep_s ?? 0;
  const light = session.light_s ?? 0;
  const rem = session.rem_s ?? 0;
  const awake = session.awake_s ?? 0;
  const asleep = deep + light + rem;
  if (asleep <= 0) return [];

  const startMs = new Date(session.start_time).getTime();
  const endMs = new Date(session.end_time).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return [];
  }

  const windowS = (endMs - startMs) / 1000;
  const rawTotal = deep + light + rem + awake;
  const scale = rawTotal > 0 ? windowS / rawTotal : 1;
  const D = deep * scale;
  const L = light * scale;
  const R = rem * scale;
  const A = awake * scale;

  let numCycles = Math.max(3, Math.min(5, Math.round((D + L + R) / (90 * 60))));
  if (D + L + R < 3 * 3600) numCycles = 3;
  if (D + L + R > 9 * 3600) numCycles = 5;

  const deepW: number[] = [];
  const remW: number[] = [];
  const lightW: number[] = [];
  for (let i = 0; i < numCycles; i++) {
    deepW.push(numCycles - i);
    remW.push(i + 1);
    lightW.push(1);
  }
  const dSum = deepW.reduce((s, v) => s + v, 0) || 1;
  const rSum = remW.reduce((s, v) => s + v, 0) || 1;
  const lSum = lightW.reduce((s, v) => s + v, 0) || 1;
  const deepPer = deepW.map((w) => (D * w) / dSum);
  const remPer = remW.map((w) => (R * w) / rSum);
  const lightPer = lightW.map((w) => (L * w) / lSum);

  const awakeSlots = Math.max(0, numCycles - 1);
  const awakeW: number[] = [];
  for (let i = 0; i < awakeSlots; i++) awakeW.push(i + 1.5);
  const aSum = awakeW.reduce((s, v) => s + v, 0) || 1;
  const awakePer = awakeW.map((w) => (A * w) / aSum);

  const raw: HypnogramSeg[] = [];
  let t = startMs;
  const push = (stage: StageKey, durS: number) => {
    if (durS < 1) return;
    raw.push({ stage, startMs: t, endMs: t + durS * 1000, durS });
    t += durS * 1000;
  };
  for (let i = 0; i < numCycles; i++) {
    push("light", lightPer[i] / 2);
    push("deep", deepPer[i]);
    push("light", lightPer[i] / 2);
    push("rem", remPer[i]);
    if (i < numCycles - 1) push("awake", awakePer[i]);
  }

  const merged: HypnogramSeg[] = [];
  for (const seg of raw) {
    const last = merged[merged.length - 1];
    if (last && last.stage === seg.stage) {
      last.endMs = seg.endMs;
      last.durS += seg.durS;
    } else {
      merged.push({ ...seg });
    }
  }

  if (merged.length) {
    const last = merged[merged.length - 1];
    if (last.endMs !== endMs) {
      last.endMs = endMs;
      last.durS = (endMs - last.startMs) / 1000;
    }
  }
  return merged;
}

function Hypnogram({ session }: { session: SessionItem }) {
  const segments = useMemo(() => buildHypnogramSegments(session), [session]);
  const [hover, setHover] = useState<number | null>(null);

  const W = 1000;
  const H = 300;
  const padLeft = 60;
  const padRight = 22;
  const padTop = 16;
  const padBottom = 36;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;

  // Standard hypnogram Y-axis order: Awake (top) → REM → Light → Deep (bottom).
  const stageOrder: StageKey[] = ["awake", "rem", "light", "deep"];
  const stageLabel: Record<StageKey, string> = {
    awake: "Awake",
    rem: "REM",
    light: "Light",
    deep: "Deep",
  };
  const stageY: Record<StageKey, number> = {
    awake: padTop + 0.07 * plotH,
    rem: padTop + 0.35 * plotH,
    light: padTop + 0.63 * plotH,
    deep: padTop + 0.93 * plotH,
  };

  const startMs = new Date(session.start_time).getTime();
  const endMs = new Date(session.end_time).getTime();
  const totalMs = Math.max(endMs - startMs, 1);
  const xFor = (ms: number) => padLeft + ((ms - startMs) / totalMs) * plotW;

  const tickStepMs = totalMs > 8 * 3600 * 1000 ? 2 * 3600 * 1000 : 3600 * 1000;
  const ticks: { x: number; label: string }[] = [];
  for (let ms = 0; ms <= totalMs + 1; ms += tickStepMs) {
    const m = Math.min(ms, totalMs);
    ticks.push({
      x: xFor(startMs + m),
      label: new Date(startMs + m).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
    });
  }
  const lastLabel = new Date(endMs).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  if (!ticks.length || ticks[ticks.length - 1].label !== lastLabel) {
    ticks.push({ x: xFor(endMs), label: lastLabel });
  }

  if (!segments.length) {
    return (
      <div className="rounded-[var(--radius-control)] border border-dashed border-hairline2 px-4 py-6 text-center">
        <div className="text-[14px] font-semibold text-ink2">No stage data</div>
        <div className="num mt-1 text-[13px] text-ink3">
          This night has no recorded deep / light / REM totals, so an estimated hypnogram can't be built.
        </div>
      </div>
    );
  }

  const hoveredSeg = hover !== null ? segments[hover] : null;
  const hoverXPct = hoveredSeg
    ? ((xFor(hoveredSeg.startMs) + xFor(hoveredSeg.endMs)) / 2 / W) * 100
    : 0;
  const flip = hoverXPct > 75;

  return (
    <div className="relative">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: 480 }}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Estimated hypnogram"
          onMouseLeave={() => setHover(null)}
        >
          {/* Plot background — faint. */}
          <rect
            x={padLeft}
            y={padTop}
            width={plotW}
            height={plotH}
            fill="var(--c-surface-3)"
            opacity={0.25}
          />

          {/* Horizontal stage grid lines (dashed). */}
          {stageOrder.map((s) => (
            <line
              key={`grid-${s}`}
              x1={padLeft}
              y1={stageY[s]}
              x2={padLeft + plotW}
              y2={stageY[s]}
              stroke="var(--c-divider)"
              strokeWidth={1}
              strokeDasharray="2 4"
            />
          ))}

          {/* Awake highlight bands (full plot height, faint red). */}
          {segments.map((seg, i) =>
            seg.stage === "awake" ? (
              <rect
                key={`awake-${i}`}
                x={xFor(seg.startMs)}
                y={padTop}
                width={Math.max(1.5, xFor(seg.endMs) - xFor(seg.startMs))}
                height={plotH}
                fill="var(--c-alert)"
                opacity={0.09}
              />
            ) : null,
          )}

          {/* Vertical transitions between consecutive segments. */}
          {segments.slice(1).map((seg, i) => {
            const prev = segments[i];
            return (
              <line
                key={`v-${i}`}
                x1={xFor(seg.startMs)}
                y1={stageY[prev.stage]}
                x2={xFor(seg.startMs)}
                y2={stageY[seg.stage]}
                stroke="var(--c-text-3)"
                strokeWidth={1.2}
                opacity={0.7}
              />
            );
          })}

          {/* Horizontal segment lines (the step-line) — stage colour,
              thicker on hover. */}
          {segments.map((seg, i) => {
            const x1 = xFor(seg.startMs);
            const x2 = xFor(seg.endMs);
            const y = stageY[seg.stage];
            const isHover = hover === i;
            return (
              <line
                key={`h-${i}`}
                x1={x1}
                y1={y}
                x2={x2}
                y2={y}
                stroke={STAGE_VARS[seg.stage]}
                strokeWidth={isHover ? 5 : 3.5}
                strokeLinecap="round"
              />
            );
          })}

          {/* Y-axis stage labels. */}
          {stageOrder.map((s) => (
            <text
              key={`yl-${s}`}
              x={padLeft - 10}
              y={stageY[s] + 3.5}
              textAnchor="end"
              style={{
                fontSize: 13,
                fill: "var(--c-text-2)",
                fontFamily: "var(--font-mono)",
              }}
            >
              {stageLabel[s]}
            </text>
          ))}

          {/* X-axis baseline + ticks. */}
          <line
            x1={padLeft}
            y1={padTop + plotH}
            x2={padLeft + plotW}
            y2={padTop + plotH}
            stroke="var(--c-divider-strong)"
            strokeWidth={1}
          />
          {ticks.map((tick, i) => (
            <g key={`xt-${i}`}>
              <line
                x1={tick.x}
                y1={padTop + plotH}
                x2={tick.x}
                y2={padTop + plotH + 4}
                stroke="var(--c-divider-strong)"
                strokeWidth={1}
              />
              <text
                x={tick.x}
                y={padTop + plotH + 18}
                textAnchor="middle"
                style={{
                  fontSize: 11,
                  fill: "var(--c-text-3)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {tick.label}
              </text>
            </g>
          ))}

          {/* Hover hit-rects */}
          {segments.map((seg, i) => {
            const x1 = xFor(seg.startMs);
            const x2 = xFor(seg.endMs);
            return (
              <rect
                key={`hit-${i}`}
                x={x1}
                y={padTop}
                width={Math.max(3, x2 - x1)}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                style={{ cursor: "pointer" }}
              />
            );
          })}
        </svg>
      </div>

      {/* Hover tooltip */}
      {hover !== null && hoveredSeg && (
        <div
          style={{
            position: "absolute",
            left: flip ? undefined : `${hoverXPct}%`,
            right: flip ? `${100 - hoverXPct}%` : undefined,
            top: 4,
            transform: flip ? undefined : "translateX(8px)",
            pointerEvents: "none",
            zIndex: 30,
          }}
          className="num min-w-[170px] max-w-[230px] rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
        >
          <div className="mb-1 flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: STAGE_VARS[hoveredSeg.stage] }}
            />
            <span className="text-[14px] font-semibold text-ink">
              {stageLabel[hoveredSeg.stage]}
            </span>
          </div>
          <div className="text-[12px] text-ink2">
            {new Date(hoveredSeg.startMs).toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })}
            {" → "}
            {new Date(hoveredSeg.endMs).toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })}
          </div>
          <div className="num mt-0.5 text-[12px] text-ink3">
            {fmtDurShort(hoveredSeg.durS)}
            {" · "}
            {hoveredSeg.stage === "awake" ? "wake episode" : "cycle phase"}
          </div>
        </div>
      )}

      {/* Caption */}
      <div className="num mt-2 text-[12px] text-ink3">
        Estimated from stage totals — no real timeline data
      </div>
    </div>
  );
}

function fmtDurShort(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "—";
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.round((total % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function shortDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

/* --------------------------------------------------------------- tone helpers */
function scoreToDot(t: DataTone): "neutral" | "ok" | "watch" | "alert" {
  return t === "positive" ? "ok" : t === "warning" ? "watch" : t === "alert" ? "alert" : "neutral";
}

function scoreBandWord(score: number | null, baseline: BaselineBlock | null): string {
  if (score === null) return "—";
  if (!baseline) {
    const t = scoreTone(score);
    return t === "positive" ? "Good" : t === "warning" ? "Fair" : t === "alert" ? "Low" : "—";
  }
  const p33 = baseline.sleep_scores.p33;
  const p66 = baseline.sleep_scores.p66;
  if (p33 === null || p66 === null || baseline.sleep_scores.count < 5) {
    const t = scoreTone(score);
    return t === "positive" ? "Good" : t === "warning" ? "Fair" : t === "alert" ? "Low" : "—";
  }
  if (score >= p66) return "Top third";
  if (score <= p33) return "Low";
  return "Typical";
}

function durationTone(dur: number, targetS: number): "neutral" | "ok" | "watch" | "alert" {
  if (!Number.isFinite(dur)) return "neutral";
  const ratio = dur / targetS;
  if (ratio >= 0.9) return "ok";
  if (ratio >= 0.7) return "watch";
  return "alert";
}

function durationWord(dur: number, targetS: number): string {
  if (!Number.isFinite(dur)) return "—";
  const ratio = dur / targetS;
  if (ratio >= 0.9) return "On target";
  if (ratio >= 0.7) return "Slightly short";
  return "Short";
}
