"use client";

/**
 * Apex Health — Sleep night detail page (hypnogram + overnight HRV).
 *
 * Route purpose: "What happened during this night?"
 *
 * Composition:
 *   BackLink → "Back to sleep"
 *   PageHeader — date (fmtDateLong) + sleep score BigStat (tone colour)
 *   Hero row — Sleep Score | Total Sleep | Efficiency (BigStat + DeltaChip vs 28d avg)
 *   Hypnogram — full-width SVG; segments at the right stage level (Deep=bottom,
 *     REM, Light, Awake=top), Y-axis labels on the left, X-axis time scale at
 *     the bottom (bedtime → wake, mono labels every ~2h).
 *   Stage totals — 4 StatPods (Deep / REM / Light / Awake) with stage colour dot
 *     and hours.
 *   Overnight HRV Trajectory — full-width SVG line chart of hrv_readings[].hrv_ms
 *     with rolling_baseline_ms as a dashed reference line. Legend: Peak (max),
 *     Baseline (rolling).
 *   Biometrics row — 4 StatPods: Resting HR / SpO₂ / Respiration / Skin Temp.
 *   Source pills + "Source" label.
 */

import { useMemo } from "react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { sleepSessions, getSleepDay } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  StatPod,
  DeltaChip,
  Eyebrow,
  SectionHeader,
  Empty,
  SourcePill,
  BackLink,
} from "@/components/apex/kit";
import { fmtDateLong, fmtHours, fmtClock, fmtNum } from "@/lib/apex/format";

type SleepDay = ReturnType<typeof getSleepDay>;
type HrvReading = SleepDay["hrv_readings"][number];
type StageSeg = NonNullable<SleepDay["stages"]>["segments"][number];

const STAGE_VARS = {
  deep: "var(--c-stage-deep)",
  rem: "var(--c-stage-rem)",
  light: "var(--c-stage-core)",
  awake: "var(--c-stage-awake)",
} as const;

function scoreTone(score: number | null): "positive" | "primary" | "warning" | "alert" {
  if (score === null) return "warning";
  if (score >= 85) return "positive";
  if (score >= 70) return "primary";
  if (score >= 50) return "warning";
  return "alert";
}

