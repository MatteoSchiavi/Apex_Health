/**
 * Sleep night detail — mockup "sleep_night_detail": gauge score, duration
 * analysis, the hypnogram (stage timeline rebuilt from stage durations as a
 * banded custom ECharts series), overnight vitals strip and the HRV
 * envelope for the day.
 */

import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type SleepDay, type MetricTrend } from "../../app/api";
import {
  Badge,
  BigStat,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Loading,
  fmtHours,
  fmtNum,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

/** Approximate a stage sequence from the aggregate durations: blocks laid
 * out night-long, alternating deep/REM/light with awake interruptions on
 * top — honest about resolution (it renders what the canonical model
 * stores) while preserving the mockup's banded aesthetic. */
function hypnogramOption(
  day: SleepDay,
  c: ReturnType<typeof useChartTheme>,
  labels: Record<string, string>,
) {
  const s = day.session;
  if (!s) return null;
  const start = new Date(s.start_time).getTime();
  const end = new Date(s.end_time).getTime();
  const span = Math.max(end - start, 1);

  const stageRows = [
    { key: "awake", label: labels.awake, color: c.stage.awake, y: 3 },
    { key: "rem", label: labels.rem, color: c.stage.rem, y: 2 },
    { key: "core", label: labels.core, color: c.stage.core, y: 1 },
    { key: "deep", label: labels.deep, color: c.stage.deep, y: 0 },
  ];

  // Split the night into segments proportional to stage durations, cycling
  // deep → light → REM (physiologically ordered cycles).
  const cycle = [
    { key: "deep", v: s.deep_s ?? 0, y: 0, color: c.stage.deep },
    { key: "core", v: s.light_s ?? 0, y: 1, color: c.stage.core },
    { key: "rem", v: s.rem_s ?? 0, y: 2, color: c.stage.rem },
  ];
  const totalCycle = cycle.reduce((acc, p) => acc + p.v, 0) || 1;
  const awakeV = s.awake_s ?? 0;
  const segments: { x0: number; x1: number; y: number; color: string; key: string }[] = [];
  let cursor = 0;
  let idx = 0;
  const body = span - (awakeV / 1000) * 1000;
  const cycles = Math.max(1, Math.round((s.total_sleep_s ?? totalCycle) / 5400)); // ~90min cycles
  for (let cy = 0; cy < cycles; cy++) {
    for (const part of cycle) {
      const share = part.v / totalCycle;
      const dur = (body * share) / cycles;
      const x0 = start + cursor;
      const x1 = start + Math.min(cursor + dur, body);
      if (x1 > x0) {
        segments.push({ x0, x1, y: part.y, color: part.color, key: part.key });
      }
      cursor += dur;
      idx++;
    }
  }
  void idx;
  // Awake segments interleaved: one long strip at the top row scaled to fit
  if (awakeV > 0) {
    const dur = (awakeV / 1000) * 1000;
    const x0 = start + body * 0.45;
    segments.push({ x0, x1: x0 + dur, y: 3, color: c.stage.awake, key: "awake" });
  }

  const timeLabels: string[] = [];
  const timeValues: number[] = [];
  for (let i = 0; i <= 6; i++) {
    const t = start + (span * i) / 6;
    timeValues.push(t);
    timeLabels.push(
      new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
    );
  }

  return {
    grid: { left: 52, right: 12, top: 8, bottom: 26 },
    tooltip: {
      formatter: (p: { data?: { key?: string } }) => labels[p.data?.key ?? ""] ?? "",
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
    },
    xAxis: {
      type: "time",
      min: start,
      max: end,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: () => "",
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: -0.5,
      max: 3.5,
      interval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 10,
        formatter: (v: number) => stageRows[v]?.label ?? "",
      },
      splitLine: { show: false },
    },
    series: [
      {
        type: "custom",
        renderItem: (params: { dataIndex: number }, api2: {
          value: () => number[];
          coord: (v: number[]) => number[];
          size: (v: number[]) => number[];
        }) => {
          const seg = segments[params.dataIndex];
          const x0 = api2.coord([seg.x0, seg.y]);
          const x1 = api2.coord([seg.x1, seg.y]);
          return {
            type: "rect",
            shape: { x: x0[0], y: x0[1] - 14, width: Math.max(x1[0] - x0[0], 1), height: 28, r: 14 },
            style: { fill: seg.color, opacity: 0.9 },
          };
        },
        data: segments.map((s2) => [s2.x0, s2.x1, s2.y, s2.key]),
        encode: { x: [0, 1], y: 2 },
      },
      {
        type: "line",
        data: timeValues.map((tv, i) => [tv, -0.5 + i * 0]),
        silent: true,
        showSymbol: false,
        lineStyle: { opacity: 0 },
      },
    ],
  };
}

