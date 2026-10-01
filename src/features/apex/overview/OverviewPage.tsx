"use client";

/**
 * Apex Health — Overview (the reference screen).
 *
 * Implements all 9 design principles from ui-language/RULES.md:
 *   1. One answer: "Good morning, Matteo. You're moderately ready."
 *   2. One hero: the readiness ring, 2× anything else.
 *   3. No outlines: cards by surface contrast, no card-in-card.
 *   4. Sentence-case labels, 14px minimum.
 *   5. Numbers stay white; status = dot + word.
 *   6. Accent (orange) for the hero ring + actions, not for "good".
 *   7. Plain words: "Body signals", "Training load", "Last night".
 *   8. Charts: one line + normal band + latest point.
 *   9. Seven sections maximum.
 *
 * Data: /api/dashboard (scores + sleep + biomarkers + activities + alerts),
 *       /api/gym/plan (today's plan), /api/events (next event),
 *       /api/metrics/load (28-day chart), /api/gear (due for service).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, Info } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me } from "@/lib/apex/data";
import { localToday, dayDiff } from "@/lib/apex/localTime";
import {
  Card,
  Section,
  Hero,
  StatusDot,
  Row,
  PageSentence,
  ChartFrame,
  ScoreBar,
  DeltaChip,
  SportIcon,
  ApexButton,
  Empty,
  Loading,
  Hairline,
  Sparkline,
  scoreTone,
  acwrTone,
  rangeTone,
  hrvDevTone,
} from "@/components/apex/kit";
import { InteractiveComboChart, ChartLegend, ChartInfoBadge } from "@/components/apex/charts";
import {
  fmtNum,
  fmtHours,
  fmtDuration,
  fmtClock,
  fmtDistance,
  fmtDate,
  friendlyDiscipline,
} from "@/lib/apex/format";
import type { ActivityCard } from "@/lib/apex/types";

/* ----------------------------------------------------------- types */

interface OverviewData {
  date: string;
  readiness: { value: number | null; delta_7d: number | null };
  recovery: { value: number | null; delta_7d: number | null };
  strain: { value: number | null; delta_7d: number | null };
  sleep_score: { value: number | null; delta_7d: number | null };
  sleep_hours: number | null;
  hrv_ms: number | null;
  hrv_baseline_ms: number | null;
  hrv_deviation_pct: number | null;
  resting_hr: number | null;
  resting_hr_delta_7d: number | null;
  spo2_avg: number | null;
  respiration_avg: number | null;
  weight_kg: number | null;
  acute_load: number | null;
  chronic_load: number | null;
  acwr: number | null;
  activities: ActivityCard[];
  sleep: {
    start_time: string;
    end_time: string;
    total_sleep_s: number | null;
    sleep_score: number | null;
    stages: { deep_s: number | null; light_s: number | null; rem_s: number | null; awake_s: number | null };
    respiration_avg: number | null;
    spo2_avg: number | null;
    restlessness: number | null;
  } | null;
  alerts: { type: string; severity: "info" | "warning" | "alert"; message: string }[];
}

interface DayLoad {
  date: string;
  load: number;
  acute: number | null;
  chronic: number | null;
  acwr: number | null;
}

interface GearItem {
  id: number;
  name: string;
  gear_type: string;
  usage_pct: number;
  hours_since_service: number;
  service_interval_hours: number | null;
  km_since_service: number;
  service_interval_km: number | null;
}

interface ApexEvent {
  id: number;
  title: string;
  kind: string;
  date: string;
  priority: string;
  taperDays: number | null;
}

interface GymPlanLite {
  id: number;
  title: string;
  status: string;
  adjustmentNote: string | null;
  exercises: unknown[];
}

const RHR_RANGE = { low: 50, high: 70 };
const SPO2_RANGE = { low: 95, high: 100 };
const RESP_RANGE = { low: 12, high: 20 };

/* ----------------------------------------------------------- helpers */

