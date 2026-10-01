"use client";

/**
 * Apex Health — Sleep night (strict redesign per plan §4).
 *
 * Layout:
 *   Header: BackLink, date title, prev / next night arrows.
 *   Row 1 (xl:col-4 + xl:col-8):
 *     - Score card: BigStat with scoreTone + badge computed against the
 *       30-day score distribution (top third / typical / low) — not a
 *       constant. Efficiency with an "Asleep ÷ sleep window" tooltip.
 *       Latency tile is REMOVED (no source provides it).
 *     - Duration analysis: time asleep + real DeltaChip vs target
 *       (goodWhen="up"), sleep window, deep + REM, awake. ONE stage
 *       composition bar — denominator = time asleep (deep + light + REM),
 *       labels read "of time asleep".
 *   Row 2 (col-12): Stage composition, honest mode — one horizontal stacked
 *     bar + a table: stage, duration, % of sleep, 30-day average, typical
 *     range. NO timeline is drawn. Caption: "This source provides stage
 *     totals only — no timeline."
 *   Row 3 (col-12 xl:col-6 + col-12 xl:col-6):
 *     - Left: vitals against baseline — Resting HR, SpO₂, Respiration,
 *       Skin Temp (if available) as RangeBar against your 30-day band
 *       (mean ± 1 SD) with a DeltaChip and rangeTone. InfoButton next to
 *       each label with content from metricInfo.ts.
 *     - Right: overnight HRV curve with the rolling baseline band, and the
 *       30-day deviation trend below with a zero line. hrvDevTone for the
 *       deviation color.
 *   Row 4 (col-12): previous 7 nights as mini bars with this night
 *     highlighted, and a "What this meant for today" strip: today's
 *     readiness and recovery with a link to the Overview.
 *
 * Coherence law: kit-only. Data tone from scoreTone / rangeTone / hrvDevTone.
 * The fake hypnogram is GONE — this source provides stage totals only.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ArrowRight } from "lucide-react";
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
  Hairline,
  BackLink,
  RangeBar,
  InfoButton,
  MetricInfoContent,
  ApexButton,
  scoreTone,
  rangeTone,
  hrvDevTone,
  toneFor,
  type DataTone,
} from "@/components/apex/kit";
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
  const t = useT();
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
      // Always fetch the list in parallel — used for prev/next navigation
      // and the "last 7 nights" mini bars. If no date is selected yet,
      // the list also tells us what the most recent night is.
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
      // If we auto-selected the most recent night, persist it in the UI
      // store so prev/next arrows work on the next render.
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
  const allDates = useMemo(
    () => list?.all_dates ?? [],
    [list],
  );
  const currentIndex = useMemo(
    () => (sessionDate ? allDates.indexOf(sessionDate) : -1),
    [allDates, sessionDate],
  );
  const prevDate = currentIndex > 0 ? allDates[currentIndex - 1] : null;
  const nextDate =
    currentIndex >= 0 && currentIndex < allDates.length - 1
      ? allDates[currentIndex + 1]
      : null;

  // ─────────────────────────────────────────────────────────────── render
  if (loading && !detail) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <BackLink onClick={() => ui.setView("sleep")}>{t("sleep.back_to_list")}</BackLink>
        <div className="mt-6">
          <Loading label="Loading night…" />
        </div>
      </div>
    );
  }

  if (error || !detail || !detail.session) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <BackLink onClick={() => ui.setView("sleep")}>{t("sleep.back_to_list")}</BackLink>
        <div className="mt-6">
          <Empty title={t("sleep.empty")} body={error ?? undefined} />
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

  return (
    <div className="mx-auto max-w-[1240px]">
      <BackLink onClick={() => ui.setView("sleep")}>{t("sleep.back_to_list")}</BackLink>

      <PageHeader
        className="mt-3"
        title={fmtDateLong(session.local_date, ui.locale)}
        subtitle={t("sleep.night")}
        actions={
          <div className="flex items-center gap-1.5">
            <PrevNextArrow
              dir="prev"
              disabled={!prevDate}
              onClick={() => prevDate && ui.selectSleepDate(prevDate)}
            />
            <PrevNextArrow
              dir="next"
              disabled={!nextDate}
              onClick={() => nextDate && ui.selectSleepDate(nextDate)}
            />
          </div>
        }
      />

      {/* ───────────────────────────────────────────── Row 1 — score + duration */}
      <div className="mt-6 grid grid-cols-12 gap-3">
        <div className="col-span-12 xl:col-span-4">
          <ScoreCard
            score={score}
            efficiency={effPct}
            baseline={baseline}
          />
        </div>
        <div className="col-span-12 xl:col-span-8">
          <DurationAnalysisCard
            session={session}
            targetS={targetS}
            asleepS={asleepS}
            winS={winS}
          />
        </div>
      </div>

      {/* ───────────────────────────────────────────── Row 2 — Stages */}
      <div className="mt-3">
        <StageCompositionCard
          session={session}
          baseline={baseline}
        />
      </div>

      {/* ───────────────────────────────────────── Row 3 — Vitals + HRV */}
      <div className="mt-3 grid grid-cols-12 gap-3">
        <div className="col-span-12 xl:col-span-6">
          <VitalsAgainstBaselineCard
            bio={bio}
            session={session}
            baseline={baseline}
          />
        </div>
        <div className="col-span-12 xl:col-span-6">
          <HrvCard
            readings={hrvReadings}
            hrvMs={bio?.hrv_ms ?? null}
            hrvStats={baseline?.vitals.hrv_ms ?? null}
            listItems={list?.items ?? []}
            selectedDate={session.local_date}
          />
        </div>
      </div>

      {/* ───────────────────────────────────────────── Row 4 — In context */}
      <div className="mt-3">
        <InContextCard
          listItems={list?.items ?? []}
          selectedDate={session.local_date}
          dashboard={dashboard}
          onOverview={() => ui.setView("overview")}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------- Header: prev / next arrows */