export function SleepNightPage() {
  const t = useT();
  const ui = useApexUi();

  const sessionDate = ui.selectedSleepDate ?? sleepSessions[0].local_date;
  const sleepDay = useMemo(() => getSleepDay(sessionDate), [sessionDate]);
  const session = sleepDay.session;

  // 28-day averages for delta chips
  const baseline = useMemo(() => {
    const last28 = sleepSessions.slice(0, 28);
    const valid = last28.filter((s) => s.sleep_score !== null && s.total_sleep_s !== null);
    const avgScore = valid.reduce((s, x) => s + (x.sleep_score ?? 0), 0) / (valid.length || 1);
    const avgTotal = valid.reduce((s, x) => s + (x.total_sleep_s ?? 0), 0) / (valid.length || 1);
    const avgEff = valid.reduce((s, x) => {
      const dur = (new Date(x.end_time).getTime() - new Date(x.start_time).getTime()) / 1000;
      const eff = dur > 0 ? ((x.total_sleep_s ?? 0) / dur) * 100 : 0;
      return s + eff;
    }, 0) / (valid.length || 1);
    return { avgScore, avgTotal, avgEff };
  }, []);

  if (!session) {
    return (
      <div className="mx-auto max-w-[1240px]">
        <BackLink onClick={() => ui.setView("sleep")}>{t("sleep.back_to_list")}</BackLink>
        <Empty title={t("sleep.empty")} className="mt-6" />
      </div>
    );
  }

  const score = session.sleep_score;
  const totalSleep = session.total_sleep_s ?? 0;
  const durationS =
    (new Date(session.end_time).getTime() - new Date(session.start_time).getTime()) / 1000;
  const efficiency = durationS > 0 ? (totalSleep / durationS) * 100 : 0;

  const deltaScore = score !== null ? score - baseline.avgScore : null;
  const deltaTotalMin = Math.round((totalSleep - baseline.avgTotal) / 60);
  const deltaEff = efficiency - baseline.avgEff;

  const stages = [
    { key: "deep", label: t("sleep.deep"), seconds: session.deep_s, color: STAGE_VARS.deep },
    { key: "rem", label: t("sleep.rem"), seconds: session.rem_s, color: STAGE_VARS.rem },
    { key: "light", label: t("sleep.light"), seconds: session.light_s, color: STAGE_VARS.light },
    { key: "awake", label: t("sleep.awake"), seconds: session.awake_s, color: STAGE_VARS.awake },
  ] as const;

  const bio = sleepDay.biometrics;

  return (
    <div className="mx-auto max-w-[1240px]">
      <BackLink onClick={() => ui.setView("sleep")}>{t("sleep.back_to_list")}</BackLink>

      <PageHeader
        className="mt-3"
        title={fmtDateLong(session.local_date, ui.locale)}
        subtitle={t("sleep.night")}
        actions={
          <div className="flex flex-col items-end gap-0.5">
            <Eyebrow>{t("sleep.score")}</Eyebrow>
            <BigStat
              value={fmtNum(score, 0)}
              size="xl"
              tone={scoreTone(score)}
            />
          </div>
        }
      />

      {/* Hero row: Sleep Score | Total Sleep | Efficiency — each with delta vs 28d */}
      <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card>
          <Eyebrow>{t("sleep.score")}</Eyebrow>
          <BigStat
            value={fmtNum(score, 0)}
            size="lg"
            tone={scoreTone(score)}
            className="mt-1"
          />
          <div className="mt-2 flex items-center gap-2">
            <DeltaChip delta={deltaScore} goodWhen="up" suffix={t("sleep.vs_28d")} />
            <span className="num text-[11px] text-faint">
              {t("sleep.vs_28d")}: {fmtNum(baseline.avgScore, 0)}
            </span>
          </div>
        </Card>
        <Card>
          <Eyebrow>{t("sleep.total")}</Eyebrow>
          <BigStat value={fmtHours(totalSleep)} size="lg" className="mt-1" />
          <div className="mt-2 flex items-center gap-2">
            <DeltaChip
              delta={deltaTotalMin}
              unit="min"
              goodWhen="up"
              suffix={t("sleep.vs_28d")}
            />
            <span className="num text-[11px] text-faint">
              {t("sleep.vs_28d")}: {fmtHours(baseline.avgTotal)}
            </span>
          </div>
        </Card>
        <Card>
          <Eyebrow>{t("sleep.efficiency")}</Eyebrow>
          <BigStat value={fmtNum(efficiency, 0)} unit="%" size="lg" className="mt-1" />
          <div className="mt-2 flex items-center gap-2">
            <DeltaChip
              delta={deltaEff}
              unit="%"
              goodWhen="up"
              suffix={t("sleep.vs_28d")}
            />
            <span className="num text-[11px] text-faint">
              {t("sleep.vs_28d")}: {fmtNum(baseline.avgEff, 0)}%
            </span>
          </div>
        </Card>
      </div>

      {/* Hypnogram */}
      <Card className="mt-4">
        <CardHeader eyebrow={t("sleep.night")} title={t("sleep.stages_chart")} />
        <Hypnogram
          segments={sleepDay.stages?.segments ?? []}
          start={session.start_time}
          end={session.end_time}
          locale={ui.locale}
        />
      </Card>

      {/* Stage totals — 4 StatPods with stage colour dot + hours */}
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {stages.map((st) => (
          <StatPod
            key={st.key}
            label={st.label}
            value={fmtHours(st.seconds)}
            right={
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: st.color }}
                aria-hidden
              />
            }
          />
        ))}
      </div>

      {/* Overnight HRV Trajectory */}
      <Card className="mt-4">
        <CardHeader eyebrow={t("sleep.hrv")} title={t("sleep.overnight_hrv")} />
        <HrvTrajectory readings={sleepDay.hrv_readings} locale={ui.locale} />
      </Card>

      {/* Biometrics row */}
      <SectionHeader
        eyebrow={t("sleep.night")}
        title={t("sleep.resting_hr")}
        className="mt-6"
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatPod
          label={t("sleep.resting_hr")}
          value={fmtNum(bio.resting_hr, 0)}
          unit="bpm"
        />
        <StatPod
          label={t("sleep.spo2")}
          value={fmtNum(bio.spo2_avg, 1)}
          unit="%"
        />
        <StatPod
          label={t("sleep.respiration")}
          value={fmtNum(bio.respiration_avg, 1)}
          unit="brpm"
        />
        <StatPod
          label={t("sleep.skin_temp")}
          value={fmtNum(bio.skin_temp_c, 1)}
          unit="°C"
        />
      </div>

      {/* Source pills + label */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Eyebrow>{t("sleep.source")}</Eyebrow>
        {session.sources.map((src) => (
          <SourcePill key={src}>{src}</SourcePill>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- Hypnogram */

const STAGE_ORDER = ["awake", "light", "rem", "deep"] as const;

function Hypnogram({
  segments,
  start,
  end,
  locale,
}: {
  segments: StageSeg[];
  start: string;
  end: string;
  locale: "en" | "it";
}) {
  const t = useT();
  const stageLabels: Record<(typeof STAGE_ORDER)[number], string> = {
    awake: t("sleep.awake"),
    light: t("sleep.light"),
    rem: t("sleep.rem"),
    deep: t("sleep.deep"),
  };

  const W = 1000;
  const H = 240;
  const padLeft = 56;
  const padRight = 18;
  const padTop = 14;
  const padBottom = 28;
  const plotW = W - padLeft - padRight;
  const plotH = H - padTop - padBottom;
  const rowH = plotH / 4;

  const startMs = new Date(start).getTime();
  const endMs = new Date(end).getTime();
  const totalMs = Math.max(endMs - startMs, 1);

  // X-axis time marks every ~2h
  const twoH = 2 * 3600 * 1000;
  const xMarks: { x: number; label: string; align: "start" | "middle" | "end" }[] = [];
  for (let ms = 0; ms <= totalMs + 1; ms += twoH) {
    const ts = startMs + Math.min(ms, totalMs);
    const x = padLeft + (Math.min(ms, totalMs) / totalMs) * plotW;
    const label = new Date(ts).toLocaleTimeString(
      locale === "it" ? "it-IT" : "en-GB",
      { hour: "2-digit", minute: "2-digit", hour12: false },
    );
    const align =
      ms === 0 ? "start" : ms >= totalMs ? "end" : "middle";
    xMarks.push({ x, label, align });
  }

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ minWidth: 600 }}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={t("sleep.stages_chart")}
      >
        {/* Y-axis: row separators + stage labels */}
        {STAGE_ORDER.map((stg, i) => {
          const yMid = padTop + i * rowH + rowH / 2;
          return (
            <g key={stg}>
              <line
                x1={padLeft}
                y1={yMid}
                x2={padLeft + plotW}
                y2={yMid}
                stroke="var(--c-hairline)"
                strokeDasharray="2 4"
                strokeWidth={1}
              />
              <text
                x={padLeft - 10}
                y={yMid + 4}
                textAnchor="end"
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  fill: "var(--c-text-muted)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {stageLabels[stg].toUpperCase()}
              </text>
            </g>
          );
        })}

        {/* Stage segment bars */}
        {segments.map((seg, i) => {
          const segStart = new Date(seg.t_start).getTime();
          const segEnd = new Date(seg.t_end).getTime();
          const x = padLeft + ((segStart - startMs) / totalMs) * plotW;
          const w = Math.max(((segEnd - segStart) / totalMs) * plotW - 1, 2);
          const rowIdx = STAGE_ORDER.indexOf(seg.stage as (typeof STAGE_ORDER)[number]);
          if (rowIdx < 0) return null;
          const yTop = padTop + rowIdx * rowH;
          const barH = rowH - 8;
          const fill =
            STAGE_VARS[seg.stage as keyof typeof STAGE_VARS] ?? "var(--c-text-faint)";
          return (
            <rect
              key={i}
              x={x}
              y={yTop + 4}
              width={w}
              height={barH}
              rx={2}
              fill={fill}
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

        {/* X-axis time labels */}
        {xMarks.map((m, i) => (
          <text
            key={i}
            x={m.x}
            y={padTop + plotH + 18}
            textAnchor={m.align}
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

/* ----------------------------------------------------------- HRV trajectory */

function HrvTrajectory({
  readings,
  locale,
}: {
  readings: HrvReading[];
  locale: "en" | "it";
}) {
  const t = useT();
  if (!readings.length) return null;

  const W = 1000;
  const H = 200;
  const padLeft = 52;
  const padRight = 18;
  const padTop = 14;
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

  // Single dashed baseline = mean of rolling_baseline_ms
  const baselineMs =
    baselines.length > 0
      ? baselines.reduce((s, v) => s + v, 0) / baselines.length
      : 0;

  const startMs = new Date(readings[0].timestamp).getTime();
  const endMs = new Date(readings[readings.length - 1].timestamp).getTime();
  const totalMs = Math.max(endMs - startMs, 1);

  const linePath = readings
    .map((r) => {
      const ts = new Date(r.timestamp).getTime();
      const x = padLeft + ((ts - startMs) / totalMs) * plotW;
      const y = padTop + plotH - ((r.hrv_ms - yMin) / yRange) * plotH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const baselineY = padTop + plotH - ((baselineMs - yMin) / yRange) * plotH;

  const peakIdx = values.indexOf(rawMax);
  const peakX = padLeft + ((new Date(readings[peakIdx].timestamp).getTime() - startMs) / totalMs) * plotW;
  const peakY = padTop + plotH - ((rawMax - yMin) / yRange) * plotH;

  // Y-axis ticks (3)
  const yTicks = [yMin, yMin + yRange / 2, yMax];

  // X-axis time marks every ~2h
  const twoH = 2 * 3600 * 1000;
  const xMarks: { x: number; label: string; align: "start" | "middle" | "end" }[] = [];
  for (let ms = 0; ms <= totalMs + 1; ms += twoH) {
    const ts = startMs + Math.min(ms, totalMs);
    const x = padLeft + (Math.min(ms, totalMs) / totalMs) * plotW;
    const label = new Date(ts).toLocaleTimeString(
      locale === "it" ? "it-IT" : "en-GB",
      { hour: "2-digit", minute: "2-digit", hour12: false },
    );
    const align = ms === 0 ? "start" : ms >= totalMs ? "end" : "middle";
    xMarks.push({ x, label, align });
  }

  return (
    <div>
      {/* Legend */}
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11px]">
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-3 rounded-full"
            style={{ background: "var(--c-primary)" }}
          />
          <span className="text-muted">{t("sleep.hrv_peak")}</span>
          <span className="num font-semibold text-ink2">
            {fmtNum(rawMax, 1)} ms
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <svg width="16" height="6" aria-hidden>
            <line
              x1="0"
              y1="3"
              x2="16"
              y2="3"
              stroke="var(--c-text-faint)"
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
          </svg>
          <span className="text-muted">{t("sleep.hrv_baseline")}</span>
          <span className="num font-semibold text-ink2">
            {fmtNum(baselineMs, 1)} ms
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ minWidth: 560 }}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label={t("sleep.overnight_hrv")}
        >
          {/* Y grid + tick labels */}
          {yTicks.map((v, i) => {
            const y = padTop + plotH - ((v - yMin) / yRange) * plotH;
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
                  x={padLeft - 8}
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

          {/* Dashed baseline reference */}
          <line
            x1={padLeft}
            y1={baselineY}
            x2={padLeft + plotW}
            y2={baselineY}
            stroke="var(--c-text-faint)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />

          {/* Area fill under line */}
          <path
            d={`M${linePath} L${padLeft + plotW},${padTop + plotH} L${padLeft},${padTop + plotH} Z`}
            fill="var(--c-primary)"
            fillOpacity={0.08}
            stroke="none"
          />

          {/* Line path */}
          <path
            d={`M${linePath}`}
            fill="none"
            stroke="var(--c-primary)"
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Peak marker */}
          <circle cx={peakX} cy={peakY} r={3} fill="var(--c-primary)" />
          <circle
            cx={peakX}
            cy={peakY}
            r={6}
            fill="var(--c-primary)"
            fillOpacity={0.18}
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

          {/* X-axis time labels */}
          {xMarks.map((m, i) => (
            <text
              key={i}
              x={m.x}
              y={padTop + plotH + 18}
              textAnchor={m.align}
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
    </div>
  );
}
