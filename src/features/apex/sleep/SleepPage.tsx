"use client";

/**
 * Apex Health — Sleep list page.
 *
 * Route purpose: "How have I been sleeping?"
 * A clean, dense historical view of sleep sessions. Each row is a clickable
 * card that navigates to the night detail (hypnogram) view.
 *
 * Layout:
 *   PageHeader — title "Sleep" + 28-day trend summary card (avg score, avg
 *   total, vs 28d delta) on the right.
 *   Below — a vertical list of session rows. Each row shows date (mono),
 *   sleep score (large, tone-coloured), total sleep, 4 stage mini-bars,
 *   bedtime → wake, respiration, SpO₂, restlessness, source pills.
 *
 * Coherence law: only composes shared kit; no custom card variants.
 */

import { useMemo } from "react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { sleepSessions } from "@/lib/apex/data";
import {
  Card,
  PageHeader,
  BigStat,
  DeltaChip,
  Eyebrow,
  SourcePill,
} from "@/components/apex/kit";
import { fmtDateLong, fmtHours, fmtClock, fmtNum } from "@/lib/apex/format";

type SleepSession = (typeof sleepSessions)[number];

/** Stage CSS variable — Awake=alert, REM=blue, Light=core (N1+N2), Deep=indigo. */
const STAGE_VARS = {
  deep: "var(--c-stage-deep)",
  rem: "var(--c-stage-rem)",
  light: "var(--c-stage-core)",
  awake: "var(--c-stage-awake)",
} as const;

/** Tone for a sleep score: 85+ positive, 70+ primary, 50+ warning, else alert. */
function scoreTone(score: number | null): "positive" | "primary" | "warning" | "alert" {
  if (score === null) return "warning";
  if (score >= 85) return "positive";
  if (score >= 70) return "primary";
  if (score >= 50) return "warning";
  return "alert";
}

export function SleepPage() {
  const t = useT();
  const ui = useApexUi();

  // 28-day trend summary + delta of most recent night vs 28-day average.
  const trend = useMemo(() => {
    const last28 = sleepSessions.slice(0, 28);
    const valid = last28.filter(
      (s) => s.sleep_score !== null && s.total_sleep_s !== null,
    );
    const avgScore =
      valid.reduce((s, x) => s + (x.sleep_score ?? 0), 0) / (valid.length || 1);
    const avgTotal =
      valid.reduce((s, x) => s + (x.total_sleep_s ?? 0), 0) / (valid.length || 1);
    const latest = sleepSessions[0];
    const deltaScore =
      latest && latest.sleep_score !== null ? latest.sleep_score - avgScore : null;
    const deltaTotalMin =
      latest && latest.total_sleep_s !== null
        ? Math.round(((latest.total_sleep_s ?? 0) - avgTotal) / 60)
        : null;
    return { avgScore, avgTotal, deltaScore, deltaTotalMin };
  }, []);

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader
        title={t("sleep.title")}
        subtitle={t("sleep.trend_28d")}
        actions={<TrendCard trend={trend} />}
      />

      <div className="mt-6 space-y-2">
        {sleepSessions.map((s) => (
          <SleepRow key={s.local_date} session={s} />
        ))}
      </div>
    </div>
  );
}

/** Compact summary card — sits in the PageHeader actions slot. */
function TrendCard({
  trend,
}: {
  trend: {
    avgScore: number;
    avgTotal: number;
    deltaScore: number | null;
    deltaTotalMin: number | null;
  };
}) {
  const t = useT();
  return (
    <Card pad={false} className="px-4 py-3">
      <div className="flex items-stretch gap-5">
        <div className="flex flex-col">
          <Eyebrow>{t("sleep.avg_score")}</Eyebrow>
          <div className="num mt-1 flex items-baseline gap-1.5">
            <span className="text-[22px] font-bold leading-7 text-ink">
              {fmtNum(trend.avgScore, 0)}
            </span>
            <span className="text-[10px] font-medium text-muted">/100</span>
          </div>
          <div className="mt-1.5">
            <DeltaChip
              delta={trend.deltaScore}
              goodWhen="up"
              suffix={t("sleep.vs_28d")}
            />
          </div>
        </div>
        <div className="w-px self-stretch bg-hairline" />
        <div className="flex flex-col">
          <Eyebrow>{t("sleep.avg_total")}</Eyebrow>
          <div className="num mt-1 text-[22px] font-bold leading-7 text-ink">
            {fmtHours(trend.avgTotal)}
          </div>
          <div className="mt-1.5">
            <DeltaChip
              delta={trend.deltaTotalMin}
              unit="min"
              goodWhen="up"
              suffix={t("sleep.vs_28d")}
            />
          </div>
        </div>
      </div>
    </Card>
  );
}