function PrevNextArrow({
  dir,
  disabled,
  onClick,
}: {
  dir: "prev" | "next";
  disabled: boolean;
  onClick: () => void;
}) {
  const Icon = dir === "prev" ? ChevronLeft : ChevronRight;
  return (
    <ApexButton
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === "prev" ? "Previous night" : "Next night"}
    >
      <Icon size={14} />
    </ApexButton>
  );
}

/* ----------------------------------------------------------- Row 1: Score card */
function ScoreCard({
  score,
  efficiency,
  baseline,
}: {
  score: number | null;
  efficiency: number;
  baseline: BaselineBlock | null;
}) {
  const t = useT();
  // Plan §4: badge computed against 30-day distribution (top third /
  // typical / low), not a constant threshold.
  const scoreBand = useMemo<{
    label: string;
    tone: "positive" | "primary" | "warning";
  } | null>(() => {
    if (score === null || !baseline) return null;
    const p33 = baseline.sleep_scores.p33;
    const p66 = baseline.sleep_scores.p66;
    if (p33 === null || p66 === null) return null;
    if (baseline.sleep_scores.count < 5) return null;
    if (score >= p66) return { label: "Top third", tone: "positive" };
    if (score <= p33) return { label: "Low", tone: "warning" };
    return { label: "Typical", tone: "primary" };
  }, [score, baseline]);

  // Efficiency DeltaChip vs 30-day average (we don't have a 30-day eff
  // directly, so we use score's mean as a proxy baseline of 75% default).
  // Plan §4 says the score badge is computed; the efficiency just needs
  // its tooltip — no delta chip required here.
  const effTone: DataTone =
    efficiency >= 90 ? "positive" : efficiency >= 80 ? "warning" : "alert";

  return (
    <Card className="h-full">
      <CardHeader eyebrow={t("sleep.score")} title={t("sleep.night")} />
      <div className="flex items-end gap-2.5">
        <BigStat
          value={fmtNum(score, 0)}
          unit="/100"
          size="xl"
          tone={toneFor(scoreTone(score))}
        />
        {scoreBand && (
          <Badge tone={scoreBand.tone} dot className="mb-2.5">
            {scoreBand.label}
            {/* TODO i18n */}
          </Badge>
        )}
      </div>
      <Hairline className="my-4" />

      {/* Efficiency with tooltip — plan §4 "Asleep ÷ sleep window". */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Eyebrow>{t("sleep.efficiency")}</Eyebrow>
          <InfoButton title={"Sleep efficiency"}>
            <MetricInfoContent
              whatItMeasures={"Asleep ÷ sleep window — the share of the time you were in bed that you actually slept."}
              whyItMatters={"Even with 8h in bed, low efficiency (lots of tossing or wake-ups) means less restorative sleep."}
              whatInfluencesIt={"Stress, caffeine late in the day, alcohol, irregular schedule, screen time, room temperature, sleep disorders."}
              howToReadIt={"≥85% good · 75–84% fair · <75% poor. Track the trend — one bad night is normal."}
            />
          </InfoButton>
        </div>
        <BigStat
          value={fmtNum(efficiency, 0)}
          unit="%"
          size="lg"
          tone={toneFor(effTone)}
        />
      </div>
    </Card>
  );
}

/* --------------------------------------------------- Row 1: Duration analysis */
function DurationAnalysisCard({
  session,
  targetS,
  asleepS,
  winS,
}: {
  session: SessionItem;
  targetS: number;
  asleepS: number;
  winS: number;
}) {
  const t = useT();
  // Real delta vs target (plan §4) — goodWhen="up" (sleeping more than
  // target is good).
  const deltaVsTargetMin = Math.round((asleepS - targetS) / 60);

  const deepS = session.deep_s ?? 0;
  const remS = session.rem_s ?? 0;
  const awakeS = session.awake_s ?? 0;

  // Stage composition: ONE horizontal stacked bar (deep / light / REM),
  // denominator = time asleep. Plan §4 fixes the unit bug — all stages
  // in seconds, all %s "of time asleep".
  const stages: { key: StageKey; secs: number; color: string }[] = [
    { key: "deep", secs: deepS, color: STAGE_VARS.deep },
    { key: "light", secs: session.light_s ?? 0, color: STAGE_VARS.light },
    { key: "rem", secs: remS, color: STAGE_VARS.rem },
  ];
  const totalAsleep = deepS + (session.light_s ?? 0) + remS;

  return (
    <Card className="h-full">
      <CardHeader eyebrow={"Duration analysis" /* TODO i18n */} title={"Did I sleep enough?" /* TODO i18n */} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat
          label={t("sleep.total")}
          value={fmtHours(asleepS)}
          chip={
            <DeltaChip
              delta={deltaVsTargetMin}
              unit="min"
              goodWhen="up"
              suffix={"vs target"}
            />
          }
          foot={`Target ${fmtHours(targetS)}`}
        />
        <MiniStat
          label={"Sleep window" /* TODO i18n */}
          value={fmtHours(winS)}
          foot={`Efficiency ${fmtNum(sleepEfficiencyPct(session), 0)}%`}
        />
        <MiniStat
          label={"Deep + REM" /* TODO i18n */}
          value={fmtHours(deepS + remS)}
          foot={`${fmtNum((deepS + remS) / (totalAsleep || 1) * 100, 0)}% of sleep`}
        />
        <MiniStat
          label={t("sleep.awake")}
          value={fmtHours(awakeS)}
          foot={`${fmtNum(awakeS / (winS || 1) * 100, 0)}% of window`}
        />
      </div>

      {/* Stage composition bar — single horizontal stacked bar, denominator
          = time asleep (deep + light + REM). Plan §4: labels read "of time
          asleep". */}
      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between">
          <Eyebrow>{"Composition · of time asleep" /* TODO i18n */}</Eyebrow>
          <span className="num text-[10px] text-faint">
            {fmtHours(totalAsleep)} asleep
          </span>
        </div>
        <div className="flex h-6 w-full overflow-hidden rounded-[var(--radius-control)] bg-surface3">
          {stages.map((s) => {
            const pct = totalAsleep > 0 ? (s.secs / totalAsleep) * 100 : 0;
            if (pct <= 0) return null;
            return (
              <div
                key={s.key}
                className="flex items-center justify-center text-[9px] font-semibold text-white/80 transition-all"
                style={{ width: `${pct}%`, background: s.color }}
                title={`${t_label(s.key)}: ${fmtHours(s.secs)} (${Math.round(pct)}% of time asleep)`}
              >
                {pct > 12 && <span>{Math.round(pct)}%</span>}
              </div>
            );
          })}
        </div>
        <div className="num mt-1.5 flex items-center gap-4 text-[10px] text-muted">
          <LegendDot color={STAGE_VARS.deep} label={t("sleep.deep")} />
          <LegendDot color={STAGE_VARS.light} label={t("sleep.light")} />
          <LegendDot color={STAGE_VARS.rem} label={t("sleep.rem")} />
        </div>
        <div className="num mt-1 text-[10px] text-faint">
          {"This source provides stage totals only — no timeline." /* TODO i18n */}
        </div>
      </div>
    </Card>
  );
}

function MiniStat({
  label,
  value,
  chip,
  foot,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  chip?: React.ReactNode;
  foot?: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2/50 px-3 py-2">
      <Eyebrow>{label}</Eyebrow>
      <div className="num mt-0.5 text-[20px] font-bold leading-6 text-ink">
        {value}
      </div>
      {chip && <div className="mt-1">{chip}</div>}
      {foot && <div className="num mt-0.5 text-[10px] text-faint">{foot}</div>}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: color }}
      />
      <span>{label}</span>
    </span>
  );
}

