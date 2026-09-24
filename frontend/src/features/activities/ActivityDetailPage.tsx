/**
 * Activity detail — mockup "cycling_activity_detail": KPI strip, GPS trace
 * (SVG polyline colored by altitude — fully offline, faithful to the
 * approved mockup), synchronized multi-stream timeline (HR / power /
 * cadence / elevation with true values in the tooltip), HR zone bars, lap
 * table, source metrics and formatted conditions.
 */

import { useMemo } from "react";
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
  StatPod,
  fmtDuration,
  fmtNum,
  friendlyDiscipline,
} from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

function paceKmh(distanceM: number | null, durationS: number): number | null {
  if (!distanceM || durationS <= 0) return null;
  return distanceM / 1000 / (durationS / 3600);
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

/* ---------------------------------------------------------------- GPS */

function GpsTrace({ stream }: { stream: StreamOut }) {
  const c = useChartTheme();
  const { t } = useTranslation();
  const lat = stream.columns.lat as (number | null)[] | undefined;
  const lon = stream.columns.lon as (number | null)[] | undefined;
  if (!lat || !lon) return <Empty>{t("activities.no_map")}</Empty>;
  const pts: { x: number; y: number; alt: number }[] = [];
  for (let i = 0; i < lat.length; i++) {
    if (lat[i] !== null && lon[i] !== null) {
      pts.push({ x: lon[i]!, y: lat[i]!, alt: (stream.columns.altitude?.[i] ?? 0) as number });
    }
  }
  if (pts.length < 2) return <Empty>{t("activities.no_map")}</Empty>;

  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxY - minY, 1e-6);
  const W = 1000;
  const H = 380;
  const alts = pts.map((p) => p.alt);
  const aMin = Math.min(...alts);
  const aMax = Math.max(...alts);
  const color = (a: number) => {
    const f = aMax > aMin ? (a - aMin) / (aMax - aMin) : 0.5;
    if (f < 0.33) return c.positive;
    if (f < 0.66) return c.primary;
    return c.alert;
  };
  const segments: { color: string; d: string }[] = [];
  const px = (p: { x: number; y: number }) => ({
    x: ((p.x - minX) / spanX) * (W - 40) + 20,
    y: H - (((p.y - minY) / spanY) * (H - 40) + 20),
  });
  for (let i = 1; i < pts.length; i++) {
    const a = px(pts[i - 1]);
    const b = px(pts[i]);
    segments.push({ color: color(pts[i].alt), d: `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} L ${b.x.toFixed(1)} ${b.y.toFixed(1)}` });
  }
  const startPx = px(pts[0]);
  const endPx = px(pts[pts.length - 1]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-card border border-hairline bg-bg">
      {segments.map((s, i) => (
        <path key={i} d={s.d} stroke={s.color} strokeWidth={2.4} fill="none" strokeLinecap="round" opacity={0.92} />
      ))}
      <circle cx={startPx.x} cy={startPx.y} r={6} fill={c.primary} stroke={c.surface} strokeWidth={2} />
      <circle cx={endPx.x} cy={endPx.y} r={6} fill={c.positive} stroke={c.surface} strokeWidth={2} />
      <text x={16} y={H - 8} fill={c.muted} fontSize={12} fontFamily="JetBrains Mono">
        GPS · {pts.length} pts · ▲ {fmtNum(aMax - aMin, 0)} m
      </text>
    </svg>
  );
}

/* -------------------------------------------------------- weather chips */

const WEATHER_CODES: Record<number, string> = {
  0: "clear", 1: "mostly_clear", 2: "partly_cloudy", 3: "overcast",
  45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
  61: "rain", 63: "rain", 65: "rain", 71: "snow", 73: "snow", 75: "snow",
  80: "showers", 81: "showers", 82: "showers", 95: "storm", 96: "storm", 99: "storm",
};