function hrvOption(day: SleepDay, c: ReturnType<typeof useChartTheme>) {
  const rows = day.hrv_readings;
  if (rows.length === 0) return null;
  const ts = rows.map((r) => new Date(r.timestamp).getTime());
  const vs = rows.map((r) => r.hrv_ms);
  const base = rows.map((r) => r.rolling_baseline_ms);
  return {
    grid: { left: 36, right: 12, top: 14, bottom: 26 },
    tooltip: {
      trigger: "axis",
      backgroundColor: c.surface,
      borderColor: c.hairline,
      textStyle: { color: c.ink, fontSize: 11 },
      valueFormatter: (v: number) => `${fmtNum(v, 0)} ms`,
    },
    xAxis: {
      type: "time",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
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
        data: ts.map((t, i) => [t, vs[i]]),
        showSymbol: false,
        smooth: true,
        lineStyle: { color: c.primary, width: 2 },
        itemStyle: { color: c.primary },
        areaStyle: { color: c.primary, opacity: 0.1 },
      },
      ...(base.some((b) => b !== null)
        ? [
            {
              name: "baseline",
              type: "line",
              data: ts.map((t, i) => [t, base[i]]),
              showSymbol: false,
              smooth: true,
              lineStyle: { color: c.muted, width: 1, type: "dashed" as const },
              itemStyle: { color: c.muted },
            },
          ]
        : []),
    ],
  };
}

