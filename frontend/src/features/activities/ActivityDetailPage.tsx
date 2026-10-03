import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  useMap,
} from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  api,
  type ActivityDetail as Detail,
  type StreamOut,
} from "../../app/api";
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
  fmtDuration,
  fmtNum,
  friendlyDiscipline,
} from "../../components/kit";
import { Tabs } from "../../components/Tabs";
import { useUnits } from "../../components/data";
import { EChart, useChartTheme } from "../../components/charts/EChart";
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(points as LatLngBoundsExpression, { padding: [24, 24] });
  }, [map, points]);
  return null;
}
function GpsTrace({ stream }: { stream: StreamOut }) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const points = useMemo(() => {
    const coords: [number, number][] = [];
    stream.columns.lat?.forEach((lat, i) => {
      const lon = stream.columns.lon?.[i];
      if (
        lat != null &&
        lon != null &&
        Number.isFinite(lat) &&
        Number.isFinite(lon) &&
        Math.abs(lat) <= 90 &&
        Math.abs(lon) <= 180
      )
        coords.push([lat, lon]);
    });
    return coords;
  }, [stream]);
  if (points.length < 2) return <Empty>{t("activities.no_map")}</Empty>;
  return (
    <div className="h-[300px] overflow-hidden md:h-[380px]">
      <MapContainer
        center={points[0]}
        zoom={13}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Polyline
          positions={points}
          pathOptions={{ color: c.ink, weight: 3 }}
        />
        <CircleMarker
          center={points[0]}
          radius={5}
          pathOptions={{
            color: c.surface,
            fillColor: c.ink,
            fillOpacity: 1,
            weight: 2,
          }}
        />
        <CircleMarker
          center={points.at(-1)!}
          radius={5}
          pathOptions={{
            color: c.surface,
            fillColor: c.primary,
            fillOpacity: 1,
            weight: 2,
          }}
        />
        <FitBounds points={points} />
      </MapContainer>
    </div>
  );
}
function Timeline({ stream }: { stream: StreamOut }) {
  const { t } = useTranslation();
  const c = useChartTheme();
  const units = useUnits();
  const [channel, setChannel] = useState("hr");
  const defs = [
    {
      key: "hr",
      label: t("activities.hr"),
      unit: "bpm",
      convert: (v: number) => v,
    },
    {
      key: "power",
      label: t("activities.power"),
      unit: "W",
      convert: (v: number) => v,
    },
    {
      key: "cadence",
      label: t("activities.cadence"),
      unit: "rpm",
      convert: (v: number) => v,
    },
    {
      key: "altitude",
      label: t("activities.altitude"),
      unit: units.elevationUnit,
      convert: (v: number) => units.elevation(v)!,
    },
    {
      key: "speed",
      label: t("activities.speed"),
      unit: units.speedUnit,
      convert: (v: number) => units.speed(v * 3.6)!,
    },
  ].filter((d) => stream.columns[d.key]?.some((v) => v != null));
  const active = defs.find((d) => d.key === channel) ?? defs[0];
  if (!active) return <Empty>{t("design.no_streams")}</Empty>;
  return (
    <Card>
      <CardHeader
        title={t("design.session_timeline")}
        right={<span className="text-[12px] text-muted">{active.unit}</span>}
      />
      <Tabs
        value={active.key}
        onChange={setChannel}
        options={defs.map((d) => ({ value: d.key, label: d.label }))}
        label={t("activities.streams")}
      />
      <div
        className="mt-4"
        role="img"
        aria-label={active.label + " · " + active.unit}
      >
        <EChart
          height={260}
          option={{
            animation: false,
            grid: { left: 48, right: 16, top: 20, bottom: 45 },
            tooltip: {
              trigger: "axis",
              confine: true,
              backgroundColor: c.surface,
              borderColor: c.hairline,
              textStyle: { color: c.ink, fontSize: 13 },
              valueFormatter: (v: number) => fmtNum(v, 1) + " " + active.unit,
            },
            dataZoom: [
              { type: "inside" },
              {
                type: "slider",
                height: 12,
                bottom: 0,
                borderColor: c.hairline,
                handleSize: 12,
                textStyle: { color: c.muted },
              },
            ],
            xAxis: {
              type: "category",
              data: stream.t.map(fmtDuration),
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
                name: active.label,
                type: "line",
                data: stream.columns[active.key].map((v) =>
                  v == null ? null : active.convert(v),
                ),
                smooth: false,
                connectNulls: false,
                showSymbol: false,
                lineStyle: { color: c.ink, width: 1.8 },
                itemStyle: { color: c.ink },
              },
            ],
          }}
        />
      </div>
      <p className="mt-5 text-[12px] text-muted">
        {t("design.stream_note", { count: stream.t.length })}
      </p>
    </Card>
  );
}
const WEATHER_CODES: Record<number, string> = {
  0: "clear",
  1: "mostly_clear",
  2: "partly_cloudy",
  3: "overcast",
  45: "fog",
  48: "fog",
  51: "drizzle",
  53: "drizzle",
  55: "drizzle",
  61: "rain",
  63: "rain",
  65: "rain",
  71: "snow",
  73: "snow",
  75: "snow",
  80: "showers",
  81: "showers",
  82: "showers",
  95: "storm",
  96: "storm",
  99: "storm",
};
export default function ActivityDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const units = useUnits();
  const timezone = useUi((s) => s.me?.timezone);
  const [tab, setTab] = useState("session");
  const detail = useQuery({
    queryKey: ["activity", id],
    queryFn: () => api.get<Detail>("/activities/" + id),
    enabled: !!id,
  });
  const streams = useQuery({
    queryKey: ["streams", id],
    queryFn: () => api.get<StreamOut>("/activities/" + id + "/streams"),
    enabled: !!detail.data?.has_streams,
  });
  if (detail.isLoading) return <Loading />;
  if (detail.isError || !detail.data) return <ErrorNote />;
  const a = detail.data;
  const water = [
    "sailing",
    "kitesurf",
    "windsurf",
    "surf",
    "wakeboard",
  ].includes(a.discipline ?? "");
  const weather = a.weather;
  const weatherNum = (key: string) =>
    typeof weather?.[key] === "number" ? (weather[key] as number) : null;
  const code = weatherNum("weather_code");
  return (
    <div className="flex flex-col gap-6">
      <Link to="/app/activities" className="text-link text-muted">
        <ArrowLeft size={16} />
        {t("activities.all")}
      </Link>
      <PageHeader
        title={friendlyDiscipline(a.discipline, t)}
        subtitle={new Date(a.start_time).toLocaleString(undefined, {
          weekday: "long",
          day: "numeric",
          month: "long",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: timezone,
        })}
        actions={<Badge>{a.data_completeness}</Badge>}
      />
      <div className="stat-row">
        <StatPod
          label={t("activities.duration")}
          value={fmtDuration(a.duration_s)}
        />
        <StatPod
          label={t("activities.distance")}
          value={fmtNum(units.distance(a.distance_m), 2)}
          unit={units.distanceUnit}
        />
        <StatPod
          label={t("activities.avg_hr")}
          value={fmtNum(a.avg_hr)}
          unit="bpm"
        />
        <StatPod
          label={t("activities.load")}
          value={fmtNum(a.training_load)}
          unit="TSS"
        />
      </div>
      <Tabs
        value={tab}
        onChange={setTab}
        label={t("activities.detail_title")}
        options={[
          { value: "session", label: t("design.session") },
          { value: "laps", label: t("activities.laps") },
          { value: "sources", label: t("activities.sources") },
        ]}
      />
      {tab === "session" && (
        <>
          <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader title={t("activities.map")} />
              {streams.isLoading ? (
                <Loading />
              ) : streams.isError ? (
                <ErrorNote />
              ) : streams.data ? (
                <GpsTrace stream={streams.data} />
              ) : (
                <Empty>{t("activities.no_map")}</Empty>
              )}
            </Card>
            <Card>
              <CardHeader title={t("design.session_metrics")} />
              <div className="grid grid-cols-2 gap-x-6">
                {!water && (
                  <StatPod
                    label={t("activities.elevation")}
                    value={fmtNum(units.elevation(a.elevation_gain_m))}
                    unit={units.elevationUnit}
                  />
                )}
                <StatPod
                  label={t("activities.max_hr")}
                  value={fmtNum(a.max_hr)}
                  unit="bpm"
                />
                <StatPod
                  label={t("activities.avg_power")}
                  value={fmtNum(a.avg_power)}
                  unit="W"
                />
                <StatPod
                  label={t("activities.np")}
                  value={fmtNum(a.np_power)}
                  unit="W"
                />
                <StatPod
                  label={t("activities.speed")}
                  value={fmtNum(
                    units.speed(
                      a.distance_m != null && a.duration_s > 0
                        ? (a.distance_m / a.duration_s) * 3.6
                        : null,
                    ),
                    1,
                  )}
                  unit={units.speedUnit}
                />
                <StatPod
                  label={t("activities.calories")}
                  value={fmtNum(a.calories)}
                  unit="kcal"
                />
              </div>
              {a.gear.length > 0 && (
                <p className="mt-5 border-t border-hairline pt-4 text-[13px] text-muted">
                  {t("activities.gear")}: {a.gear.map((g) => g.name).join(", ")}
                </p>
              )}
            </Card>
          </div>
          {streams.isLoading ? (
            <Loading />
          ) : streams.isError ? (
            <ErrorNote />
          ) : streams.data ? (
            <Timeline stream={streams.data} />
          ) : (
            <Card>
              <Empty>{t("design.no_streams")}</Empty>
            </Card>
          )}
          {weather && (
            <Card>
              <CardHeader
                title={t("activities.weather")}
                right={
                  code != null && WEATHER_CODES[code]
                    ? t("weather." + WEATHER_CODES[code])
                    : undefined
                }
              />
              <div className="grid grid-cols-2 gap-6 md:grid-cols-3">
                <StatPod
                  label={t("weather.temp")}
                  value={fmtNum(weatherNum("temperature_2m_mean"), 1)}
                  unit="°C"
                  sub={
                    weatherNum("temperature_2m_min") != null &&
                    weatherNum("temperature_2m_max") != null
                      ? fmtNum(weatherNum("temperature_2m_min")) +
                        "° / " +
                        fmtNum(weatherNum("temperature_2m_max")) +
                        "°"
                      : undefined
                  }
                />
                <StatPod
                  label={t("weather.wind")}
                  value={fmtNum(
                    units.speed(weatherNum("wind_speed_10m_max")),
                    1,
                  )}
                  unit={units.speedUnit}
                />
                <StatPod
                  label={t("weather.precip")}
                  value={fmtNum(weatherNum("precipitation_sum"), 1)}
                  unit="mm"
                />
              </div>
            </Card>
          )}
        </>
      )}
      {tab === "laps" && (
        <Card>
          {!a.laps.length ? (
            <Empty>{t("activities.no_laps")}</Empty>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    {[
                      "lap",
                      "duration",
                      "distance",
                      "avg_hr",
                      "max_hr",
                      "avg_power",
                      "calories",
                    ].map((k) => (
                      <th key={k}>{t("activities." + k)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {a.laps.map((l) => (
                    <tr key={l.lap_index}>
                      <td>{l.lap_index}</td>
                      <td>{fmtDuration(l.duration_s)}</td>
                      <td>
                        {fmtNum(units.distance(l.distance_m), 2)}{" "}
                        {units.distanceUnit}
                      </td>
                      <td>{fmtNum(l.avg_hr)} bpm</td>
                      <td>{fmtNum(l.max_hr)} bpm</td>
                      <td>{fmtNum(l.avg_power)} W</td>
                      <td>{fmtNum(l.calories)} kcal</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      {tab === "sources" && (
        <Card>
          <CardHeader
            title={t("activities.sources")}
            right={
              <span className="text-[13px] text-muted">
                {a.sources.join(" · ")}
              </span>
            }
          />
          {!Object.keys(a.source_metrics ?? {}).length ? (
            <Empty>{t("design.no_source_metrics")}</Empty>
          ) : (
            Object.entries(a.source_metrics ?? {}).map(([provider, meta]) => (
              <div key={provider} className="mb-6">
                <h2 className="section-label mb-4">{provider}</h2>
                <dl className="grid gap-x-8 md:grid-cols-2">
                  {Object.entries(meta)
                    .filter(([, v]) => v != null)
                    .map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-start justify-between gap-4 border-t border-hairline py-3 text-[13px]"
                      >
                        <dt className="text-muted">{k.replaceAll("_", " ")}</dt>
                        <dd className="num max-w-[60%] break-words text-right">
                          {typeof v === "object"
                            ? JSON.stringify(v)
                            : String(v)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </div>
            ))
          )}
        </Card>
      )}
    </div>
  );
}
