/**
 * Activity detail — mockup "cycling_activity_detail": KPI strip, GPS trace
 * (SVG contour trace colored by elevation, faithful to the approved mockup
 * and fully offline), synchronized stream chart, HR zone bars, lap
 * table, source metrics (Whoop strain etc.), weather and gear.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { api, type ActivityDetail as Detail, type StreamOut } from "../../app/api";
import {
  Badge,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Loading,
  fmtDuration,
  fmtNum,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

function paceKmh(distanceM: number | null, durationS: number): number | null {
  if (!distanceM || durationS <= 0) return null;
  return (distanceM / 1000) / (durationS / 3600);
}

/** HR zone distribution computed from the stream (5 zones off HRmax). */
function zonesFromStream(t: number[], hr: (number | null)[]): { name: string; minutes: number; pct: number }[] | null {
  const values = hr.filter((v): v is number => v !== null);
  if (values.length < 10) return null;
  const hrmax = Math.max(...values);
  const bounds = [0, 0.6, 0.7, 0.8, 0.9, 1.0].map((f) => f * hrmax);
  const counts = [0, 0, 0, 0, 0];
  let n = 0;
  for (const v of values) {
    for (let z = 4; z >= 0; z--) {
      if (v > bounds[z] && v <= bounds[z + 1]) {
        counts[z]++;
        n++;
        break;
      }
    }
  }
  const names = ["Z1", "Z2", "Z3", "Z4", "Z5"];
  return counts.map((c, i) => ({
    name: names[i],
    minutes: (c / n) * (t[t.length - 1] / 60),
    pct: (c / n) * 100,
  }));
}

function GpsTrace({ stream }: { stream: StreamOut | null }) {
  const c = useChartTheme();
  const { t } = useTranslation();
  if (!stream || !stream.columns.lat || !stream.columns.lon) {
    return <Empty>{t("activities.no_map")}</Empty>;
  }
  const lat = stream.columns.lat as (number | null)[];
  const lon = stream.columns.lon as (number | null)[];
  const pts: { x: number; y: number; alt: number }[] = [];
  for (let i = 0; i < lat.length; i++) {
    if (lat[i] !== null && lon[i] !== null) {
      pts.push({ x: lon[i]!, y: lat[i]!, alt: (stream.columns.altitude?.[i] ?? 0) as number });
    }
  }
  if (pts.length < 2) return <Empty>{t("activities.no_map")}</Empty>;

  // Normalize to the viewBox; color segments by altitude terciles.
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxY - minY, 1e-6);
  const W = 1000, H = 400;
  const alts = pts.map((p) => p.alt);
  const aMin = Math.min(...alts), aMax = Math.max(...alts);
  const color = (a: number) => {
    const f = aMax > aMin ? (a - aMin) / (aMax - aMin) : 0.5;
    if (f < 0.33) return c.positive;
    if (f < 0.66) return c.primary;
    return c.alert;
  };
  // Segmented polylines by color
  const segments: { color: string; d: string }[] = [];
  for (let i = 1; i < pts.length; i++) {
    const x1 = ((pts[i - 1].x - minX) / spanX) * (W - 40) + 20;
    const y1 = H - (((pts[i - 1].y - minY) / spanY) * (H - 40) + 20);
    const x2 = ((pts[i].x - minX) / spanX) * (W - 40) + 20;
    const y2 = H - (((pts[i].y - minY) / spanY) * (H - 40) + 20);
    segments.push({ color: color(pts[i].alt), d: `M ${x1} ${y1} L ${x2} ${y2}` });
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-card border border-hairline bg-bg">
      {segments.map((s, i) => (
        <path key={i} d={s.d} stroke={s.color} strokeWidth={2.2} fill="none" strokeLinecap="round" opacity={0.9} />
      ))}
      <circle cx={((pts[0].x - minX) / spanX) * (W - 40) + 20} cy={H - (((pts[0].y - minY) / spanY) * (H - 40) + 20)} r={6} fill={c.primary} stroke={c.surface} strokeWidth={2} />
      <circle cx={((pts[pts.length - 1].x - minX) / spanX) * (W - 40) + 20} cy={H - (((pts[pts.length - 1].y - minY) / spanY) * (H - 40) + 20)} r={6} fill={c.positive} stroke={c.surface} strokeWidth={2} />
      <text x={16} y={H - 8} fill={c.muted} fontSize={12} fontFamily="JetBrains Mono">
        {t("activities.map")} · {pts.length} pts · ▲ {fmtNum(aMax - aMin, 0)} {t("common.m")}
      </text>
    </svg>
  );
}

