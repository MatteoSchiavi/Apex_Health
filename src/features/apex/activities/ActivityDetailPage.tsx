"use client";

/**
 * Apex Health — Activity detail.
 *
 * Route purpose: "What happened in this activity?"
 *
 * The most analytically dense page in the app. Layout (top-to-bottom):
 *   1. Back link
 *   2. PageHeader (title + date · time · discipline + Export)
 *   3. Primary metrics strip — 8 StatPods
 *   4. Two-column grid: GPS Trace (~8 cols) + side panel (~4 cols)
 *      Side panel = Weather + Gear + Sources (source_metrics) + Export
 *   5. Synchronized Timeline Stream — 5 sparkline-style SVG charts stacked
 *      vertically with shared x-axis (HR / Power / Speed / Altitude / Cadence)
 *   6. Heart Rate Zone Distribution — ZoneBar + per-zone legend cards
 *   7. Laps table — 8 rows, Lap # / Start / Duration / Distance / Avg HR / Max
 *      HR / Avg Power / Calories
 *   8. Sources footer — SourcePills per provider
 *
 * Coherence law: every visual primitive comes from the shared kit. The two
 * custom inline SVGs (GpsTrace + StreamChart) are deliberately scoped to this
 * page because they are too specific to live in the kit; they reuse the same
 * tokens (var(--c-primary), tabular-nums, hairlines) so they read as part of
 * the same design system.
 */

import { useMemo, type ReactNode } from "react";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import {
  activities,
  getActivityDetail,
  getActivityStreams,
} from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  StatPod,
  ZoneBar,
  SportIcon,
  Eyebrow,
  SectionHeader,
  Empty,
  SourcePill,
  BackLink,
  ApexButton,
  Hairline,
} from "@/components/apex/kit";
import {
  fmtClock,
  fmtDateLong,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  friendlyDiscipline,
} from "@/lib/apex/format";
import type { ActivityDetail, ActivityStream } from "@/lib/apex/types";

/** Assumed maximum heart rate for zone distribution calculations. */
const MAX_HR = 190;