function scoreWord(tone: "positive" | "warning" | "alert" | "muted"): string {
  if (tone === "positive") return "Good";
  if (tone === "warning") return "Watch";
  if (tone === "alert") return "Low";
  return "—";
}

function acwrWord(tone: "positive" | "warning" | "alert" | "muted"): string {
  if (tone === "positive") return "Optimal";
  if (tone === "warning") return "Elevated";
  if (tone === "alert") return "High risk";
  return "—";
}

function fmtHoursFromSecs(s: number | null): string {
  if (s === null) return "—";
  return fmtHours(s);
}

/* ----------------------------------------------------------- page */

export function OverviewPage() {
  const t = useT();
  const ui = useApexUi();

  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [load, setLoad] = useState<DayLoad[] | null>(null);
  const [gearDue, setGearDue] = useState<GearItem[]>([]);
  const [plan, setPlan] = useState<GymPlanLite | null>(null);
  const [events, setEvents] = useState<ApexEvent[]>([]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/dashboard", { cache: "no-store" });
      const j = await r.json();
      if (j?.ok) {
        setData(j.overview as OverviewData);
      } else {
        setError(j?.error || "Failed to load");
      }
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    // Load supporting data in parallel
    (async () => {
      try {
        const [loadR, gearR, planR, eventsR] = await Promise.all([
          fetch("/api/metrics/load?days=28").then((r) => r.json()).catch(() => null),
          fetch("/api/gear").then((r) => r.json()).catch(() => null),
          fetch(`/api/gym/plan?date=${localToday("Europe/Rome")}`).then((r) => r.json()).catch(() => null),
          fetch("/api/events").then((r) => r.json()).catch(() => null),
        ]);
        if (loadR?.ok) setLoad(loadR.series);
        if (gearR?.ok) {
          const due = (gearR.gear as GearItem[])
            .filter((g) => g.usage_pct >= 80)
            .sort((a, b) => b.usage_pct - a.usage_pct)
            .slice(0, 4);
          setGearDue(due);
        }
        if (planR?.ok && planR.plan) {
          setPlan({
            id: planR.plan.id,
            title: planR.plan.title,
            status: planR.plan.status,
            adjustmentNote: planR.plan.adjustmentNote,
            exercises: planR.plan.exercises ?? [],
          });
        }
        if (eventsR?.ok) setEvents(eventsR.events);
      } catch {
        /* ignore */
      }
    })();
  }, [loadAll]);

  // Derive the page sentence (principle 1: one answer)
  const readinessValue = data?.readiness?.value ?? null;
  const readinessTone = scoreTone(readinessValue);
  const pageSentence = useMemo(() => {
    const firstName = me.name.split(" ")[0] || "Matteo";
    const hour = new Date().getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    if (readinessValue === null) return `${greeting}, ${firstName}. Waiting for your first sync.`;
    if (readinessTone === "positive") return `${greeting}, ${firstName}. You're ready. Train hard today.`;
    if (readinessTone === "warning") return `${greeting}, ${firstName}. You're moderately ready. Keep today aerobic.`;
    return `${greeting}, ${firstName}. You're below your baseline. Prioritise recovery today.`;
  }, [readinessValue, readinessTone]);

  const nextEvent = useMemo(() => {
    const today = data?.date ?? localToday("Europe/Rome");
    return events
      .filter((e) => {
        const d = dayDiff(today, e.date);
        return d >= 0 && d <= 14;
      })
      .sort((a, b) => a.date.localeCompare(b.date))[0];
  }, [events, data?.date]);

  if (loading || !data) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <Loading label="Loading your overview…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 py-8">
        <Card>
          <div className="text-[20px] font-medium text-ink">Couldn't load your data</div>
          <p className="mt-2 text-[14px] text-ink2">{error}</p>
          <ApexButton variant="secondary" size="sm" className="mt-4" onClick={loadAll}>
            Try again
          </ApexButton>
        </Card>
      </div>
    );
  }

  const sleepTone = scoreTone(data.sleep_score.value ?? data.sleep?.sleep_score ?? null);
  const acwrT = acwrTone(data.acwr);
  const rhrTone = rangeTone(data.resting_hr, RHR_RANGE.low, RHR_RANGE.high);
  const spo2Tone = rangeTone(data.spo2_avg, SPO2_RANGE.low, SPO2_RANGE.high);
  const respTone = rangeTone(data.respiration_avg, RESP_RANGE.low, RESP_RANGE.high);
  const hrvTone = hrvDevTone(data.hrv_deviation_pct, 8);

  const sleepStages = data.sleep?.stages;
  const deepS = sleepStages?.deep_s ?? 0;
  const remS = sleepStages?.rem_s ?? 0;
  const lightS = sleepStages?.light_s ?? 0;
  const awakeS = sleepStages?.awake_s ?? 0;
  const totalSleepS = deepS + lightS + remS || 1;

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ====== GREETING (principle 1: one answer) ====== */}
      <div>
        <h1 className="page-title">Overview</h1>
        <PageSentence className="mt-2">{pageSentence}</PageSentence>
      </div>

      {/* ====== HERO — Readiness ring (principle 2: one hero, 2× anything) ====== */}
      <Card>
        <div className="flex flex-col gap-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-8">
            {/* Readiness ring — the hero */}
            <ReadinessRing value={readinessValue} tone={readinessTone} />
            <div>
              <div className="text-[14px] font-medium text-ink2">Readiness</div>
              <div className="mt-1 flex items-center gap-3">
                <StatusDot tone={readinessTone === "positive" ? "ok" : readinessTone === "warning" ? "watch" : readinessTone === "alert" ? "alert" : "neutral"} label={scoreWord(readinessTone)} />
                {data.readiness.delta_7d !== null && (
                  <DeltaChip delta={data.readiness.delta_7d} goodWhen="up" suffix="vs 7d" />
                )}
              </div>
              <div className="mt-2 text-[14px] text-ink2">
                {readinessTone === "positive" && "Your body is handling load well. A hard session is in range."}
                {readinessTone === "warning" && "Recovery is partial. Keep the session aerobic or skill-focused."}
                {readinessTone === "alert" && "You're below your baseline. Prioritise sleep and easy movement."}
                {readinessTone === "muted" && "Sync your devices to see your readiness score."}
              </div>
            </div>
          </div>

          {/* Recovery + Strain as small rings */}
          <div className="flex gap-6 sm:gap-8">
            <MiniRing label="Recovery" value={data.recovery.value} tone={scoreTone(data.recovery.value)} />
            <MiniRing label="Strain" value={data.strain.value} tone="neutral" neutral />
          </div>
        </div>

        {/* What's driving it (principle 1: the answer + the why) */}
        {readinessValue !== null && (
          <div className="mt-8">
            <div className="mb-3 text-[14px] font-medium text-ink2">What's driving it</div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Driver
                label="Sleep"
                value={data.sleep_score.value !== null ? `${Math.round(data.sleep_score.value)}` : "—"}
                unit="/100"
                tone={sleepTone}
              />
              <Driver
                label="HRV"
                value={data.hrv_ms !== null ? `${Math.round(data.hrv_ms)}` : "—"}
                unit="ms"
                tone={hrvTone}
              />
              <Driver
                label="Resting HR"
                value={data.resting_hr !== null ? `${data.resting_hr}` : "—"}
                unit="bpm"
                tone={rhrTone}
              />
              <Driver
                label="Load"
                value={data.acwr !== null ? `${data.acwr.toFixed(2)}` : "—"}
                unit="ACWR"
                tone={acwrT}
              />
            </div>
          </div>
        )}
      </Card>

      {/* ====== 3 FACTS (principle: slim row of 3 facts, always right under hero) ====== */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        {/* Today's plan */}
        <Card>
          <div className="text-[14px] font-medium text-ink2">Today's plan</div>
          {plan ? (
            <div className="mt-3">
              <div className="text-[20px] font-semibold text-ink">{plan.title}</div>
              <div className="mt-1 text-[14px] text-ink2">
                {plan.status === "confirmed" ? "Confirmed" : "Draft"} · {plan.exercises.length} exercises
              </div>
              {plan.adjustmentNote && (
                <div className="mt-2 text-[13px] text-ink2">{plan.adjustmentNote}</div>
              )}
              <ApexButton
                variant="ghost"
                size="sm"
                className="mt-3"
                iconRight={<ChevronRight size={12} />}
                onClick={() => ui.setView("training")}
              >
                Open training
              </ApexButton>
            </div>
          ) : (
            <div className="mt-3">
              <div className="text-[16px] text-ink2">Rest day</div>
              <ApexButton
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => ui.setView("training")}
              >
                Generate a plan
              </ApexButton>
            </div>
          )}
        </Card>

        {/* Next event */}
        <Card>
          <div className="text-[14px] font-medium text-ink2">Next event</div>
          {nextEvent ? (
            <div className="mt-3">
              <div className="text-[20px] font-semibold text-ink">{nextEvent.title}</div>
              <div className="mt-1 text-[14px] text-ink2">
                {fmtDate(nextEvent.date, ui.locale)} · in {dayDiff(data.date, nextEvent.date)} days
              </div>
              {nextEvent.taperDays && nextEvent.taperDays > 0 && (
                <div className="mt-2">
                  <StatusDot tone="watch" label={`Taper · ${nextEvent.taperDays} days`} />
                </div>
              )}
            </div>
          ) : (
            <div className="mt-3 text-[16px] text-ink2">No events in the next 14 days</div>
          )}
        </Card>

        {/* Gear due */}
        <Card>
          <div className="text-[14px] font-medium text-ink2">Gear due for service</div>
          {gearDue.length > 0 ? (
            <div className="mt-3 space-y-2">
              {gearDue.slice(0, 2).map((g) => (
                <div key={g.id} className="flex items-center justify-between gap-2">
                  <span className="truncate text-[14px] text-ink">{g.name}</span>
                  <StatusDot
                    tone={g.usage_pct >= 100 ? "alert" : "watch"}
                    label={`${Math.round(g.usage_pct)}%`}
                  />
                </div>
              ))}
              <ApexButton
                variant="ghost"
                size="sm"
                className="mt-1"
                iconRight={<ChevronRight size={12} />}
                onClick={() => ui.setView("gear")}
              >
                View all gear
              </ApexButton>
            </div>
          ) : (
            <div className="mt-3 text-[16px] text-ink2">Nothing due soon</div>
          )}
        </Card>
      </div>

      {/* ====== TRAINING LOAD (principle 8: one line + normal band) ====== */}
      <Card>
        <Section label="Training load">
          <div className="flex items-baseline justify-between">
            <div className="flex items-baseline gap-6">
              <div>
                <div className="num text-[40px] font-semibold leading-none text-ink">
                  {data.acwr !== null ? data.acwr.toFixed(2) : "—"}
                </div>
                <div className="mt-1 text-[14px] text-ink2">ACWR</div>
              </div>
              <div>
                <StatusDot
                  tone={acwrT === "positive" ? "ok" : acwrT === "warning" ? "watch" : acwrT === "alert" ? "alert" : "neutral"}
                  label={acwrWord(acwrT)}
                />
                <div className="mt-1 text-[14px] text-ink2">
                  Acute {fmtNum(data.acute_load, 0)} · Chronic {fmtNum(data.chronic_load, 0)}
                </div>
              </div>
            </div>
            <ChartInfoBadge
              text={
                <span>
                  <strong className="text-ink2">Acute load</strong> = 7-day training load (fatigue).{" "}
                  <strong className="text-ink2">Chronic load</strong> = 28-day average (fitness base).{" "}
                  <strong className="text-ink2">ACWR</strong> = acute ÷ chronic. 0.8–1.3 optimal; above 1.5 high injury-risk.
                </span>
              }
            />
          </div>

          {load && load.length > 0 ? (
            <div className="mt-6">
              <InteractiveComboChart
                categories={load.map((d) => ({ label: d.date.slice(5) }))}
                bars={{
                  name: "Acute (7d)",
                  color: "var(--c-accent)",
                  values: load.map((d) => d.acute ?? 0),
                }}
                lines={[
                  {
                    name: "Chronic (28d)",
                    color: "var(--c-text-3)",
                    values: load.map((d) => d.chronic ?? 0),
                  },
                ]}
                height={140}
                formatBarValue={(v) => (v === null ? "—" : `${Math.round(v)} TSS`)}
                formatLineValue={(v) => (v === null ? "—" : `${Math.round(v)} TSS`)}
              />
              <ChartLegend
                className="mt-3"
                items={[
                  { name: "Acute load (7-day fatigue)", color: "var(--c-accent)" },
                  { name: "Chronic load (28-day base)", color: "var(--c-text-3)" },
                ]}
              />
            </div>
          ) : (
            <div className="mt-6 text-[14px] text-ink2">
              No load history yet. Sync your devices to populate the chart.
            </div>
          )}
        </Section>
      </Card>

      {/* ====== BODY SIGNALS (principle 9: rows, not cards) ====== */}
      <Card>
        <Section label="Body signals">
          <div className="divide-y divide-[var(--c-divider)]">
            <Row
              label="Resting heart rate"
              value={data.resting_hr !== null ? data.resting_hr : "—"}
              unit="bpm"
              status={
                <StatusDot
                  tone={rhrTone === "positive" ? "ok" : rhrTone === "warning" ? "watch" : rhrTone === "alert" ? "alert" : "neutral"}
                  label={rhrTone === "positive" ? "In range" : rhrTone === "warning" ? "Borderline" : rhrTone === "alert" ? "Out of range" : "—"}
                />
              }
              spark={
                data.resting_hr_delta_7d !== null ? (
                  <DeltaChip delta={data.resting_hr_delta_7d} goodWhen="down" compact />
                ) : null
              }
              onClick={() => { ui.selectMetric("resting_hr"); ui.setView("metric"); }}
            />
            <Row
              label="SpO₂"
              value={data.spo2_avg !== null ? data.spo2_avg.toFixed(1) : "—"}
              unit="%"
              status={
                <StatusDot
                  tone={spo2Tone === "positive" ? "ok" : spo2Tone === "warning" ? "watch" : spo2Tone === "alert" ? "alert" : "neutral"}
                  label={spo2Tone === "positive" ? "In range" : spo2Tone === "warning" ? "Borderline" : spo2Tone === "alert" ? "Low" : "—"}
                />
              }
              onClick={() => { ui.selectMetric("spo2_avg"); ui.setView("metric"); }}
            />
            <Row
              label="Respiration"
              value={data.respiration_avg !== null ? data.respiration_avg.toFixed(1) : "—"}
              unit="brpm"
              status={
                <StatusDot
                  tone={respTone === "positive" ? "ok" : respTone === "warning" ? "watch" : respTone === "alert" ? "alert" : "neutral"}
                  label={respTone === "positive" ? "In range" : respTone === "warning" ? "Borderline" : respTone === "alert" ? "Out of range" : "—"}
                />
              }
              onClick={() => { ui.selectMetric("respiration_avg"); ui.setView("metric"); }}
            />
            <Row
              label="HRV"
              value={data.hrv_ms !== null ? Math.round(data.hrv_ms) : "—"}
              unit="ms"
              status={
                <StatusDot
                  tone={hrvTone === "positive" ? "ok" : hrvTone === "warning" ? "watch" : hrvTone === "alert" ? "alert" : "neutral"}
                  label={hrvTone === "positive" ? "On baseline" : hrvTone === "warning" ? "Slightly off" : hrvTone === "alert" ? "Below baseline" : "—"}
                />
              }
              onClick={() => { ui.selectMetric("hrv_ms"); ui.setView("metric"); }}
            />
            <Row
              label="Weight"
              value={data.weight_kg !== null ? data.weight_kg.toFixed(1) : "—"}
              unit="kg"
              onClick={() => { ui.selectMetric("weight_kg"); ui.setView("metric"); }}
            />
          </div>
        </Section>
      </Card>

      {/* ====== LAST NIGHT (compact: one stage bar + 5 numbers) ====== */}
      {data.sleep && (
        <Card>
          <Section label="Last night">
            <div className="flex items-baseline justify-between">
              <div className="flex items-baseline gap-6">
                <div>
                  <div className="num text-[40px] font-semibold leading-none text-ink">
                    {data.sleep_score.value !== null ? Math.round(data.sleep_score.value) : (data.sleep.sleep_score ?? "—")}
                  </div>
                  <div className="mt-1 text-[14px] text-ink2">Sleep score</div>
                </div>
                <div>
                  <StatusDot
                    tone={sleepTone === "positive" ? "ok" : sleepTone === "warning" ? "watch" : sleepTone === "alert" ? "alert" : "neutral"}
                    label={scoreWord(sleepTone)}
                  />
                  {data.sleep_score.delta_7d !== null && (
                    <div className="mt-1">
                      <DeltaChip delta={data.sleep_score.delta_7d} goodWhen="up" compact />
                    </div>
                  )}
                </div>
              </div>
              <ApexButton
                variant="ghost"
                size="sm"
                iconRight={<ChevronRight size={12} />}
                onClick={() => { ui.selectSleepDate(data.date); ui.setView("sleep-night"); }}
              >
                Open night
              </ApexButton>
            </div>

            {/* Stage bar — one horizontal bar, honest */}
            <div className="mt-6">
              <div className="flex h-3 overflow-hidden rounded-full bg-surface2">
                {[
                  { v: deepS, color: "var(--c-stage-deep)" },
                  { v: remS, color: "var(--c-stage-rem)" },
                  { v: lightS, color: "var(--c-stage-core)" },
                ].map((s, i) => (
                  <div key={i} style={{ width: `${(s.v / totalSleepS) * 100}%`, background: s.color }} />
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
                <span className="flex items-center gap-1.5 text-ink2">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--c-stage-deep)" }} />
                  Deep {fmtHoursFromSecs(deepS)} · {Math.round((deepS / totalSleepS) * 100)}%
                </span>
                <span className="flex items-center gap-1.5 text-ink2">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--c-stage-rem)" }} />
                  REM {fmtHoursFromSecs(remS)} · {Math.round((remS / totalSleepS) * 100)}%
                </span>
                <span className="flex items-center gap-1.5 text-ink2">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--c-stage-core)" }} />
                  Light {fmtHoursFromSecs(lightS)} · {Math.round((lightS / totalSleepS) * 100)}%
                </span>
                <span className="flex items-center gap-1.5 text-ink2">
                  <span className="h-2 w-2 rounded-full" style={{ background: "var(--c-stage-awake)" }} />
                  Awake {fmtHoursFromSecs(awakeS)}
                </span>
              </div>
            </div>

            {/* 5 numbers */}
            <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-5">
              <Fact label="Total" value={fmtHoursFromSecs(data.sleep.total_sleep_s)} />
              <Fact label="Window" value={fmtHoursFromSecs(data.sleep.end_time && data.sleep.start_time ? (new Date(data.sleep.end_time).getTime() - new Date(data.sleep.start_time).getTime()) / 1000 : 0)} />
              <Fact label="Bedtime" value={fmtClock(data.sleep.start_time, ui.locale)} />
              <Fact label="Wake" value={fmtClock(data.sleep.end_time, ui.locale)} />
              <Fact label="Efficiency" value={data.sleep.total_sleep_s && data.sleep.end_time ? `${Math.round((data.sleep.total_sleep_s / ((new Date(data.sleep.end_time).getTime() - new Date(data.sleep.start_time).getTime()) / 1000)) * 100)}%` : "—"} />
            </div>
          </Section>
        </Card>
      )}

      {/* ====== TODAY'S ACTIVITIES (list, not cards) ====== */}
      {data.activities.length > 0 && (
        <Card>
          <Section label="Today's activities">
            <div className="space-y-3">
              {data.activities.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => { ui.selectActivity(a.id); ui.setView("activity-detail"); }}
                  className="flex w-full items-center gap-4 py-2 text-left transition-colors hover:bg-surface2 rounded-[var(--radius-control)] px-2 -mx-2"
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface2 text-ink2">
                    <SportIcon discipline={a.discipline} size={18} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[16px] font-medium text-ink">{a.title}</div>
                    <div className="text-[13px] text-ink2">
                      {friendlyDiscipline(a.discipline, ui.locale)} · {fmtClock(a.start_time, ui.locale)} · {fmtDuration(a.duration_s)}
                    </div>
                  </div>
                  <div className="num text-[14px] text-ink2">
                    {a.distance_m !== null ? fmtDistance(a.distance_m, "metric", 1) : ""}
                    {a.avg_hr !== null ? ` · ${a.avg_hr} bpm` : ""}
                  </div>
                  <ChevronRight size={14} className="shrink-0 text-ink3" />
                </button>
              ))}
            </div>
          </Section>
        </Card>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- sub-components */

