/**
 * Sleep night detail — mockup "sleep_night_detail".
 *
 * Score arc gauge, duration analysis pods, the stage timeline, the
 * overnight vitals strip and the HRV envelope. The hypnogram renders from
 * the STORED stage epochs (GET /sleep/{date}/stages, parsed from raw
 * payloads — no invention); when a night has no epoch timeline the page
 * falls back to the proportional architecture bar and says so.
 */

import { useQuery } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Info } from "lucide-react";
import { api, type SleepDay, type SleepList, type SleepStages } from "../../app/api";
import {
  ArcGauge,
  Badge,
  BigStat,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  StatPod,
  ZoneBar,
  fmtClock,
  fmtHours,
  fmtNum,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

const OPTIMAL_SLEEP_S = 8 * 3600; // "optimal target" reference buffer

function stageColor(key: string): string {
  return {
    deep: "var(--c-stage-deep)",
    rem: "var(--c-stage-rem)",
    core: "var(--c-stage-core)",
    light: "var(--c-stage-core)",
    awake: "var(--c-stage-awake)",
  }[key] ?? "var(--c-hairline2)";
}

/* ----------------------------------------------------------- hypnogram */

function Hypnogram({
  day,
  stages,
}: {
  day: SleepDay;
  stages: SleepStages | null;
}) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const s = day.session;

  const labels: Record<string, string> = {
    awake: t("stage.awake"),
    rem: t("stage.rem"),
    core: t("stage.core"),
    light: t("stage.core"),
    deep: t("stage.deep"),
  };

  const rows = [
    { key: "awake", label: labels.awake, y: 3, color: c.stage.awake },
    { key: "rem", label: labels.rem, y: 2, color: c.stage.rem },
    { key: "core", label: labels.core, y: 1, color: c.stage.core },
    { key: "deep", label: labels.deep, y: 0, color: c.stage.deep },
  ];

  let segments: { x0: number; x1: number; stage: string }[] = [];
  const measured = !!stages?.segments?.length;
  if (measured && stages?.segments) {
    segments = stages.segments.map((seg) => ({
      x0: new Date(seg.t_start).getTime(),
      x1: new Date(seg.t_end).getTime(),
      stage: seg.stage === "light" ? "core" : seg.stage,
    }));
  } else if (s) {
    // Proportional fallback: blocks laid out night-long in physiological
    // cycle order from the canonical aggregates. Labeled as such in the UI.
    const start = new Date(s.start_time).getTime();
    const end = new Date(s.end_time).getTime();
    const span = Math.max(end - start, 1);
    const cycle = [
      { key: "deep", v: s.deep_s ?? 0 },
      { key: "core", v: s.light_s ?? 0 },
      { key: "rem", v: s.rem_s ?? 0 },
    ];
    const cycleTotal = cycle.reduce((a, p) => a + p.v, 0) || 1;
    const cycles = Math.max(1, Math.round((s.total_sleep_s ?? cycleTotal) / 5400));
    let cursor = 0;
    const body = span * 0.92;
    for (let cy = 0; cy < cycles; cy++) {
      for (const part of cycle) {
        const dur = (body * (part.v / cycleTotal)) / cycles;
        segments.push({ x0: start + cursor, x1: start + cursor + dur, stage: part.key });
        cursor += dur;
      }
    }
    const awakeMs = span - body;
    if (awakeMs > 0) {
      segments.push({ x0: start + body * 0.5, x1: start + body * 0.5 + awakeMs, stage: "awake" });
    }
  }

  if (!s || segments.length === 0) return null;

  const start = new Date(s.start_time).getTime();
  const end = new Date(s.end_time).getTime();

  const timeLabels: string[] = [];
  for (let i = 0; i <= 6; i++) {
    const tt = start + ((end - start) * i) / 6;
    timeLabels.push(
      new Date(tt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
    );
  }

  const option = {
    grid: { left: 56, right: 12, top: 8, bottom: 26 },
    tooltip: {
      trigger: "item",
      formatter: (p: { data?: { stage?: string; x0?: number; x1?: number } }) => {
        const d = p.data;
        if (!d?.stage) return "";
        const f = (ms: number) =>
          new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
        const dur = d.x1 && d.x0 ? Math.round((d.x1 - d.x0) / 60000) : null;
        return `${labels[d.stage] ?? d.stage}${dur !== null ? ` · ${dur} min` : ""}${d.x0 ? `<br/>${f(d.x0)} → ${f(d.x1 ?? 0)}` : ""}`;
      },
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
    },
    xAxis: {
      type: "value",
      min: start,
      max: end,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: () => "",
        interval: 0,
      },
      splitLine: { show: false },
    },
    yAxis: {
      // category bands: bottom→top = DEEP, CORE, REM, AWAKE (mockup order)
      type: "category",
      data: ["DEEP", "CORE", "REM", "AWAKE"],
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        fontFamily: "Geist",
        fontWeight: 600,
      },
    },
    series: [
      {
        type: "custom",
        renderItem: (
          params: { coordSys: { x: number; y: number; width: number; height: number }; dataIndex: number },
        ) => {
          const seg = segments[params.dataIndex];
          if (!seg) return null as unknown as string;
          // category band index: 0=DEEP (bottom) … 3=AWAKE (top)
          const band =
            ({ deep: 0, rem: 2, core: 1, light: 1, awake: 3 } as Record<string, number>)[seg.stage] ?? 1;
          const cat = params.coordSys;
          const x0 = cat.x + ((seg.x0 - start) / (end - start)) * cat.width;
          const x1 = cat.x + ((seg.x1 - start) / (end - start)) * cat.width;
          const rowH = cat.height / 4;
          // category index 0 renders at the BOTTOM of a y category axis
          const rectY = cat.y + (3 - band + 0.5) * rowH - 7;
          const row = rows.find((r) => r.y === band);
          return {
            type: "rect",
            shape: { x: x0, y: rectY, width: Math.max(2, x1 - x0), height: 14, r: 7 },
            style: { fill: row?.color ?? c.hairline },
          };
        },
        data: segments.map((seg, i) => ({ ...seg, value: [seg.x0, i], dataIndex: i, seg })),
        encode: { x: 0 },
        clip: true,
      },
    ],
  };

  const total = (s.deep_s ?? 0) + (s.rem_s ?? 0) + (s.light_s ?? 0) + (s.awake_s ?? 0) || 1;
  const parts = [
    { key: "awake", v: s.awake_s ?? 0, label: "stage.awake" },
    { key: "rem", v: s.rem_s ?? 0, label: "stage.rem" },
    { key: "core", v: s.light_s ?? 0, label: "stage.core" },
    { key: "deep", v: s.deep_s ?? 0, label: "stage.deep" },
  ].filter((p) => p.v > 0);

  return (
    <Card>
      <CardHeader
        eyebrow={t("sleep.hypnogram")}
        title={t("sleep.hypnogram_title")}
        right={
          <Badge tone={measured ? "primary" : "neutral"}>
            {measured ? t("sleep.stage_epochs") : t("sleep.proportional")}
          </Badge>
        }
      />
      <p className="mb-2 text-[12px] text-muted">
        {measured
          ? t("sleep.hypnogram_measured")
          : t("sleep.hypnogram_fallback")}
      </p>
      <EChart option={option} height={190} />
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {parts.map((p) => (
          <span key={p.key} className="num flex items-center gap-1.5 text-[11px] text-muted">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: stageColor(p.key) }} />
            {t(p.label)} {Math.round((p.v / total) * 100)}%
          </span>
        ))}
      </div>
      <div className="num mt-1 flex justify-between text-[10px] text-faint">
        {timeLabels.map((l, i) => (
          <span key={i}>{l}</span>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------- page */

export default function SleepNightPage() {
  const { t } = useTranslation();
  const { date } = useParams<{ date: string }>();
  const navigate = useNavigate();

  const day = useQuery({
    queryKey: ["sleep", date],
    queryFn: () => api.get<SleepDay>(`/sleep/${date}`),
    enabled: !!date,
  });
  const stages = useQuery({
    queryKey: ["sleep-stages", date],
    queryFn: () => api.get<SleepStages>(`/sleep/${date}/stages`),
    enabled: !!date,
  });
  const week = useQuery({
    queryKey: ["sleep", "week"],
    queryFn: () => api.get<SleepList>("/sleep?limit=7"),
  });

  if (day.isLoading) return <Loading />;
  if (day.isError || !day.data) return <ErrorNote />;
  const d = day.data;
  const s = d.session;

  const shift = (days: number) => {
    if (!date) return;
    const nd = new Date(date + "T00:00:00");
    nd.setDate(nd.getDate() + days);
    navigate(`/app/sleep/${nd.toISOString().slice(0, 10)}`);
  };

  const inBed = s ? (new Date(s.end_time).getTime() - new Date(s.start_time).getTime()) / 1000 : null;
  const debt = s?.total_sleep_s !== null && s ? Math.max(0, OPTIMAL_SLEEP_S - s.total_sleep_s) : null;
  const hrvVals = d.hrv_readings.map((r) => r.hrv_ms);
  const hrvAvg = hrvVals.length ? hrvVals.reduce((a, b) => a + b, 0) / hrvVals.length : null;
  const hrvBase = [...d.hrv_readings].reverse().find((r) => r.rolling_baseline_ms)?.rolling_baseline_ms ?? null;

  // 7-day rhythm blocks from the week list
  const weekNights = week.data?.items ?? [];
  const weekAvg = weekNights.length
    ? weekNights.reduce((a, n) => a + (n.total_sleep_s ?? 0), 0) / weekNights.length
    : null;

  const score = s?.sleep_score === null || !s ? null : Math.round(s.sleep_score);
  const scoreTone = score === null ? "var(--c-hairline2)" : score >= 75 ? "var(--c-positive)" : score >= 50 ? "var(--c-primary)" : "var(--c-warning)";
  const verdict =
    score === null ? "—" : score >= 75 ? t("common.optimal") : score >= 50 ? t("common.good") : t("common.fair");

  const prevNight = weekNights.find((n) => n.local_date < (date ?? ""));
  const nextNight = [...weekNights].reverse().find((n) => n.local_date > (date ?? ""));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={
          new Date((date ?? "") + "T00:00:00").toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
          })
        }
        subtitle={t("sleep.night_subtitle", {
          start: s ? new Date(s.start_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—",
          end: s ? new Date(s.end_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—",
        })}
        actions={
          <div className="num flex items-center gap-1 rounded-control border border-hairline bg-surface px-1">
            <button
              type="button"
              aria-label={t("common.prev_day")}
              onClick={() => shift(-1)}
              disabled={!prevNight}
              className="flex h-7 w-7 items-center justify-center text-muted hover:text-ink disabled:opacity-30"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              aria-label={t("common.next_day")}
              onClick={() => shift(1)}
              disabled={!nextNight}
              className="flex h-7 w-7 items-center justify-center text-muted hover:text-ink disabled:opacity-30"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        }
      />

      {s ? (
        <>
          <div className="grid grid-cols-12 gap-4">
            {/* ---- score + duration row ---- */}
            <Card className="col-span-12 lg:col-span-4">
              <CardHeader eyebrow={t("sleep.recovery_index")} />
              <div className="flex flex-col items-center">
                <ArcGauge value={score} tone={scoreTone} label={<Badge tone={score !== null && score >= 75 ? "positive" : "neutral"}>{verdict}</Badge>} />
                <div className="mt-2 grid w-full grid-cols-2 gap-3 border-t border-hairline pt-3">
                  <div>
                    <div className="eyebrow">{t("sleep.efficiency")}</div>
                    <BigStat
                      value={
                        inBed && s.total_sleep_s
                          ? fmtNum((s.total_sleep_s / inBed) * 100, 1)
                          : "—"
                      }
                      unit="%"
                      size="md"
                      className="mt-0.5"
                    />
                  </div>
                  <div>
                    <div className="eyebrow">{t("sleep.latency")}</div>
                    <BigStat value="—" size="md" className="mt-0.5" />
                  </div>
                </div>
              </div>
            </Card>

            <Card className="col-span-12 lg:col-span-8">
              <CardHeader
                eyebrow={t("sleep.duration_analysis")}
                title={t("sleep.asleep_vs_bed")}
                right={
                  <span className="flex items-center gap-3 text-[10px] text-muted">
                    <span className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-positive" /> {t("sleep.asleep")}
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-alert" /> {t("stage.awake")}
                    </span>
                  </span>
                }
              />
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatPod label={t("sleep.time_in_bed")} value={fmtClock(inBed)} sub={t("sleep.bed_window")} />
                <StatPod
                  label={t("sleep.time_asleep")}
                  value={fmtClock(s.total_sleep_s)}
                  sub={
                    debt !== null && debt > 0
                      ? `−${fmtClock(debt)} ${t("sleep.vs_target")}`
                      : t("sleep.target_met")
                  }
                  tone={(s.total_sleep_s ?? 0) >= OPTIMAL_SLEEP_S * 0.88 ? "positive" : "ink"}
                />
                <StatPod label={t("sleep.awake_time")} value={fmtClock(s.awake_s)} sub={`${t("sleep.disturbances")}`} />
                <StatPod label={t("sleep.restlessness")} value={fmtNum(s.restlessness, 2)} unit="" sub={t("sleep.movement_index")} />
              </div>
              <div className="mt-4">
                <ZoneBar
                  height={10}
                  parts={[
                    { key: "awake", value: s.awake_s ?? 0, color: stageColor("awake") },
                    { key: "rem", value: s.rem_s ?? 0, color: stageColor("rem") },
                    { key: "core", value: s.light_s ?? 0, color: stageColor("core") },
                    { key: "deep", value: s.deep_s ?? 0, color: stageColor("deep") },
                  ]}
                />
                <div className="num mt-1.5 flex flex-wrap justify-between gap-2 text-[10px] text-muted">
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: stageColor("awake") }} />
                    {t("stage.awake")} {Math.round(((s.awake_s ?? 0) / (inBed || 1)) * 100)}%
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: stageColor("rem") }} />
                    {t("stage.rem")} {Math.round(((s.rem_s ?? 0) / (inBed || 1)) * 100)}%
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: stageColor("core") }} />
                    {t("stage.core")} {Math.round(((s.light_s ?? 0) / (inBed || 1)) * 100)}%
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: stageColor("deep") }} />
                    {t("stage.deep")} {Math.round(((s.deep_s ?? 0) / (inBed || 1)) * 100)}%
                  </span>
                </div>
              </div>
            </Card>

            {/* ---- hypnogram ---- */}
            <div className="col-span-12">
              <Hypnogram day={d} stages={stages.data ?? null} />
            </div>

            {/* ---- vitals row ---- */}
            <Card className="col-span-12">
              <CardHeader
                eyebrow={t("sleep.vitals")}
                title={t("sleep.autonomic")}
                right={<span className="num text-[10px] tracking-[0.08em] text-faint">{t("sleep.overnight_sensors")}</span>}
              />
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <StatPod
                  label={t("overview.resting_hr")}
                  value={fmtNum(d.biometrics.resting_hr)}
                  unit="bpm"
                  right={null}
                />
                <StatPod
                  label={t("biometrics.hrv")}
                  value={fmtNum(hrvAvg, 0)}
                  unit="ms"
                  sub={
                    hrvBase
                      ? `${hrvAvg !== null && hrvAvg >= hrvBase ? "+" : ""}${hrvAvg !== null ? (hrvAvg - hrvBase).toFixed(1) : "—"} ${t("overview.vs_baseline")}`
                      : undefined
                  }
                  tone={hrvBase && hrvAvg !== null && hrvAvg >= hrvBase ? "positive" : "ink"}
                />
                <StatPod label={t("overview.respiration")} value={fmtNum(s.respiration_avg, 1)} unit="br/min" sub={t("sleep.steady")} />
                <StatPod label={t("overview.spo2")} value={fmtNum(s.spo2_avg ?? d.biometrics.spo2_avg, 1)} unit="%" sub={t("sleep.saturation_note")} />
                <StatPod
                  label={t("sleep.sleep_regularity_short")}
                  value={weekNights.length >= 5 ? t("sleep.stable") : t("sleep.limited")}
                  sub={`${t("sleep.window7")}`}
                />
              </div>
            </Card>

            {/* ---- HRV envelope + circadian ---- */}
            <Card className="col-span-12 lg:col-span-8">
              <CardHeader
                eyebrow={t("sleep.hrv_envelope")}
                title={t("sleep.overnight_hrv")}
                right={
                  <span className="num text-[10px] text-faint">
                    {hrvVals.length} {t("sleep.readings")}
                  </span>
                }
              />
              <HrvEnvelope day={d} />
            </Card>

            <Card className="col-span-12 lg:col-span-4">
              <CardHeader
                eyebrow={t("sleep.circadian")}
                title={t("sleep.rhythm_alignment")}
                right={<Badge tone="positive">{t("sleep.window7")}</Badge>}
              />
              {weekAvg !== null ? (
                <>
                  <div className="num mb-3 flex items-baseline gap-2">
                    <span className="text-[28px] font-bold text-ink">{fmtHours(weekAvg)}</span>
                    <span className="text-[11px] text-muted">{t("sleep.avg7")}</span>
                  </div>
                  <div className="flex justify-between gap-1.5">
                    {weekNights.map((n) => {
                      const ratio = (n.total_sleep_s ?? 0) / (OPTIMAL_SLEEP_S * 0.9);
                      const alpha = Math.max(0.18, Math.min(1, ratio));
                      return (
                        <Link
                          key={n.local_date}
                          to={`/app/sleep/${n.local_date}`}
                          title={`${n.local_date} · ${fmtHours(n.total_sleep_s)}`}
                          className="flex h-9 flex-1 items-end justify-center rounded-sm border border-hairline"
                          style={{ background: `color-mix(in srgb, var(--c-primary) ${alpha * 100}%, transparent)` }}
                        >
                          <span className="num pb-0.5 text-[9px] font-semibold text-ink">
                            {new Date(n.local_date + "T00:00:00").toLocaleDateString(undefined, { weekday: "narrow" })}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-hairline pt-3 text-[11px] text-muted">
                    <span>{t("sleep.midpoint")}</span>
                    <span className="num text-ink2">
                      {s
                        ? new Date(
                            (new Date(s.start_time).getTime() + new Date(s.end_time).getTime()) / 2,
                          ).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
                        : "—"}
                    </span>
                  </div>
                </>
              ) : (
                <Empty>{t("sleep.no_night")}</Empty>
              )}
            </Card>
          </div>
        </>
      ) : (
        <Card>
          <Empty
            action={
              <span className="flex items-center gap-1.5 text-[11px] text-faint">
                <Info size={12} /> {t("sleep.no_night_hint")}
              </span>
            }
          >
            {t("sleep.no_night")}
          </Empty>
        </Card>
      )}
    </div>
  );
}