export default function ActivityDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const c = useChartTheme();
  const [activeStream, setActiveStream] = useState<"hr" | "power" | "cadence" | "speed" | "altitude">("hr");

  const detail = useQuery({
    queryKey: ["activity", id],
    queryFn: () => api.get<Detail>(`/activities/${id}`),
    enabled: !!id,
  });
  const streams = useQuery({
    queryKey: ["streams", id],
    queryFn: () => api.get<StreamOut>(`/activities/${id}/streams`),
    enabled: !!id && (detail.data?.has_streams ?? false),
  });

  const zoneData = useMemo(() => {
    if (!streams.data) return null;
    const { t: ts, columns } = streams.data;
    return zonesFromStream(ts, (columns.hr ?? []) as (number | null)[]);
  }, [streams.data]);

  if (detail.isLoading) return <Loading />;
  if (detail.isError || !detail.data) return <ErrorNote />;
  const a = detail.data;

  const seriesKeys = streams.data
    ? (Object.keys(streams.data.columns) as string[]).filter(
        (k) => (streams.data!.columns[k] ?? []).some((v) => v !== null),
      )
    : [];
  const active = (seriesKeys.includes(activeStream) ? activeStream : seriesKeys[0]) as
    | "hr"
    | "power"
    | "cadence"
    | "speed"
    | "altitude"
    | undefined;

  function buildStreamOption() {
    if (!streams.data || !active) return null;
    const { t: ts, columns } = streams.data;
    const labels = ts.map((s) => fmtDuration(s));
    return {
      grid: { left: 40, right: 12, top: 24, bottom: 46 },
      tooltip: {
        trigger: "axis",
        backgroundColor: c.surface,
        borderColor: c.hairline,
        textStyle: { color: c.ink, fontSize: 11 },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono", interval: Math.max(0, Math.floor(labels.length / 8) - 1) },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
        axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
      },
      series: [
        {
          name: t(`activities.${active === "altitude" ? "elevation" : active}`),
          type: "line",
          data: columns[active],
          showSymbol: false,
          smooth: 0.2,
          lineStyle: { color: c.primary, width: 1.8 },
          itemStyle: { color: c.primary },
          areaStyle:
            active === "altitude"
              ? { color: "transparent" }
              : { color: c.primary, opacity: 0.08 },
        },
      ],
    };
  }

  const streamOption = buildStreamOption();

  const kmh = paceKmh(a.distance_m, a.duration_s);

  return (
    <div className="flex flex-col gap-4">
      {/* header */}
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/app/activities" className="eyebrow hover:underline">
            ← {t("activities.all")}
          </Link>
          {a.discipline && <Badge tone="primary">{a.discipline}</Badge>}
          {a.sources.map((s) => (
            <Badge key={s} tone="neutral">{s}</Badge>
          ))}
        </div>
        <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">
          {new Date(a.start_time).toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        </h1>
        <div className="num mt-0.5 text-[12px] text-muted">
          {new Date(a.start_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
          {a.gear.length > 0 && <> · {a.gear.map((g) => g.name).join(", ")}</>}
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label={t("activities.distance")} value={`${fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)}`} unit="km" />
        <Kpi label={t("activities.duration")} value={fmtDuration(a.duration_s)} />
        <Kpi label={t("activities.elevation")} value={`+${fmtNum(a.elevation_gain_m, 0)}`} unit="m" />
        <Kpi
          label={t("activities.np")}
          value={fmtNum(a.np_power ?? a.avg_power, 0)}
          unit="W"
          sub={a.avg_power && a.avg_power > 0 ? `${fmtNum(a.avg_power / 75, 2)} ${t("activities.wkg")}` : undefined}
        />
        <Kpi
          label={t("activities.speed")}
          value={fmtNum(kmh, 1)}
          unit="km/h"
          sub={`${fmtNum(a.avg_hr)} ${t("common.bpm")}`}
        />
        <Kpi
          label={t("activities.load")}
          value={fmtNum(a.training_load, 0)}
          unit="TSS"
          sub={`${fmtNum(a.calories, 0)} ${t("common.kcal")}`}
          tone="positive"
        />
      </div>

      {/* GPS */}
      <Card>
        <CardHeader eyebrow={t("activities.map")} />
        {streams.data ? (
          <GpsTrace stream={streams.data} />
        ) : (
          <Empty>{t("common.loading")}</Empty>
        )}
      </Card>

      {/* streams */}
      {a.has_streams && (
        <Card>
          <CardHeader
            eyebrow={t("activities.streams")}
            right={
              <div className="flex gap-1.5">
                {(["hr", "power", "cadence", "speed", "altitude"] as const).map((k) =>
                  seriesKeys.includes(k) ? (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setActiveStream(k)}
                      className={`rounded-sm px-2 py-1 text-[11px] font-medium ${
                        active === k ? "bg-surface3 text-ink" : "text-muted hover:text-ink2"
                      }`}
                    >
                      {t(`activities.${k === "altitude" ? "altitude" : k}`)}
                    </button>
                  ) : null,
                )}
              </div>
            }
          />
          {streamOption ? <EChart option={streamOption} height={300} /> : <Empty>{t("biometrics.no_data")}</Empty>}
        </Card>
      )}

      {/* zones + source metrics */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {zoneData && (
          <Card>
            <CardHeader eyebrow={t("activities.zones")} />
            <div className="flex flex-col gap-2.5">
              {zoneData.map((z) => (
                <div key={z.name} className="flex items-center gap-3">
                  <span className="num w-7 text-[11px] font-bold text-muted">{z.name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-hairline">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${z.pct}%`,
                        background: ["var(--c-stage-deep)", "var(--c-stage-core)", "var(--c-stage-rem)", "var(--c-warning)", "var(--c-alert)"][
                          Number(z.name.slice(1)) - 1
                        ],
                      }}
                    />
                  </div>
                  <span className="num w-16 text-right text-[11px] text-muted">
                    {fmtNum(z.minutes, 0)} min
                  </span>
                </div>
              ))}
            </div>
          </Card>
        )}

        {(Object.keys(a.source_metrics ?? {}).length > 0 || a.weather) && (
          <Card>
            <CardHeader eyebrow={t("activities.sources")} />
            <div className="flex flex-col gap-3">
              {Object.entries(a.source_metrics ?? {}).map(([provider, meta]) => (
                <div key={provider} className="rounded-card border border-hairline bg-surface2 p-3">
                  <div className="eyebrow mb-1.5">{provider}</div>
                  <div className="num grid grid-cols-2 gap-x-4 gap-y-1 text-[12px] text-ink2 md:grid-cols-3">
                    {Object.entries(meta as Record<string, unknown>)
                      .filter(([, v]) => v !== null && typeof v !== "object")
                      .slice(0, 9)
                      .map(([k, v]) => (
                        <span key={k} className="truncate">
                          {k.replace(/_/g, " ")}: <span className="font-semibold text-ink">{String(v)}</span>
                        </span>
                      ))}
                  </div>
                </div>
              ))}
              {a.weather && (
                <div className="rounded-card border border-hairline bg-surface2 p-3">
                  <div className="eyebrow mb-1.5">{t("activities.weather")}</div>
                  <div className="num text-[12px] text-ink2">
                    {Object.entries(a.weather)
                      .filter(([, v]) => v !== null && typeof v !== "object")
                      .slice(0, 6)
                      .map(([k, v]) => `${k}: ${String(v)}`)
                      .join(" · ")}
                  </div>
                </div>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* laps */}
      <Card>
        <CardHeader eyebrow={t("activities.laps")} />
        {a.laps.length === 0 ? (
          <Empty>{t("activities.no_laps")}</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-hairline text-left">
                  <th className="eyebrow py-2 pr-3">{t("activities.lap")}</th>
                  <th className="eyebrow py-2 pr-3">{t("activities.duration")}</th>
                  <th className="eyebrow py-2 pr-3">{t("activities.distance")}</th>
                  <th className="eyebrow py-2 pr-3">{t("activities.avg_hr")}</th>
                  <th className="eyebrow py-2 pr-3">{t("activities.max_hr")}</th>
                  <th className="eyebrow py-2 pr-3">{t("activities.avg_power")}</th>
                  <th className="eyebrow py-2">{t("activities.calories")}</th>
                </tr>
              </thead>
              <tbody className="num text-ink2">
                {a.laps.map((l) => (
                  <tr key={l.lap_index} className="border-b border-hairline last:border-0">
                    <td className="py-2 pr-3 font-semibold text-ink">L{l.lap_index}</td>
                    <td className="py-2 pr-3">{fmtDuration(l.duration_s)}</td>
                    <td className="py-2 pr-3">{fmtNum(l.distance_m ? l.distance_m / 1000 : null, 2)} km</td>
                    <td className="py-2 pr-3">{fmtNum(l.avg_hr)}</td>
                    <td className="py-2 pr-3">{fmtNum(l.max_hr)}</td>
                    <td className="py-2 pr-3">{fmtNum(l.avg_power, 0)}</td>
                    <td className="py-2">{fmtNum(l.calories, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Kpi({
  label,
  value,
  unit,
  sub,
  tone = "ink",
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  tone?: "ink" | "positive";
}) {
  return (
    <Card className="!p-3">
      <div className="eyebrow truncate">{label}</div>
      <div className={`num mt-1 text-[20px] font-bold ${tone === "positive" ? "text-positiveText" : "text-ink"}`}>
        {value}
        {unit && <span className="ml-1 text-[10px] font-medium text-muted">{unit}</span>}
      </div>
      {sub && <div className="num mt-0.5 text-[10px] text-faint">{sub}</div>}
    </Card>
  );
}