/** Readiness ring — the hero. 120px SVG ring, 72px number inside. */
function ReadinessRing({ value, tone }: { value: number | null; tone: "positive" | "warning" | "alert" | "muted" }) {
  const v = value ?? 0;
  const r = 54;
  const c = 2 * Math.PI * r;
  const color = tone === "positive" ? "var(--c-ok)" : tone === "warning" ? "var(--c-watch)" : tone === "alert" ? "var(--c-alert)" : "var(--c-text-3)";
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

/** Mini ring for Recovery + Strain (smaller, under the hero). */
function MiniRing({
  label,
  value,
  tone,
  neutral = false,
}: {
  label: string;
  value: number | null;
  tone: "positive" | "warning" | "alert" | "muted";
  neutral?: boolean;
}) {
  const v = value ?? 0;
  const r = 34;
  const c = 2 * Math.PI * r;
  const color = neutral ? "var(--c-text-3)" : tone === "positive" ? "var(--c-ok)" : tone === "warning" ? "var(--c-watch)" : tone === "alert" ? "var(--c-alert)" : "var(--c-text-3)";
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-[80px] w-[80px]">
        <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
          <circle cx="40" cy="40" r={r} fill="none" stroke="var(--c-surface-2)" strokeWidth="5" />
          <circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - v / 100)}
            style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0.16,1,0.3,1)" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="num text-[20px] font-semibold text-ink">
            {value !== null ? Math.round(value) : "—"}
          </span>
        </div>
      </div>
      <span className="text-[14px] text-ink2">{label}</span>
    </div>
  );
}

/** Driver — a small stat in the "What's driving it" grid. */
function Driver({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  tone: "positive" | "warning" | "alert" | "muted";
}) {
  return (
    <div>
      <div className="text-[14px] text-ink2">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="num text-[24px] font-semibold text-ink">{value}</span>
        <span className="text-[13px] text-ink2">{unit}</span>
      </div>
      <div className="mt-1">
        <StatusDot
          tone={tone === "positive" ? "ok" : tone === "warning" ? "watch" : tone === "alert" ? "alert" : "neutral"}
          label={tone === "positive" ? "Good" : tone === "warning" ? "Watch" : tone === "alert" ? "Low" : "—"}
        />
      </div>
    </div>
  );
}

/** Fact — a label + value in the sleep 5-numbers row. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[13px] text-ink2">{label}</div>
      <div className="num mt-0.5 text-[20px] font-semibold text-ink">{value}</div>
    </div>
  );
}