function ConditionsCard({ weather }: { weather: Record<string, unknown> | null }) {
  const { t } = useTranslation();
  if (!weather) return null;
  const num = (k: string) => {
    const v = weather[k];
    return typeof v === "number" ? v : null;
  };
  const code = num("weather_code");
  const tMax = num("temperature_2m_max");
  const tMin = num("temperature_2m_min");
  const tMean = num("temperature_2m_mean");
  const wind = num("wind_speed_10m_max");
  const precip = num("precipitation_sum");
  const label = code !== null ? t(`weather.${WEATHER_CODES[code] ?? "overcast"}`) : null;
  return (
    <Card>
      <CardHeader eyebrow={t("activities.weather")} title={label} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatPod label={t("weather.temp")} value={fmtNum(tMean, 1)} unit="°C" sub={tMax !== null && tMin !== null ? `${fmtNum(tMin, 0)}° / ${fmtNum(tMax, 0)}°` : undefined} />
        <StatPod label={t("weather.wind")} value={fmtNum(wind, 1)} unit="km/h" />
        <StatPod label={t("weather.precip")} value={fmtNum(precip, 1)} unit="mm" />
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------- page */

export default function ActivityDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const c = useChartTheme();

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

  const seriesDefs = [
    { key: "hr", label: t("activities.hr"), color: c.alert },
    { key: "power", label: t("activities.power"), color: c.primary },
    { key: "cadence", label: t("activities.cadence"), color: c.positive },
    { key: "altitude", label: t("activities.elevation"), color: c.muted },
    { key: "speed", label: t("activities.speed"), color: c.warning },
  ].filter((d) => (streams.data?.columns[d.key] ?? []).some((v) => v !== null));

  const streamOption = useMemo(() => {
    if (!streams.data || seriesDefs.length === 0) return null;
    const { t: ts, columns } = streams.data;
    const labels = ts.map((s) => fmtDuration(s));
    // y-axes: first two series get labeled axes; extras hide labels.
    const yAxes = seriesDefs.map((_d, i) => ({
      type: "value",
      splitLine: { show: i === 0, lineStyle: { color: c.hairline, type: "dashed" } },
      axisLabel: { show: i < 2, color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
    }));
    return {
      grid: { left: 44, right: seriesDefs.length > 1 ? 44 : 12, top: 30, bottom: 44 },
      tooltip: {
        trigger: "axis",
        backgroundColor: c.surface,
        borderColor: c.hairline,
        textStyle: { color: c.ink, fontSize: 11 },
      },
      legend: {
        top: 0,
        left: 0,
        icon: "rect",
        itemWidth: 10,
        itemHeight: 2,
        textStyle: { color: c.muted, fontSize: 10, fontFamily: "Geist" },
        data: seriesDefs.map((d) => d.label),
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6 }],
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: c.muted,
          fontSize: 10,
          fontFamily: "JetBrains Mono",
          interval: Math.max(0, Math.floor(labels.length / 8) - 1),
        },
      },
      yAxis: yAxes,
      series: seriesDefs.map((d, i) => ({
        name: d.label,
        type: "line",
        yAxisIndex: i,
        data: columns[d.key],
        showSymbol: false,
        smooth: 0.25,
        lineStyle: { color: d.color, width: d.key === "altitude" ? 1 : 1.8 },
        itemStyle: { color: d.color },
      })),
    };
  }, [streams.data, c, seriesDefs, t]);

  if (detail.isLoading) return <Loading />;
  if (detail.isError || !detail.data) return <ErrorNote />;
  const a = detail.data;





  const kmh = paceKmh(a.distance_m, a.duration_s);
  const dateStr = new Date(a.start_time).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="flex flex-col gap-4">
      {/* header */}
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/app/activities" className="eyebrow hover:underline">
            ← {t("activities.all")}
          </Link>
          {a.discipline && <Badge tone="primary">{friendlyDiscipline(a.discipline, t)}</Badge>}
          {a.sources.map((s) => (
            <Badge key={s} tone="neutral">{s.toUpperCase()}</Badge>
          ))}
        </div>
        <h1 className="page-title mt-1">{friendlyDiscipline(a.discipline, t)}</h1>
        <div className="num mt-0.5 text-[12px] text-muted">
          {dateStr} ·{" "}
          {new Date(a.start_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
          {a.gear.length > 0 && <> · {a.gear.map((g) => g.name).join(", ")}</>}
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatPod label={t("activities.distance")} value={fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)} unit="km" />
        <StatPod label={t("activities.duration")} value={fmtDuration(a.duration_s)} />
        <StatPod label={t("activities.elevation")} value={`+${fmtNum(a.elevation_gain_m, 0)}`} unit="m" />
        <StatPod
          label={t("activities.np")}
          value={fmtNum(a.np_power ?? a.avg_power, 0)}
          unit="W"
          sub={a.avg_power && a.avg_power > 0 ? `${fmtNum(a.avg_power / 75, 2)} ${t("activities.wkg")}` : undefined}
        />
        <StatPod label={t("activities.speed")} value={fmtNum(kmh, 1)} unit="km/h" sub={`${fmtNum(a.avg_hr)} ${t("common.bpm")}`} />
        <StatPod
          label={t("activities.load")}
          value={fmtNum(a.training_load, 0)}
          unit="TSS"
          sub={`${fmtNum(a.calories, 0)} ${t("common.kcal")}`}
          tone="positive"
        />
      </div>

      {/* GPS — rendered only when the query can actually resolve */}
      {a.has_streams && (
        <Card>
          <CardHeader
            eyebrow={t("activities.map")}
            right={<Badge tone="neutral">{t("activities.altitude_color")}</Badge>}
          />
          {streams.isLoading ? (
            <Loading />
          ) : streams.data ? (
            <GpsTrace stream={streams.data} />
          ) : (
            <Empty>{t("activities.no_map")}</Empty>
          )}
        </Card>
      )}

      {/* synchronized streams */}
      {a.has_streams && streamOption && (
        <Card>
          <CardHeader
            eyebrow={t("activities.streams")}
            title={t("activities.timeline_title")}
            right={<span className="num text-[10px] text-faint">{seriesDefs.length} × {t("activities.channels")}</span>}
          />
          <EChart option={streamOption} height={300} />
        </Card>
      )}

      {/* zones + sources */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {zoneData && (
          <Card>
            <CardHeader
              eyebrow={t("activities.zones")}
              right={
                <span className="num text-[10px] text-faint">
                  HRmax {fmtNum(Math.max(...((streams.data?.columns.hr ?? []) as number[]).filter((v) => !Number.isNaN(v))))} bpm
                </span>
              }
            />
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

        {Object.keys(a.source_metrics ?? {}).length > 0 && (
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
            </div>
          </Card>
        )}
      </div>

      <ConditionsCard weather={a.weather} />

      {/* laps */}
      <Card>
        <CardHeader
          eyebrow={t("activities.laps")}
          right={<span className="num text-[10px] text-faint">{a.laps.length} {t("activities.identified")}</span>}
        />
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
                  <tr key={l.lap_index} className="border-b border-hairline last:border-0 hover:bg-surface2">
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