/** One historical sleep session — clickable row. */
function SleepRow({ session: s }: { session: SleepSession }) {
  const t = useT();
  const ui = useApexUi();

  const stages = [
    { key: "deep", label: t("sleep.deep"), seconds: s.deep_s, color: STAGE_VARS.deep },
    { key: "rem", label: t("sleep.rem"), seconds: s.rem_s, color: STAGE_VARS.rem },
    { key: "light", label: t("sleep.light"), seconds: s.light_s, color: STAGE_VARS.light },
    { key: "awake", label: t("sleep.awake"), seconds: s.awake_s, color: STAGE_VARS.awake },
  ] as const;
  const totalStage = stages.reduce((sum, st) => sum + (st.seconds ?? 0), 0) || 1;

  return (
    <Card
      pad={false}
      onClick={() => {
        ui.selectSleepDate(s.local_date);
        ui.setView("sleep-night");
      }}
      className="cursor-pointer px-4 py-3 transition-colors hover:border-hairline2 hover:bg-surface2/40"
    >
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 md:grid-cols-12 md:items-center">
        {/* Date + bedtime → wake */}
        <div className="col-span-2 md:col-span-2">
          <div className="mono text-[12.5px] font-semibold leading-5 text-ink">
            {fmtDateLong(s.local_date, ui.locale)}
          </div>
          <div className="num mono mt-1 text-[11px] text-muted">
            {fmtClock(s.start_time, ui.locale)} → {fmtClock(s.end_time, ui.locale)}
          </div>
        </div>

        {/* Sleep Score */}
        <div className="md:col-span-2">
          <Eyebrow>{t("sleep.score")}</Eyebrow>
          <BigStat
            value={fmtNum(s.sleep_score, 0)}
            size="lg"
            tone={scoreTone(s.sleep_score)}
            className="mt-0.5"
          />
        </div>

        {/* Total sleep + stage mini-bars */}
        <div className="col-span-2 md:col-span-3">
          <Eyebrow>{t("sleep.total")}</Eyebrow>
          <BigStat value={fmtHours(s.total_sleep_s)} size="md" className="mt-0.5" />
          <div className="mt-2 space-y-1">
            {stages.map((st) => {
              const pct = ((st.seconds ?? 0) / totalStage) * 100;
              return (
                <div key={st.key} className="flex items-center gap-2">
                  <span className="num w-10 shrink-0 text-[10px] uppercase tracking-[0.06em] text-faint">
                    {st.label}
                  </span>
                  <div className="num h-1.5 flex-1 overflow-hidden rounded-[var(--radius-control)] bg-surface3">
                    <div
                      style={{
                        width: `${pct}%`,
                        height: "100%",
                        background: st.color,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Biometrics: respiration, SpO₂, restlessness */}
        <div className="col-span-2 grid grid-cols-3 gap-3 md:col-span-3">
          <MiniStat
            label={t("sleep.respiration")}
            value={fmtNum(s.respiration_avg, 1)}
            unit="brpm"
          />
          <MiniStat
            label={t("sleep.spo2")}
            value={fmtNum(s.spo2_avg, 1)}
            unit="%"
          />
          <MiniStat
            label={t("sleep.restlessness")}
            value={fmtNum(s.restlessness, 0)}
            unit="%"
          />
        </div>

        {/* Source pills */}
        <div className="col-span-2 flex flex-wrap gap-1 md:col-span-2 md:justify-end">
          {s.sources.map((src) => (
            <SourcePill key={src}>{src}</SourcePill>
          ))}
        </div>
      </div>
    </Card>
  );
}

function MiniStat({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div>
      <Eyebrow>{label}</Eyebrow>
      <div className="num mt-0.5 flex items-baseline gap-1 text-[15px] font-bold leading-6 text-ink2">
        {value}
        <span className="text-[10px] font-medium text-muted">{unit}</span>
      </div>
    </div>
  );
}