/* --------------------------------------------------------- Row 2: Stages */
function StageCompositionCard({
  session,
  baseline,
}: {
  session: SessionItem;
  baseline: BaselineBlock | null;
}) {
  const t = useT();

  const stageRows: {
    key: StageKey;
    label: string;
    secs: number;
    color: string;
  }[] = [
    { key: "deep", label: t("sleep.deep"), secs: session.deep_s ?? 0, color: STAGE_VARS.deep },
    { key: "light", label: t("sleep.light"), secs: session.light_s ?? 0, color: STAGE_VARS.light },
    { key: "rem", label: t("sleep.rem"), secs: session.rem_s ?? 0, color: STAGE_VARS.rem },
    { key: "awake", label: t("sleep.awake"), secs: session.awake_s ?? 0, color: STAGE_VARS.awake },
  ];

  const totalAsleep =
    (session.deep_s ?? 0) + (session.light_s ?? 0) + (session.rem_s ?? 0) || 1;

  // Bar uses the three asleep stages (plan §4 denominator = time asleep).
  const barStages = stageRows.filter((s) => s.key !== "awake");

  return (
    <Card>
      <CardHeader
        eyebrow={"Stages" /* TODO i18n */}
        title={"Composition" /* TODO i18n */}
        right={
          <span className="num text-[10px] text-faint">
            {"of time asleep" /* TODO i18n */}
          </span>
        }
      />

      {/* ONE horizontal stacked bar — deep / light / REM. Denominator =
          time asleep so the three stages sum to 100%. Plan §4 fixes the
          unit bug: the old awake block was rendered in seconds on a ms
          axis; here everything is seconds. */}
      <div className="flex h-7 w-full overflow-hidden rounded-[var(--radius-control)] bg-surface3">
        {barStages.map((s) => {
          const pct = totalAsleep > 0 ? (s.secs / totalAsleep) * 100 : 0;
          if (pct <= 0) return null;
          return (
            <div
              key={s.key}
              className="flex items-center justify-center text-[10px] font-semibold text-white/80"
              style={{ width: `${pct}%`, background: s.color }}
              title={`${s.label}: ${fmtHours(s.secs)} (${Math.round(pct)}% of time asleep)`}
            >
              {pct > 10 && <span>{Math.round(pct)}%</span>}
            </div>
          );
        })}
      </div>

      {/* Composition table: stage, duration, % of sleep, 30-day average,
          typical range. */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <thead>
            <tr className="border-b border-hairline text-left">
              <th className="eyebrow py-1.5 pr-3 font-medium">{"Stage" /* TODO i18n */}</th>
              <th className="eyebrow py-1.5 pr-3 font-medium">{"Duration" /* TODO i18n */}</th>
              <th className="eyebrow py-1.5 pr-3 font-medium">{"% of sleep" /* TODO i18n */}</th>
              <th className="eyebrow py-1.5 pr-3 font-medium">{"30-day avg" /* TODO i18n */}</th>
              <th className="eyebrow py-1.5 font-medium">{"Typical range" /* TODO i18n */}</th>
            </tr>
          </thead>
          <tbody>
            {stageRows.map((s) => {
              const pctOfSleep =
                s.key === "awake"
                  ? (s.secs / totalAsleep) * 100
                  : (s.secs / totalAsleep) * 100;
              const avgS = baseline?.stages[s.key]?.mean_s ?? null;
              const avgPct = baseline?.stages[s.key]?.mean_pct ?? null;
              const typical = TYPICAL_STAGE_RANGE[s.key];
              return (
                <tr
                  key={s.key}
                  className="border-b border-hairline last:border-0"
                >
                  <td className="py-2 pr-3">
                    <span className="inline-flex items-center gap-2 text-[12px] font-medium text-ink">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{ background: s.color }}
                      />
                      {s.label}
                    </span>
                  </td>
                  <td className="num py-2 pr-3 text-[12px] text-ink2">
                    {fmtHours(s.secs)}
                  </td>
                  <td className="num py-2 pr-3 text-[12px] text-ink2">
                    {fmtNum(pctOfSleep, 0)}%
                  </td>
                  <td className="num py-2 pr-3 text-[12px] text-muted">
                    {avgS !== null
                      ? `${fmtHours(avgS)} (${fmtNum(avgPct ?? 0, 0)}%)`
                      : "—"}
                  </td>
                  <td className="num py-2 text-[12px] text-faint">
                    {s.key === "awake"
                      ? "—"
                      : `${typical.low}–${typical.high}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Caption — explicit about source limitation (plan §4). */}
      <div className="num mt-3 text-[11px] text-faint">
        {"This source provides stage totals only — no timeline." /* TODO i18n */}
      </div>
    </Card>
  );
}

/* ----------------------------------------------- Row 3 left: Vitals vs baseline */
function VitalsAgainstBaselineCard({
  bio,
  session,
  baseline,
}: {
  bio: BiometricsOut | null;
  session: SessionItem;
  baseline: BaselineBlock | null;
}) {
  const t = useT();

  // The SleepSession itself carries respiration_avg / spo2_avg in some
  // sources; the DailyBiometric (bio) is the more reliable per-date vital
  // record. Plan §4 says to use biometrics + 30-day bands.
  const restingHr = bio?.resting_hr ?? null;
  const spo2 = bio?.spo2_avg ?? session.spo2_avg ?? null;
  const respiration = bio?.respiration_avg ?? session.respiration_avg ?? null;
  const skinTemp = bio?.skin_temp_c ?? null; // schema doesn't surface this yet

  const tiles: {
    key: string;
    label: string;
    value: number | null;
    unit: string;
    stats: VitalStats | null;
  }[] = [
    {
      key: "resting_hr",
      label: t("sleep.resting_hr"),
      value: restingHr,
      unit: "bpm",
      stats: baseline?.vitals.resting_hr ?? null,
    },
    {
      key: "spo2_avg",
      label: t("sleep.spo2"),
      value: spo2,
      unit: "%",
      stats: baseline?.vitals.spo2_avg ?? null,
    },
    {
      key: "respiration_avg",
      label: t("sleep.respiration"),
      value: respiration,
      unit: "brpm",
      stats: baseline?.vitals.respiration_avg ?? null,
    },
    {
      key: "skin_temp",
      label: t("sleep.skin_temp"),
      value: skinTemp,
      unit: "°C",
      stats: null, // no 30-day baseline for skin temp yet
    },
  ];

  return (
    <Card className="h-full">
      <CardHeader
        eyebrow={"Vitals vs baseline" /* TODO i18n */}
        title={"Was your body calm overnight?" /* TODO i18n */}
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {tiles.map((tile) => (
          <VitalTile key={tile.key} tile={tile} />
        ))}
      </div>
    </Card>
  );
}

function VitalTile({
  tile,
}: {
  tile: {
    key: string;
    label: string;
    value: number | null;
    unit: string;
    stats: VitalStats | null;
  };
}) {
  const expl = getMetricExplanation(tile.key);
  // Plan §4: DeltaChip against your 30-day mean.
  const mean = tile.stats?.mean ?? null;
  const low = tile.stats?.low ?? null;
  const high = tile.stats?.high ?? null;
  const delta =
    tile.value !== null && mean !== null ? tile.value - mean : null;
  // rangeTone for the value against the 30-day band.
  const tone = rangeTone(tile.value, low, high);
  const toneCls = toneTextClass(tone);
  const showRange = low !== null && high !== null && tile.value !== null;

  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2/50 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Eyebrow>{tile.label}</Eyebrow>
          <InfoButton title={tile.label}>
            <MetricInfoContent
              whatItMeasures={expl.whatItMeasures}
              whyItMatters={expl.whyItMatters}
              whatInfluencesIt={expl.whatInfluencesIt}
              howToReadIt={expl.howToReadIt}
            />
          </InfoButton>
        </div>
        {delta !== null && (
          <DeltaChip
            delta={Math.round(delta * 10) / 10}
            unit={tile.unit}
            goodWhen={
              // For resting HR / respiration, lower is generally better.
              // For SpO₂ / skin temp, higher (or stable) is fine.
              tile.key === "resting_hr" || tile.key === "respiration_avg"
                ? "down"
                : "up"
            }
          />
        )}
      </div>

      <div className="num mt-1 flex items-baseline gap-1">
        <span className={`text-[22px] font-bold leading-7 ${toneCls}`}>
          {tile.value !== null ? fmtNum(tile.value, tile.unit === "%" || tile.unit === "°C" ? 1 : 0) : "—"}
        </span>
        {tile.value !== null && (
          <span className="text-[10px] font-medium text-muted">{tile.unit}</span>
        )}
      </div>

      {showRange ? (
        <div className="mt-2">
          <RangeBar
            value={tile.value}
            low={low}
            high={high}
            tone={toneFor(tone)}
            unit={tile.unit}
            height={4}
          />
          <div className="num mt-1 flex items-center justify-between text-[10px] text-faint">
            <span>Low {fmtNum(low, tile.unit === "%" || tile.unit === "°C" ? 1 : 0)}</span>
            <span>30-day band</span>
            <span>High {fmtNum(high, tile.unit === "%" || tile.unit === "°C" ? 1 : 0)}</span>
          </div>
        </div>
      ) : (
        <div className="num mt-2 text-[10px] text-faint">
          {mean !== null
            ? `30-day mean ${fmtNum(mean, tile.unit === "%" || tile.unit === "°C" ? 1 : 0)}`
            : "No 30-day baseline yet"}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------- Row 3 right: HRV */
function HrvCard({
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
  const t = useT();
  const hrvMean = hrvStats?.mean ?? null;
  const hrvSd = hrvStats?.sd ?? null;
  const hrvDev = hrvMs !== null && hrvMean !== null ? hrvMs - hrvMean : null;
  const hrvTone = hrvDevTone(hrvDev, hrvSd);

  // 30-day deviation trend: list of hrv_deviation_ms values from the
  // last 30 sleep sessions, oldest → newest. Zero line + the deviation
  // color (hrvDevTone).
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
    <Card className="h-full">
      <CardHeader
        eyebrow={t("sleep.hrv")}
        title={"Recovery signal" /* TODO i18n */}
        right={
          hrvDev !== null ? (
            <Badge tone={toneToBadgeTone(hrvTone)} dot>
              {hrvDev >= 0 ? "+" : "−"}
              {fmtNum(Math.abs(hrvDev), 0)} ms vs 30d
            </Badge>
          ) : null
        }
      />

      {/* HRV value */}
      <div className="mb-3 flex items-baseline gap-2">
        <BigStat
          value={fmtNum(hrvMs, 0)}
          unit="ms"
          size="md"
          tone={toneFor(hrvTone)}
        />
        {hrvMean !== null && (
          <span className="num text-[11px] text-faint">
            30d mean {fmtNum(hrvMean, 0)} ms · ±{fmtNum(hrvSd, 0)} sd
          </span>
        )}
      </div>

      {readings.length > 0 ? (
        <HrvCurve readings={readings} />
      ) : (
        <div className="rounded-[var(--radius-control)] border border-dashed border-hairline2 px-4 py-6 text-center">
          <div className="text-[12px] font-semibold text-ink2">No HRV data</div>
          <div className="num mt-0.5 text-[11px] text-faint">
            Your source didn't push overnight HRV readings for this night.
          </div>
        </div>
      )}

      <Hairline className="my-4" />

      {/* 30-day deviation trend with zero line. */}
      <div>
        <Eyebrow>{"30-day deviation" /* TODO i18n */}</Eyebrow>
        {trendItems.some((it) => it.dev !== null) ? (
          <HrvDeviationTrend items={trendItems} hrvSd={hrvSd} />
        ) : (
          <div className="num mt-1 text-[11px] text-faint">
            No HRV history yet — the deviation trend fills in once you have
            overnight HRV data.
          </div>
        )}
      </div>
    </Card>
  );
}

function toneToBadgeTone(tone: DataTone): "positive" | "warning" | "alert" | "neutral" {
  if (tone === "positive") return "positive";
  if (tone === "warning") return "warning";
  if (tone === "alert") return "alert";
  return "neutral";
}

function toneTextClass(tone: DataTone): string {
  return {
    positive: "text-positiveText",
    warning: "text-warningText",
    alert: "text-alertText",
    muted: "text-muted",
  }[tone];
}

/** Overnight HRV curve with rolling baseline band. */
function HrvCurve({ readings }: { readings: HrvReadingOut[] }) {
  const W = 1000;
  const H = 200;
  const padLeft = 44;
  const padRight = 16;
  const padTop = 12;
  const padBottom = 28;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;

  const values = readings.map((r) => r.hrv_ms);
  const baselines = readings
    .map((r) => r.rolling_baseline_ms)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const all = [...values, ...baselines];
  const rawMin = Math.min(...all);
  const rawMax = Math.max(...all);
  const pad = (rawMax - rawMin) * 0.12 || 4;
  const yMin = rawMin - pad;
  const yMax = rawMax + pad;
  const yRange = yMax - yMin || 1;

  const baselineMs =
    baselines.length > 0
      ? baselines.reduce((s, v) => s + v, 0) / baselines.length
      : null;

  const startMs = new Date(readings[0].timestamp).getTime();
  const endMs = new Date(readings[readings.length - 1].timestamp).getTime();
  const totalMs = Math.max(endMs - startMs, 1);

  const linePath = readings
    .map((r, i) => {
      const ts = new Date(r.timestamp).getTime();
      const x = padLeft + ((ts - startMs) / totalMs) * plotW;
      const y = padTop + plotH - ((r.hrv_ms - yMin) / yRange) * plotH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Baseline band: ±1 SD of rolling_baseline_ms around the mean. If
  // rolling_baseline_ms is sparse, just draw the mean line.
  const baselineBand = (() => {
    if (baselines.length < 2) return null;
    const m = baselines.reduce((s, v) => s + v, 0) / baselines.length;
    const variance =
      baselines.reduce((s, v) => s + (v - m) ** 2, 0) /
      (baselines.length - 1);
    const sd = Math.sqrt(variance);
    return { mean: m, sd };
  })();

  const yToPx = (v: number) =>
    padTop + plotH - ((v - yMin) / yRange) * plotH;

  const yTicks = [yMin, yMin + yRange / 2, yMax];
  const twoH = 2 * 3600 * 1000;
  const xMarks: { x: number; label: string }[] = [];
  for (let ms = 0; ms <= totalMs + 1; ms += twoH) {
    const ts = startMs + Math.min(ms, totalMs);
    const x = padLeft + (Math.min(ms, totalMs) / totalMs) * plotW;
    const label = new Date(ts).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    xMarks.push({ x, label });
  }

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: 480 }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Overnight HRV curve"
      >
        {/* Y-axis grid + ticks */}
        {yTicks.map((v, i) => {
          const y = yToPx(v);
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
                {fmtNum(v, 0)}
              </text>
            </g>
          );
        })}

        {/* Baseline band — mean ± 1 SD (faint fill). Plan §4: "rolling
            baseline band (the series already returned with
            rolling_baseline_ms)". */}
        {baselineBand && (
          <rect
            x={padLeft}
            y={yToPx(baselineBand.mean + baselineBand.sd)}
            width={plotW}
            height={
              yToPx(baselineBand.mean - baselineBand.sd) -
              yToPx(baselineBand.mean + baselineBand.sd)
            }
            fill="var(--c-text-faint)"
            opacity={0.1}
          />
        )}

        {/* Rolling baseline dashed line (mean of the rolling series). */}
        {baselineMs !== null && (
          <line
            x1={padLeft}
            y1={yToPx(baselineMs)}
            x2={padLeft + plotW}
            y2={yToPx(baselineMs)}
            stroke="var(--c-text-faint)"
            strokeWidth={1.4}
            strokeDasharray="4 3"
          />
        )}

        {/* Area fill under line */}
        <path
          d={`M${linePath} L${padLeft + plotW},${padTop + plotH} L${padLeft},${padTop + plotH} Z`}
          fill="var(--c-positive)"
          fillOpacity={0.08}
          stroke="none"
        />

        {/* HRV line — color via hrvDevTone of the latest value relative to
            the baseline mean. Plan §4 says hrvDevTone for the deviation
            color; here we apply it to the curve so the line reads STATE. */}
        <path
          d={`M${linePath}`}
          fill="none"
          stroke={toneToVar(toneForHrvCurve(values, baselineMs))}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* X-axis baseline */}
        <line
          x1={padLeft}
          y1={padTop + plotH}
          x2={padLeft + plotW}
          y2={padTop + plotH}
          stroke="var(--c-hairline-strong)"
          strokeWidth={1}
        />

        {/* X-axis time marks */}
        {xMarks.map((m, i) => (
          <text
            key={i}
            x={m.x}
            y={padTop + plotH + 18}
            textAnchor="middle"
            style={{
              fontSize: 10,
              fill: "var(--c-text-muted)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {m.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

function toneForHrvCurve(values: number[], baselineMs: number | null): DataTone {
  if (!values.length || baselineMs === null) return "muted";
  const last = values[values.length - 1];
  const dev = last - baselineMs;
  // Use a flat 8ms threshold when no SD is available.
  return hrvDevTone(dev, 8);
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

/** 30-day HRV deviation trend — a small SVG bar chart with a zero line.
 *  Each bar is one night's hrv_deviation_ms; positive (above baseline)
 *  renders above the zero line, negative below. Plan §4: zero line +
 *  hrvDevTone for the color. */
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

  const valid = items.map((it) => it.dev).filter((v): v is number => v !== null && Number.isFinite(v));
  if (!valid.length) {
    return (
      <div className="num mt-1 text-[11px] text-faint">
        No HRV history yet.
      </div>
    );
  }
  const maxAbs = Math.max(...valid.map((v) => Math.abs(v)), 1);
  const xStep = items.length > 1 ? plotW / (items.length - 1) : 0;
  const barW = Math.max(2, Math.min(10, xStep * 0.5));

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: 480 }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="30-day HRV deviation trend"
      >
        {/* Zero line (plan §4 explicit). */}
        <line
          x1={padLeft}
          y1={midY}
          x2={padLeft + plotW}
          y2={midY}
          stroke="var(--c-hairline-strong)"
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
              stroke="var(--c-text-faint)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <line
              x1={padLeft}
              y1={midY + (hrvSd / maxAbs) * (plotH / 2)}
              x2={padLeft + plotW}
              y2={midY + (hrvSd / maxAbs) * (plotH / 2)}
              stroke="var(--c-text-faint)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          </>
        )}

        {/* Bars — color by hrvDevTone(dev, hrvSd). */}
        {items.map((it, i) => {
          if (it.dev === null || !Number.isFinite(it.dev)) {
            // Missing night — small tick at the zero line.
            const x = padLeft + i * xStep;
            return (
              <line
                key={i}
                x1={x}
                y1={midY - 2}
                x2={x}
                y2={midY + 2}
                stroke="var(--c-hairline2)"
                strokeWidth={1}
              />
            );
          }
          const x = padLeft + i * xStep;
          const h = (Math.abs(it.dev) / maxAbs) * (plotH / 2);
          const y = it.dev >= 0 ? midY - h : midY;
          const tone = hrvDevTone(it.dev, hrvSd);
          return (
            <rect
              key={i}
              x={x - barW / 2}
              y={y}
              width={barW}
              height={h}
              fill={toneToVar(tone)}
              opacity={it.isCurrent ? 1 : 0.7}
              stroke={it.isCurrent ? "var(--c-ink)" : "none"}
              strokeWidth={it.isCurrent ? 1 : 0}
            />
          );
        })}
      </svg>
      <div className="num mt-1 flex items-center justify-between text-[10px] text-faint">
        <span>−{fmtNum(maxAbs, 0)} ms</span>
        <span>0 · baseline</span>
        <span>+{fmtNum(maxAbs, 0)} ms</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- Row 4: In context */
function InContextCard({
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
  const t = useT();
  // Most recent 7 nights (newest-first from API), reverse for left → right.
  const recent = useMemo(() => {
    const arr = listItems.slice(0, 7).reverse();
    return arr;
  }, [listItems]);

  // "What this meant for today" — only render if the selected night is the
  // most recent night AND we have today's readiness/recovery.
  const isMostRecent =
    listItems.length > 0 && listItems[0].local_date === selectedDate;
  const readiness = dashboard?.overview?.readiness?.value ?? null;
  const recovery = dashboard?.overview?.recovery?.value ?? null;
  const showTodayStrip = isMostRecent && (readiness !== null || recovery !== null);

  if (!recent.length) return null;

  // Bar geometry for "previous 7 nights as mini bars with this night
  // highlighted".
  const maxDur = Math.max(
    ...recent
      .map((it) => it.total_sleep_s ?? 0)
      .filter((v) => Number.isFinite(v)),
    1,
  );

  return (
    <Card>
      <CardHeader
        eyebrow={"In context" /* TODO i18n */}
        title={"Last 7 nights" /* TODO i18n */}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Mini bars: previous 7 nights with this night highlighted. */}
        <div className="lg:col-span-2">
          <div className="flex items-end gap-2">
            {recent.map((it) => {
              const dur = it.total_sleep_s ?? 0;
              const hPct = (dur / maxDur) * 100;
              const isCurrent = it.local_date === selectedDate;
              const tone = scoreTone(it.sleep_score);
              return (
                <div
                  key={it.local_date}
                  className="flex flex-1 flex-col items-center gap-1"
                >
                  <div className="num text-[10px] text-faint">
                    {fmtHours(dur)}
                  </div>
                  <div className="flex h-20 w-full items-end justify-center">
                    <div
                      className={`w-full max-w-[28px] rounded-[var(--radius-control)] ${isCurrent ? "ring-1 ring-ink" : ""}`}
                      style={{
                        height: `${Math.max(4, hPct)}%`,
                        background: toneToVar(tone),
                        opacity: isCurrent ? 1 : 0.7,
                      }}
                      title={`${it.local_date}: ${fmtHours(dur)} · score ${fmtNum(it.sleep_score, 0)}`}
                    />
                  </div>
                  <div className="num text-[9px] text-faint">
                    {shortDate(it.local_date)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* "What this meant for today" — today's readiness + recovery with
            link to Overview. */}
        <div className="lg:border-l lg:border-hairline lg:pl-4">
          <Eyebrow>{"What this meant for today" /* TODO i18n */}</Eyebrow>
          {showTodayStrip ? (
            <div className="mt-2 space-y-2">
              <TodayStat
                label={"Readiness" /* TODO i18n */}
                value={readiness}
                tone={scoreTone(readiness)}
              />
              <TodayStat
                label={"Recovery" /* TODO i18n */}
                value={recovery}
                tone={scoreTone(recovery)}
              />
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
            <div className="num mt-1 text-[11px] text-faint">
              {isMostRecent
                ? "Today's readiness and recovery aren't available yet — connect a source or sync to see how last night affected today."
                : "This strip shows today's readiness and recovery only for the most recent night."}
            </div>
          )}
        </div>
      </div>
    </Card>
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
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[12px] text-muted">{label}</span>
      <span className={`num text-[18px] font-bold ${toneTextClass(tone)}`}>
        {value !== null ? fmtNum(value, 0) : "—"}
      </span>
    </div>
  );
}

/* ----------------------------------------------------------- small helpers */
function t_label(k: StageKey): string {
  const en: Record<StageKey, string> = {
    deep: "Deep",
    light: "Light",
    rem: "REM",
    awake: "Awake",
  };
  return en[k];
}

function shortDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}