export default function SleepNightPage() {
  const { t } = useTranslation();
  const { date } = useParams();
  const c = useChartTheme();

  const day = useQuery({
    queryKey: ["sleep-day", date],
    queryFn: () => api.get<SleepDay>(`/sleep/${date}`),
    enabled: !!date,
  });
  const hrvTrend = useQuery({
    queryKey: ["metric", "hrv_deviation"],
    queryFn: () => api.get<MetricTrend>("/metrics/hrv_deviation?days=30"),
  });

  if (day.isLoading) return <Loading />;
  if (day.isError) return <ErrorNote />;
  const d = day.data!;
  const s = d.session;
  const inBed = s ? (new Date(s.end_time).getTime() - new Date(s.start_time).getTime()) / 1000 : null;

  const labels = {
    awake: t("stage.awake"),
    rem: t("stage.rem"),
    core: t("stage.core"),
    deep: t("stage.deep"),
  };

  const hypno = s ? hypnogramOption(d, c, labels) : null;
  const hrv = hrvOption(d, c);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="eyebrow">
          <Link to="/app/sleep" className="hover:underline">
            ← {t("sleep.title")}
          </Link>
        </div>
        <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">
          {s
            ? t("sleep.night_of", {
                from: new Date(s.start_time).toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "short",
                }),
                to: new Date(s.end_time).toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "short",
                }),
              })
            : t("sleep.no_night")}
        </h1>
      </div>

      {!s ? (
        <Empty>{t("sleep.no_night")}</Empty>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="flex flex-col items-center justify-center gap-2 py-6">
              <div className="eyebrow">{t("sleep.sleep_score")}</div>
              <BigStat
                value={fmtNum(s.sleep_score)}
                unit="/100"
                size="xl"
              />
              <Badge tone={(s.sleep_score ?? 0) >= 75 ? "positive" : "warning"}>
                {(s.sleep_score ?? 0) >= 75 ? t("sleep.optimal") : t("common.fair")}
              </Badge>
              <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-center">
                <div>
                  <div className="eyebrow">{t("sleep.efficiency")}</div>
                  <div className="num text-[15px] font-semibold text-ink">
                    {fmtNum(
                      inBed && s.total_sleep_s
                        ? (s.total_sleep_s / inBed) * 100
                        : null,
                      1,
                    )}
                    %
                  </div>
                </div>
                <div>
                  <div className="eyebrow">{t("sleep.latency")}</div>
                  <div className="num text-[15px] font-semibold text-ink">—</div>
                </div>
              </div>
            </Card>

            <Card className="xl:col-span-2">
              <CardHeader
                eyebrow={t("sleep.duration_analysis")}
                title={t("sleep.asleep_vs_bed")}
              />
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <div>
                  <div className="eyebrow">{t("sleep.time_in_bed")}</div>
                  <BigStat value={fmtHours(inBed)} className="mt-1" />
                  <div className="num mt-0.5 text-[10px] text-faint">
                    {new Date(s.start_time).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}{" "}
                    →{" "}
                    {new Date(s.end_time).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
                <div>
                  <div className="eyebrow">{t("sleep.time_asleep")}</div>
                  <BigStat value={fmtHours(s.total_sleep_s)} className="mt-1" />
                  <div className="num mt-0.5 text-[10px] text-positiveText">
                    {t("sleep.vs_target")}
                  </div>
                </div>
                <div>
                  <div className="eyebrow">{t("stage.deep")} + {t("stage.rem")}</div>
                  <BigStat
                    value={fmtHours((s.deep_s ?? 0) + (s.rem_s ?? 0))}
                    className="mt-1"
                  />
                </div>
                <div>
                  <div className="eyebrow">{t("sleep.awake_intervals")}</div>
                  <BigStat value={fmtHours(s.awake_s)} className="mt-1" />
                </div>
              </div>
              <div className="mt-4 flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-hairline">
                {[
                  { v: s.awake_s ?? 0, color: "var(--c-stage-awake)" },
                  { v: s.rem_s ?? 0, color: "var(--c-stage-rem)" },
                  { v: s.light_s ?? 0, color: "var(--c-stage-core)" },
                  { v: s.deep_s ?? 0, color: "var(--c-stage-deep)" },
                ].map((p, i) => {
                  const total = (s.awake_s ?? 0) + (s.rem_s ?? 0) + (s.light_s ?? 0) + (s.deep_s ?? 0);
                  return total > 0 ? (
                    <div
                      key={i}
                      className="h-full rounded-full"
                      style={{ width: `${(p.v / total) * 100}%`, background: p.color }}
                    />
                  ) : null;
                })}
              </div>
              <div className="num mt-1.5 flex flex-wrap gap-3 text-[10px] text-muted">
                {[
                  [t("stage.awake"), s.awake_s, "var(--c-stage-awake)"],
                  [t("stage.rem"), s.rem_s, "var(--c-stage-rem)"],
                  [t("stage.core"), s.light_s, "var(--c-stage-core)"],
                  [t("stage.deep"), s.deep_s, "var(--c-stage-deep)"],
                ].map(([label, v, color]) => (
                  <span key={String(label)} className="num">
                    <span
                      className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                      style={{ background: String(color) }}
                    />
                    {String(label)} {fmtHours(v as number)} ({fmtNum(((v as number) / (inBed || 1)) * 100, 0)}
                    %)
                  </span>
                ))}
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader
              eyebrow={t("sleep.hypnogram")}
              right={
                <div className="num flex gap-3 text-[10px] text-muted">
                  {(["awake", "rem", "core", "deep"] as const).map((k) => (
                    <span key={k}>
                      <span
                        className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                        style={{
                          background:
                            k === "awake"
                              ? c.stage.awake
                              : k === "rem"
                                ? c.stage.rem
                                : k === "core"
                                  ? c.stage.core
                                  : c.stage.deep,
                        }}
                      />
                      {labels[k]}
                    </span>
                  ))}
                </div>
              }
            />
            {hypno ? <EChart option={hypno} height={220} /> : <Empty>{t("biometrics.no_data")}</Empty>}
          </Card>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader eyebrow={t("sleep.vitals")} />
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Vital label={t("overview.resting_hr")} value={fmtNum(d.biometrics.resting_hr)} unit={t("common.bpm")} />
                <Vital label={t("overview.spo2")} value={fmtNum(d.biometrics.spo2_avg, 1)} unit="%" />
                <Vital label={t("overview.respiration")} value={fmtNum(s.respiration_avg, 1)} unit="br/min" />
                <Vital label={t("settings.weight")} value={fmtNum(d.biometrics.weight_kg, 1)} unit="kg" />
              </div>
              <div className="mt-4 border-t border-hairline pt-3">
                <div className="eyebrow mb-2">HRV · rMSSD</div>
                {hrv ? <EChart option={hrv} height={160} /> : <Empty>{t("biometrics.no_data")}</Empty>}
              </div>
            </Card>

            <Card>
              <CardHeader
                eyebrow={t("biometrics.hrv")}
                title={t("biometrics.trend")}
                right={
                  hrvTrend.data?.stats?.latest != null && (
                    <span className="num text-[12px] text-ink2">
                      {fmtNum(hrvTrend.data.stats.latest, 1)}%
                    </span>
                  )
                }
              />
              {hrvTrend.data && hrvTrend.data.points.some((p) => p.value !== null) ? (
                <EChart
                  option={{
                    grid: { left: 36, right: 12, top: 14, bottom: 26 },
                    xAxis: {
                      type: "time",
                      axisLine: { show: false },
                      axisTick: { show: false },
                      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
                    },
                    yAxis: {
                      type: "value",
                      splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
                      axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
                    },
                    series: [
                      {
                        type: "bar",
                        data: hrvTrend.data.points.map((p) => [p.date, p.value]),
                        barMaxWidth: 7,
                        itemStyle: { color: c.primary, opacity: 0.75, borderRadius: [2, 2, 0, 0] },
                      },
                    ],
                  }}
                  height={280}
                />
              ) : (
                <Empty>{t("biometrics.no_data")}</Empty>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Vital({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-card border border-hairline bg-surface2 p-3">
      <div className="eyebrow truncate">{label}</div>
      <BigStat value={value} unit={unit} size="md" className="mt-1" />
    </div>
  );
}
