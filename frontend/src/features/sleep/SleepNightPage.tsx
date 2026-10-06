import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type SleepDay, type SleepStages } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
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
import { assess, shiftDay, localDay } from "../../components/data";
import { EChart, useChartTheme } from "../../components/charts/EChart";
function StageTimeline({ stages }: { stages: SleepStages }) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const segments = (stages.segments ?? []).filter(
    (s) => new Date(s.t_end).getTime() > new Date(s.t_start).getTime(),
  );
  if (!segments.length) return <Empty>{t("design.no_epochs")}</Empty>;
  const start = Math.min(...segments.map((s) => new Date(s.t_start).getTime()));
  const end = Math.max(...segments.map((s) => new Date(s.t_end).getTime()));
  const names = ["deep", "core", "rem", "awake"];
  return (
    <>
      <EChart
        height={200}
        option={{
        animation: false,
        grid: { left: 54, right: 12, top: 8, bottom: 30 },
        tooltip: {
          trigger: "item",
          confine: true,
          backgroundColor: c.surface,
          borderColor: c.hairline,
          textStyle: { color: c.ink, fontSize: 13 },
          formatter: (p: {
            data?: {
              segment: SleepStages["segments"] extends (infer U)[] | null
                ? U
                : never;
            };
          }) => {
            const s = p.data?.segment;
            if (!s) return "";
            return (
              t("stage." + (s.stage === "light" ? "core" : s.stage)) +
              "<br>" +
              new Date(s.t_start).toLocaleString() +
              " – " +
              new Date(s.t_end).toLocaleTimeString()
            );
          },
        },
        xAxis: {
          type: "value",
          min: start,
          max: end,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: c.muted,
            fontSize: 12,
            hideOverlap: true,
            formatter: (v: number) =>
              new Date(v).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
              }),
          },
          splitLine: { show: false },
        },
        yAxis: {
          type: "category",
          data: names.map((n) => t("stage." + n)),
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: c.muted, fontSize: 12 },
          splitLine: { show: false },
        },
        series: [
          {
            type: "custom",
            clip: true,
            renderItem: (params: {
              coordSys: { x: number; y: number; width: number; height: number };
              dataIndex: number;
            }) => {
              const s = segments[params.dataIndex],
                stage = s.stage === "light" ? "core" : s.stage,
                index = names.indexOf(stage);
              if (index < 0) return null;
              const area = params.coordSys;
              const x =
                area.x +
                ((new Date(s.t_start).getTime() - start) / (end - start)) *
                  area.width;
              const width =
                ((new Date(s.t_end).getTime() - new Date(s.t_start).getTime()) /
                  (end - start)) *
                area.width;
              return {
                type: "rect",
                shape: {
                  x,
                  y: area.y + ((3 - index + 0.5) * area.height) / 4 - 7,
                  width: Math.max(1, width),
                  height: 14,
                },
                style: { fill: c.stage[stage as keyof typeof c.stage] },
              };
            },
            data: segments.map((s) => ({
              value: [
                new Date(s.t_start).getTime(),
                names.indexOf(s.stage === "light" ? "core" : s.stage),
              ],
              segment: s,
            })),
            encode: { x: 0, y: 1 },
          },
        ],
        }}
      />
      <div
        className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-muted"
        aria-label={t("sleep.architecture")}
      >
        {names.map((stage) => (
          <span key={stage} className="flex items-center gap-2">
            <span
              className="h-2 w-2"
              style={{ background: `var(--c-stage-${stage})` }}
            />
            {t("stage." + stage)}
          </span>
        ))}
      </div>
    </>
  );
}
function OvernightHrv({ day }: { day: SleepDay }) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const readings = day.hrv_readings;
  if (!readings.length) return <Empty>{t("biometrics.no_data")}</Empty>;
  return (
    <EChart
      height={240}
      option={{
        animation: false,
        grid: { left: 45, right: 12, top: 30, bottom: 30 },
        legend: {
          top: 0,
          left: 0,
          textStyle: { color: c.muted, fontSize: 12 },
        },
        tooltip: {
          trigger: "axis",
          confine: true,
          backgroundColor: c.surface,
          borderColor: c.hairline,
          textStyle: { color: c.ink, fontSize: 13 },
          valueFormatter: (v: number) => fmtNum(v, 1) + " ms",
        },
        xAxis: {
          type: "time",
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: c.muted, fontSize: 12, hideOverlap: true },
        },
        yAxis: {
          type: "value",
          scale: true,
          splitNumber: 2,
          splitLine: { lineStyle: { color: c.hairline } },
          axisLabel: { color: c.muted, fontSize: 12 },
        },
        series: [
          {
            name: "HRV",
            type: "line",
            data: readings.map((r) => [r.timestamp, r.hrv_ms]),
            showSymbol: readings.length < 3,
            smooth: false,
            lineStyle: { color: c.ink, width: 2 },
            itemStyle: { color: c.ink },
          },
          ...(readings.some((r) => r.rolling_baseline_ms != null)
            ? [
                {
                  name: t("overview.baseline7"),
                  type: "line",
                  data: readings.map((r) => [
                    r.timestamp,
                    r.rolling_baseline_ms,
                  ]),
                  showSymbol: false,
                  lineStyle: { color: c.muted, type: "dashed", width: 1 },
                  itemStyle: { color: c.muted },
                },
              ]
            : []),
        ],
      }}
    />
  );
}
export default function SleepNightPage() {
  const { t } = useTranslation();
  const { date = "" } = useParams();
  const navigate = useNavigate();
  const timezone = useUi((s) => s.me?.timezone);
  const day = useQuery({
    queryKey: ["sleep", date],
    queryFn: () => api.get<SleepDay>("/sleep/" + date),
    enabled: !!date,
  });
  const stages = useQuery({
    queryKey: ["sleep-stages", date],
    queryFn: () => api.get<SleepStages>("/sleep/" + date + "/stages"),
    enabled: !!day.data?.session,
  });
  if (day.isLoading) return <Loading />;
  if (day.isError || !day.data) return <ErrorNote />;
  const d = day.data,
    s = d.session;
  const state = assess("sleep_score", s?.sleep_score ?? null);
  const inBed = s
    ? (new Date(s.end_time).getTime() - new Date(s.start_time).getTime()) / 1000
    : null;
  const hrv = d.hrv_readings.length
    ? d.hrv_readings.reduce((a, r) => a + r.hrv_ms, 0) / d.hrv_readings.length
    : null;
  const base = [...d.hrv_readings]
    .reverse()
    .find((r) => r.rolling_baseline_ms != null)?.rolling_baseline_ms;
  const parts = s
    ? [
        { key: "deep", value: s.deep_s, color: "var(--c-stage-deep)" },
        { key: "rem", value: s.rem_s, color: "var(--c-stage-rem)" },
        { key: "core", value: s.light_s, color: "var(--c-stage-core)" },
        { key: "awake", value: s.awake_s, color: "var(--c-stage-awake)" },
      ]
    : [];
  const total = parts.reduce((a, p) => a + (p.value ?? 0), 0);
  return (
    <div className="flex flex-col gap-6">
      <Link to="/app/sleep" className="text-link text-muted">
        <ArrowLeft size={16} />
        {t("sleep.history")}
      </Link>
      <PageHeader
        title={new Date(date + "T12:00:00").toLocaleDateString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
        subtitle={
          s
            ? t("sleep.night_subtitle", {
                start: new Date(s.start_time).toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: timezone,
                }),
                end: new Date(s.end_time).toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: timezone,
                }),
              })
            : t("sleep.no_night")
        }
        actions={
          <div className="flex gap-2">
            <button
              className="p-3"
              aria-label={t("common.prev_day")}
              onClick={() => navigate("/app/sleep/" + shiftDay(date, -1))}
            >
              <ChevronLeft size={18} />
            </button>
            <button
              className="p-3 disabled:opacity-30"
              disabled={date >= localDay(timezone)}
              aria-label={t("common.next_day")}
              onClick={() => navigate("/app/sleep/" + shiftDay(date, 1))}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        }
      />
      {!s ? (
        <Card>
          <Empty>{t("sleep.no_night")}</Empty>
        </Card>
      ) : (
        <>
          <div className="grid gap-6 xl:grid-cols-[.8fr_1.6fr]">
            <Card>
              <CardHeader
                title={t("overview.sleep_score")}
                right={<Badge tone={state.tone}>{t(state.key)}</Badge>}
              />
              <div className="my-6">
                <span className="hero-number num">{fmtNum(s.sleep_score)}</span>
                <span className="ml-3 text-[18px] text-muted">/100</span>
              </div>
              <div className="mt-6 border-t border-hairline">
                <StatPod
                  label={t("sleep.efficiency")}
                  value={fmtNum(
                    inBed && s.total_sleep_s != null
                      ? (s.total_sleep_s / inBed) * 100
                      : null,
                    1,
                  )}
                  unit="%"
                />
              </div>
            </Card>
            <Card>
              <CardHeader title={t("sleep.duration_analysis")} />
              <div className="grid grid-cols-2 gap-x-6">
                <StatPod
                  label={t("sleep.time_asleep")}
                  value={fmtHours(s.total_sleep_s)}
                />
                <StatPod
                  label={t("sleep.time_in_bed")}
                  value={fmtHours(inBed)}
                />
              </div>
              <div className="mt-4">
                <ZoneBar
                  parts={parts.map((p) => ({ ...p, value: p.value ?? 0 }))}
                  height={14}
                />
                <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  {parts.map((p) => (
                    <div key={p.key}>
                      <span className="flex items-center gap-2 text-[12px] text-muted">
                        <span
                          className="h-2 w-2"
                          style={{ background: p.color }}
                        />
                        {t("stage." + p.key)}
                      </span>
                      <p className="num mt-2 text-[20px]">
                        {fmtClock(p.value)}
                      </p>
                      <p className="mt-1 text-[12px] text-muted">
                        {fmtNum(
                          total && p.value != null
                            ? (p.value / total) * 100
                            : null,
                        )}{" "}
                        %
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </div>
          <Card>
            <CardHeader
              title={t("design.sleep_stages")}
              right={
                <Badge>
                  {stages.data?.segments?.length
                    ? t("sleep.stage_epochs")
                    : t("sleep.proportional")}
                </Badge>
              }
            />
            {stages.isLoading ? (
              <Loading />
            ) : stages.isError ? (
              <ErrorNote />
            ) : stages.data?.segments?.length ? (
              <StageTimeline stages={stages.data} />
            ) : (
              <p className="py-8 text-[13px] text-muted">
                {t("design.no_epochs")}
              </p>
            )}
          </Card>
          <Card>
            <CardHeader title={t("design.overnight_signals")} />
            <div className="grid grid-cols-2 gap-6 xl:grid-cols-5">
              <StatPod
                label={t("overview.resting_hr")}
                value={fmtNum(d.biometrics.resting_hr)}
                unit="bpm"
              />
              <StatPod
                label="HRV"
                value={fmtNum(hrv, 1)}
                unit="ms"
                sub={
                  base != null
                    ? t("design.baseline_value", { value: fmtNum(base) })
                    : undefined
                }
              />
              <StatPod
                label={t("overview.spo2")}
                value={fmtNum(s.spo2_avg ?? d.biometrics.spo2_avg, 1)}
                unit="%"
              />
              <StatPod
                label={t("overview.respiration")}
                value={fmtNum(s.respiration_avg, 1)}
                unit="br/min"
              />
              <StatPod
                label={t("sleep.restlessness")}
                value={fmtNum(s.restlessness, 1)}
                unit="%"
              />
            </div>
          </Card>
          <Card>
            <CardHeader
              title={t("sleep.overnight_hrv")}
              right={
                <span className="text-[12px] text-muted">
                  {d.hrv_readings.length} {t("sleep.readings")}
                </span>
              }
            />
            <OvernightHrv day={d} />
          </Card>
          <div className="text-[12px] text-muted">
            {t("design.sleep_note")}
            {s.sources?.length ? " · " + s.sources.join(" / ") : ""}
          </div>
        </>
      )}
    </div>
  );
}