/** Overnight HRV envelope — single source EChart line. */
function HrvEnvelope({ day }: { day: SleepDay }) {
  const c = useChartTheme();
  const { t } = useTranslation();
  const readings = day.hrv_readings;
  if (readings.length === 0) return <Empty>{t("biometrics.no_data")}</Empty>;
  const times = readings.map((r) => new Date(r.timestamp).getTime());
  const vals = readings.map((r) => r.hrv_ms);
  const baseline = readings.map((r) => r.rolling_baseline_ms);
  const option = {
    grid: { left: 38, right: 10, top: 12, bottom: 24 },
    tooltip: {
      trigger: "axis",
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
      valueFormatter: (v: number) => `${Math.round(v)} ms`,
    },
    xAxis: {
      type: "time",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: (v: number) =>
          new Date(v).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
    },
    series: [
      {
        name: "HRV",
        type: "line",
        data: times.map((tt, i) => [tt, vals[i]]),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: c.positive, width: 2 },
        itemStyle: { color: c.positive },
        areaStyle: { color: c.positive, opacity: 0.08 },
      },
      ...(baseline.some((b) => b !== null)
        ? [
            {
              name: t("overview.baseline7"),
              type: "line",
              data: times.map((tt, i) => [tt, baseline[i]]),
              smooth: true,
              showSymbol: false,
              lineStyle: { color: c.muted, width: 1, type: "dashed" },
              itemStyle: { color: c.muted },
            },
          ]
        : []),
    ],
  };
  return <EChart option={option} height={200} />;
}