export function ActivityDetailPage() {
  const t = useT();
  const { locale } = useI18n();
  const ui = useApexUi();
  const id = ui.selectedActivityId ?? activities[0].id;

  const detail: ActivityDetail = useMemo(() => getActivityDetail(id), [id]);
  const streams: ActivityStream = useMemo(() => getActivityStreams(id), [id]);

  return (
    <div className="mx-auto max-w-[1240px]">
      {/* Back link */}
      <BackLink onClick={() => ui.setView("activities")}>
        {t("activities.back_to_list")}
      </BackLink>

      {/* Header */}
      <PageHeader
        className="mt-3"
        title={detail.title}
        subtitle={
          <span className="num">
            {fmtDateLong(detail.start_time, locale)} · {fmtClock(detail.start_time, locale)} ·{" "}
            {friendlyDiscipline(detail.discipline, locale)}
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
              <SportIcon discipline={detail.discipline} size={18} />
            </span>
            <ApexButton variant="secondary" size="sm">
              {t("activities.export")}
            </ApexButton>
          </div>
        }
      />

      {/* Primary metrics strip */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <StatPod
          label={t("activities.distance")}
          value={detail.distance_m === null ? "—" : fmtDistance(detail.distance_m, "metric", 1)}
          unit={detail.distance_m === null ? undefined : "km"}
        />
        <StatPod label={t("activities.duration")} value={fmtDuration(detail.duration_s)} />
        <StatPod
          label={t("activities.elevation")}
          value={detail.elevation_gain_m === null ? "—" : fmtElevation(detail.elevation_gain_m)}
          unit={detail.elevation_gain_m === null ? undefined : "m"}
        />
        <StatPod
          label={t("activities.avg_power")}
          value={detail.avg_power === null ? "—" : detail.avg_power}
          unit={detail.avg_power === null ? undefined : "W"}
        />
        <StatPod
          label={t("activities.avg_hr")}
          value={detail.avg_hr === null ? "—" : detail.avg_hr}
          unit={detail.avg_hr === null ? undefined : "bpm"}
        />
        <StatPod
          label={t("activities.max_hr")}
          value={detail.max_hr === null ? "—" : detail.max_hr}
          unit={detail.max_hr === null ? undefined : "bpm"}
        />
        <StatPod
          label={t("activities.calories")}
          value={detail.calories === null ? "—" : detail.calories}
          unit={detail.calories === null ? undefined : "kcal"}
        />
        <StatPod
          label={t("activities.col_load")}
          value={detail.training_load === null ? "—" : detail.training_load}
          tone="primary"
        />
      </div>

      {/* GPS trace + side panel */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card pad={false} className="overflow-hidden lg:col-span-8">
          <div className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
            <div>
              <div className="eyebrow">{t("activities.map")}</div>
              <div className="num mt-0.5 text-[11px] text-faint">
                {detail.route !== null ? `${detail.route.length} pts` : "—"}
              </div>
            </div>
            {detail.route !== null && (
              <div className="flex items-center gap-3 text-[10px] text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full bg-positive" />
                  {t("activities.gps_start")}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full bg-alert" />
                  {t("activities.gps_end")}
                </span>
              </div>
            )}
          </div>
          <div className="p-4">
            {detail.route === null ? (
              <Empty title={t("activities.no_map")} />
            ) : (
              <GpsTrace route={detail.route} />
            )}
          </div>
        </Card>

        <div className="space-y-4 lg:col-span-4">
          {/* Weather */}
          <Card>
            <CardHeader eyebrow={t("activities.weather")} />
            {detail.weather ? (
              <div className="grid grid-cols-2 gap-2.5">
                <WeatherStat label={t("activities.conditions")} value={detail.weather.conditions} />
                <WeatherStat label={t("activities.temp_c")} value={`${detail.weather.temp_c}°`} />
                <WeatherStat label={t("activities.wind_kph")} value={`${detail.weather.wind_kph} km/h`} />
                <WeatherStat label={t("activities.humidity_pct")} value={`${detail.weather.humidity_pct}%`} />
              </div>
            ) : (
              <Empty title="—" />
            )}
          </Card>

          {/* Gear */}
          <Card>
            <CardHeader eyebrow={t("activities.gear")} />
            {detail.gear.length === 0 ? (
              <div className="text-[12px] text-faint">—</div>
            ) : (
              <ul className="space-y-2">
                {detail.gear.map((g) => (
                  <li key={g.id} className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted">
                        <SportIcon discipline={detail.discipline} size={11} />
                      </span>
                      <span className="truncate text-[12px] text-ink2">{g.name}</span>
                    </div>
                    <span className="num shrink-0 text-[10px] uppercase tracking-[0.06em] text-faint">{g.type}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Sources */}
          <Card>
            <CardHeader eyebrow={t("activities.sources")} />
            <ul className="space-y-1.5">
              {Object.entries(detail.source_metrics).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="text-muted">{t("activities.source_metric")}: {k.replace(/_/g, " ")}</span>
                  <SourcePill>{v}</SourcePill>
                </li>
              ))}
            </ul>
            <div className="mt-3 border-t border-hairline pt-3">
              <ApexButton variant="secondary" size="sm" className="w-full">
                {t("activities.export")}
              </ApexButton>
            </div>
          </Card>
        </div>
      </div>

      {/* Synchronized Timeline Stream */}
      <Card pad={false} className="mt-6 overflow-hidden">
        <div className="border-b border-hairline px-4 py-3">
          <SectionHeader
            eyebrow={t("activities.streams")}
            right={
              <div className="num text-[10px] text-faint">
                {fmtDuration(detail.duration_s)} · {streams.t.length} samples
              </div>
            }
            className="mb-0"
          />
        </div>
        <div className="space-y-1 p-4">
          <StreamChart
            label={t("activities.hr")}
            unit="bpm"
            data={streams.columns.hr}
            color="var(--c-alert)"
          />
          <StreamChart
            label={t("activities.power")}
            unit="W"
            data={streams.columns.power}
            color="var(--c-primary)"
            emptyLabel={t("activities.no_power")}
          />
          <StreamChart
            label={t("activities.speed_stream")}
            unit="km/h"
            data={streams.columns.speed}
            color="var(--c-positive)"
            emptyLabel={t("activities.no_power")}
          />
          <StreamChart
            label={t("activities.altitude")}
            unit="m"
            data={streams.columns.alt}
            color="var(--c-text-2)"
          />
          <StreamChart
            label={t("activities.cadence")}
            unit="rpm"
            data={streams.columns.cadence}
            color="var(--c-warning)"
          />
          {/* Shared time axis */}
          <div className="flex items-center gap-3 pt-2">
            <div className="w-20 shrink-0" />
            <div className="num flex flex-1 justify-between text-[10px] text-faint">
              <span>00:00</span>
              <span>{fmtDuration(detail.duration_s / 4)}</span>
              <span>{fmtDuration(detail.duration_s / 2)}</span>
              <span>{fmtDuration((detail.duration_s * 3) / 4)}</span>
              <span>{fmtDuration(detail.duration_s)}</span>
            </div>
            <div className="w-28 shrink-0" />
          </div>
        </div>
      </Card>

      {/* Heart Rate Zone Distribution */}
      <Card className="mt-6">
        <CardHeader
          eyebrow={t("activities.zones")}
          right={
            <span className="num text-[10px] text-faint">
              {t("activities.zone_pct")} · max HR {MAX_HR}
            </span>
          }
        />
        <HrZones hrData={streams.columns.hr} t={t} />
      </Card>

      {/* Laps table */}
      <Card pad={false} className="mt-6 overflow-hidden">
        <div className="border-b border-hairline px-4 py-3">
          <div className="eyebrow">{t("activities.laps")}</div>
        </div>
        <div className="overflow-x-auto scroll-area">
          <table className="w-full min-w-[640px] border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-hairline bg-surface2 text-left">
                <LapTh className="w-[56px]">{t("activities.lap")}</LapTh>
                <LapTh className="w-[80px]">{t("activities.col_start")}</LapTh>
                <LapTh className="w-[80px] text-right">{t("activities.duration")}</LapTh>
                <LapTh className="w-[80px] text-right">{t("activities.distance")}</LapTh>
                <LapTh className="w-[72px] text-right">{t("activities.avg_hr")}</LapTh>
                <LapTh className="w-[72px] text-right">{t("activities.max_hr")}</LapTh>
                <LapTh className="w-[88px] text-right">{t("activities.avg_power")}</LapTh>
                <LapTh className="w-[80px] text-right">{t("activities.calories")}</LapTh>
              </tr>
            </thead>
            <tbody>
              {detail.laps.map((lap) => (
                <tr
                  key={lap.lap_index}
                  className="border-b border-hairline/60 transition-colors last:border-b-0 hover:bg-surface2"
                >
                  <LapTd className="num font-semibold text-primaryText">{lap.lap_index}</LapTd>
                  <LapTd className="num text-ink2">
                    {lap.start_time === null ? "—" : fmtClock(lap.start_time, locale)}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.duration_s === null ? "—" : fmtDuration(lap.duration_s)}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.distance_m === null ? <span className="text-faint">—</span> : fmtDistance(lap.distance_m, "metric", 2)}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.avg_hr === null ? <span className="text-faint">—</span> : lap.avg_hr}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.max_hr === null ? <span className="text-faint">—</span> : lap.max_hr}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.avg_power === null ? <span className="text-faint">—</span> : `${lap.avg_power} W`}
                  </LapTd>
                  <LapTd className="num text-right tabular-nums text-ink2">
                    {lap.calories === null ? <span className="text-faint">—</span> : lap.calories}
                  </LapTd>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Sources footer */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Eyebrow>{t("activities.source_label")}</Eyebrow>
        {detail.sources.map((s) => (
          <SourcePill key={s}>{s}</SourcePill>
        ))}
      </div>

      <Hairline className="mt-6 opacity-60" />
    </div>
  );
}

/* ----------------------------------------------------------- inline components */

function WeatherStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2.5 py-2">
      <div className="eyebrow !text-[9px] truncate">{label}</div>
      <div className="num mt-1 text-[14px] font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function LapTh({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <th className={`eyebrow !text-[10px] !font-semibold px-3 py-2.5 ${className}`}>{children}</th>;
}

function LapTd({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-3 py-2.5 ${className}`}>{children}</td>;
}

/* ----------------------------------------------------------- GPS trace SVG */

function GpsTrace({ route }: { route: { lat: number; lng: number; ele: number | null }[] }) {
  if (route.length < 2) return null;

  const lats = route.map((p) => p.lat);
  const lngs = route.map((p) => p.lng);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const latRange = maxLat - minLat || 1e-6;
  const lngRange = maxLng - minLng || 1e-6;

  const W = 800;
  const H = 460;
  const padding = 32;

  // Preserve the route's actual aspect ratio inside the viewBox.
  const routeAspect = lngRange / latRange;
  const innerW = W - padding * 2;
  const innerH = H - padding * 2;
  const boxAspect = innerW / innerH;
  let drawW: number, drawH: number;
  if (routeAspect > boxAspect) {
    drawW = innerW;
    drawH = drawW / routeAspect;
  } else {
    drawH = innerH;
    drawW = drawH * routeAspect;
  }
  const offX = (W - drawW) / 2;
  const offY = (H - drawH) / 2;

  const pts = route.map((p) => {
    const x = offX + ((p.lng - minLng) / lngRange) * drawW;
    // Invert y so that north (higher lat) is at the top
    const y = offY + (1 - (p.lat - minLat) / latRange) * drawH;
    return { x, y };
  });

  const path = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join(" ");
  const firstPt = pts[0];
  const lastPt = pts[pts.length - 1];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      preserveAspectRatio="xMidYMid meet"
      aria-label="GPS trace"
    >
      <defs>
        <pattern id="gpsGridMinor" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0 L0 0 0 20" fill="none" stroke="var(--c-hairline)" strokeWidth="0.5" />
        </pattern>
        <pattern id="gpsGridMajor" width="100" height="100" patternUnits="userSpaceOnUse">
          <path d="M100 0 L0 0 0 100" fill="none" stroke="var(--c-hairline-strong)" strokeWidth="0.7" />
        </pattern>
        <linearGradient id="gpsBg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-surface-2)" />
          <stop offset="100%" stopColor="var(--c-surface-3)" />
        </linearGradient>
      </defs>

      {/* Map background — tonal separation + subtle gridlines */}
      <rect width={W} height={H} fill="url(#gpsBg)" />
      <rect width={W} height={H} fill="url(#gpsGridMinor)" />
      <rect width={W} height={H} fill="url(#gpsGridMajor)" />

      {/* Outer hairline frame */}
      <rect
        x="0.5"
        y="0.5"
        width={W - 1}
        height={H - 1}
        fill="none"
        stroke="var(--c-hairline-strong)"
        strokeWidth="0.5"
      />

      {/* Route area fill — primarySoft */}
      <path
        d={`${path} L${lastPt.x.toFixed(2)},${H} L${firstPt.x.toFixed(2)},${H} Z`}
        fill="var(--c-primary)"
        fillOpacity={0.07}
        stroke="none"
      />

      {/* Route line — primary */}
      <path
        d={path}
        fill="none"
        stroke="var(--c-primary)"
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Start marker (green) */}
      <circle
        cx={firstPt.x}
        cy={firstPt.y}
        r="7"
        fill="var(--c-positive)"
        stroke="var(--c-surface)"
        strokeWidth="2.5"
      />
      {/* End marker (red) */}
      <circle
        cx={lastPt.x}
        cy={lastPt.y}
        r="7"
        fill="var(--c-alert)"
        stroke="var(--c-surface)"
        strokeWidth="2.5"
      />

      {/* Compass rose top-right */}
      <g transform={`translate(${W - 40}, 40)`}>
        <circle cx="0" cy="0" r="16" fill="var(--c-surface)" stroke="var(--c-hairline-strong)" strokeWidth="0.6" />
        <path d="M0,-11 L-3.5,3 L0,-1 L3.5,3 Z" fill="var(--c-primary)" />
        <text x="0" y="-18" textAnchor="middle" fontSize="9" fill="var(--c-text-muted)" fontWeight="700">
          N
        </text>
      </g>

      {/* Scale bar bottom-left */}
      <g transform={`translate(28, ${H - 28})`}>
        <line x1="0" y1="0" x2="60" y2="0" stroke="var(--c-text-muted)" strokeWidth="1.5" />
        <line x1="0" y1="-3" x2="0" y2="3" stroke="var(--c-text-muted)" strokeWidth="1.5" />
        <line x1="60" y1="-3" x2="60" y2="3" stroke="var(--c-text-muted)" strokeWidth="1.5" />
        <text x="30" y="-6" textAnchor="middle" fontSize="9" fill="var(--c-text-muted)" fontWeight="600">
          1 km
        </text>
      </g>
    </svg>
  );
}

/* ----------------------------------------------------------- Synchronized stream chart */

function StreamChart({
  label,
  unit,
  data,
  color,
  emptyLabel,
}: {
  label: string;
  unit: string;
  data: (number | null)[];
  color: string;
  emptyLabel?: string;
}) {
  const points = data.filter((v): v is number => v !== null && Number.isFinite(v));
  const hasData = points.length >= 2;

  const W = 1000;
  const H = 38;
  const stepX = W / Math.max(1, data.length - 1);

  let path = "";
  let min = 0;
  let max = 0;
  let avg = 0;
  let lastX = 0;
  let lastY = 0;

  if (hasData) {
    min = Math.min(...points);
    max = Math.max(...points);
    avg = Math.round(points.reduce((a, b) => a + b, 0) / points.length);
    const range = max - min || 1;
    let started = false;
    path = data
      .map((v, i) => {
        if (v === null || !Number.isFinite(v)) return "";
        const x = i * stepX;
        const y = H - 4 - ((v - min) / range) * (H - 8);
        if (!started) {
          started = true;
          lastX = x;
          lastY = y;
          return `M${x.toFixed(2)},${y.toFixed(2)}`;
        }
        lastX = x;
        lastY = y;
        return `L${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .filter(Boolean)
      .join(" ");
  }

  return (
    <div className="flex items-center gap-3 border-b border-hairline/60 pb-1 last:border-b-0">
      <div className="w-20 shrink-0">
        <div className="eyebrow !text-[10px] truncate">{label}</div>
      </div>
      <div className="h-9 min-w-0 flex-1">
        {hasData ? (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="h-9 w-full"
            preserveAspectRatio="none"
            aria-hidden
          >
            <path
              d={`${path} L${lastX.toFixed(2)},${H} L0,${H} Z`}
              fill={color}
              fillOpacity={0.08}
              stroke="none"
            />
            <path
              d={path}
              fill="none"
              stroke={color}
              strokeWidth={1.3}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
            <circle cx={lastX} cy={lastY} r={2.4} fill={color} vectorEffect="non-scaling-stroke" />
          </svg>
        ) : (
          <div className="flex h-9 items-center text-[11px] italic text-faint">
            {emptyLabel ?? "—"}
          </div>
        )}
      </div>
      <div className="num w-28 shrink-0 text-right text-[11px]">
        {hasData ? (
          <>
            <span className="font-semibold tabular-nums text-ink">{avg}</span>
            <span className="text-faint"> {unit}</span>
            <div className="tabular-nums text-[9px] text-faint">
              {min}–{max}
            </div>
          </>
        ) : (
          <span className="text-faint">—</span>
        )}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- HR zone distribution */

type ZoneKey = "zone_z1" | "zone_z2" | "zone_z3" | "zone_z4" | "zone_z5";

function HrZones({
  hrData,
  t,
}: {
  hrData: (number | null)[];
  t: (path: string, vars?: Record<string, string | number>) => string;
}) {
  const zoneData = useMemo(() => {
    const valid = hrData.filter((v): v is number => v !== null && Number.isFinite(v));
    const total = valid.length || 1;
    const counts = [0, 0, 0, 0, 0];
    for (const v of valid) {
      const pct = v / MAX_HR;
      if (pct < 0.6) counts[0]++;
      else if (pct < 0.7) counts[1]++;
      else if (pct < 0.8) counts[2]++;
      else if (pct < 0.9) counts[3]++;
      else counts[4]++;
    }
    return counts.map((c) => (c / total) * 100);
  }, [hrData]);

  // Calm → intense: primary → positive → warning → alert → deeper alert
  const colors = [
    "var(--c-primary)",
    "var(--c-positive)",
    "var(--c-warning)",
    "var(--c-alert)",
    "color-mix(in srgb, var(--c-alert) 75%, #000)",
  ];
  const zoneKeys: ZoneKey[] = ["zone_z1", "zone_z2", "zone_z3", "zone_z4", "zone_z5"];
  const labels = zoneKeys.map((k) => t(`activities.${k}`));
  const hrRanges = [
    `<${Math.round(0.6 * MAX_HR)}`,
    `${Math.round(0.6 * MAX_HR)}–${Math.round(0.7 * MAX_HR) - 1}`,
    `${Math.round(0.7 * MAX_HR)}–${Math.round(0.8 * MAX_HR) - 1}`,
    `${Math.round(0.8 * MAX_HR)}–${Math.round(0.9 * MAX_HR) - 1}`,
    `${Math.round(0.9 * MAX_HR)}+`,
  ];

  const segments = zoneData.map((z, i) => ({
    label: labels[i],
    value: z,
    color: colors[i],
  }));

  return (
    <div>
      <ZoneBar segments={segments} height={12} />
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-5">
        {zoneData.map((z, i) => (
          <div
            key={i}
            className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2.5 py-2"
          >
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: colors[i] }} />
              <span className="eyebrow !text-[10px] truncate">{labels[i]}</span>
            </div>
            <div className="num mt-1 text-[16px] font-bold tabular-nums text-ink">
              {z.toFixed(0)}
              <span className="text-[10px] font-medium text-muted">%</span>
            </div>
            <div className="num mt-0.5 text-[10px] text-faint">{hrRanges[i]} bpm</div>
          </div>
        ))}
      </div>
    </div>
  );
}
