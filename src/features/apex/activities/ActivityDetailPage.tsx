"use client";

/**
 * Apex Health — Activity detail.
 *
 * Route purpose: "What happened in this activity?"
 *
 * The most analytically dense page in the app. Layout (top-to-bottom):
 *   1. Back link
 *   2. PageHeader (title + date · time · discipline + Export)
 *   3. Primary metrics strip — 8 metric tiles
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

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import {
  activities,
  getActivityDetail,
  getActivityStreams,
} from "@/lib/apex/data";
import {
  Card,
  PageHeader,
  ZoneBar,
  SportIcon,
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
  // Lap-hover state: when the user hovers a lap row, StreamCharts highlights
  // the corresponding time range with a tinted band.
  const [hoveredLap, setHoveredLap] = useState<{ startIdx: number; endIdx: number } | null>(null);
  // Pinned lap: when the user clicks a lap row, the band stays even after mouse-leave.
  const [pinnedLap, setPinnedLap] = useState<{ startIdx: number; endIdx: number } | null>(null);

  const detail: ActivityDetail = useMemo(() => getActivityDetail(id), [id]);
  const streams: ActivityStream = useMemo(() => getActivityStreams(id), [id]);

  // Convert a lap (start_time + duration_s) to stream-index range
  const lapToIndexRange = (lap: { start_time: string | null; duration_s: number | null }) => {
    if (!lap.start_time || !lap.duration_s) return null;
    const lapStartMs = new Date(lap.start_time).getTime();
    const activityStartMs = new Date(detail.start_time).getTime();
    const lapEndMs = lapStartMs + lap.duration_s * 1000;
    const activityEndMs = activityStartMs + detail.duration_s * 1000;
    const totalMs = activityEndMs - activityStartMs;
    if (totalMs <= 0) return null;
    const samples = streams.t.length;
    const startIdx = Math.max(0, Math.round(((lapStartMs - activityStartMs) / totalMs) * (samples - 1)));
    const endIdx = Math.min(samples - 1, Math.round(((lapEndMs - activityStartMs) / totalMs) * (samples - 1)));
    return { startIdx, endIdx };
  };

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
            <ApexButton variant="secondary" size="sm" onClick={() => window.print()}>
              {t("activities.export")}
            </ApexButton>
          </div>
        }
      />

      {/* Primary metrics strip */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <div>
          <div className="text-[14px] text-ink2">{t("activities.distance")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.distance_m === null ? "—" : fmtDistance(detail.distance_m, "metric", 1)}</span>
            {detail.distance_m !== null && <span className="text-[14px] text-ink2">km</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.duration")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{fmtDuration(detail.duration_s)}</span>
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.elevation")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.elevation_gain_m === null ? "—" : fmtElevation(detail.elevation_gain_m)}</span>
            {detail.elevation_gain_m !== null && <span className="text-[14px] text-ink2">m</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.avg_power")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.avg_power === null ? "—" : detail.avg_power}</span>
            {detail.avg_power !== null && <span className="text-[14px] text-ink2">W</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.avg_hr")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.avg_hr === null ? "—" : detail.avg_hr}</span>
            {detail.avg_hr !== null && <span className="text-[14px] text-ink2">bpm</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.max_hr")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.max_hr === null ? "—" : detail.max_hr}</span>
            {detail.max_hr !== null && <span className="text-[14px] text-ink2">bpm</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.calories")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.calories === null ? "—" : detail.calories}</span>
            {detail.calories !== null && <span className="text-[14px] text-ink2">kcal</span>}
          </div>
        </div>
        <div>
          <div className="text-[14px] text-ink2">{t("activities.col_load")}</div>
          <div className="num mt-1 flex items-baseline gap-1 text-ink">
            <span className="text-[28px] font-semibold">{detail.training_load === null ? "—" : detail.training_load}</span>
          </div>
        </div>
      </div>

      {/* GPS trace + side panel */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card pad={false} className="overflow-hidden lg:col-span-8">
          <div className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
            <div>
              <div className="text-[14px] font-medium text-ink2">{t("activities.map")}</div>
              <div className="num mt-0.5 text-[12px] text-faint">
                {detail.route !== null ? `${detail.route.length} pts` : "—"}
              </div>
            </div>
            {detail.route !== null && (
              <div className="flex items-center gap-3 text-[12px] text-muted">
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
            <div className="mb-3 text-[14px] font-medium text-ink2">{t("activities.weather")}</div>
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
            <div className="mb-3 text-[14px] font-medium text-ink2">{t("activities.gear")}</div>
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
                    <span className="num shrink-0 text-[12px] tracking-[0.06em] text-faint">{g.type}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Sources */}
          <Card>
            <div className="mb-3 text-[14px] font-medium text-ink2">{t("activities.sources")}</div>
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
          <div className="mb-0 flex items-baseline justify-between gap-3">
            <div className="text-[14px] font-medium text-ink2">{t("activities.streams")}</div>
            <div className="num text-[12px] text-faint">
              {fmtDuration(detail.duration_s)} · {streams.t.length} samples
            </div>
          </div>
        </div>
        <StreamCharts
          streams={streams}
          startTime={detail.start_time}
          duration_s={detail.duration_s}
          t={t}
          lapRange={hoveredLap ?? pinnedLap}
        />
      </Card>

      {/* Heart Rate Zone Distribution */}
      <Card className="mt-6">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div className="text-[14px] font-medium text-ink2">{t("activities.zones")}</div>
          <span className="num text-[12px] text-faint">
            {t("activities.zone_pct")} · max HR {MAX_HR}
          </span>
        </div>
        <HrZones hrData={streams.columns.hr} t={t} />
      </Card>

      {/* Laps table */}
      <Card pad={false} className="mt-6 overflow-hidden">
        <div className="border-b border-hairline px-4 py-3">
          <div className="text-[14px] font-medium text-ink2">{t("activities.laps")}</div>
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
              {detail.laps.map((lap) => {
                const range = lapToIndexRange(lap);
                const isPinned = pinnedLap && range && pinnedLap.startIdx === range.startIdx && pinnedLap.endIdx === range.endIdx;
                return (
                  <tr
                    key={lap.lap_index}
                    className={`border-b border-hairline/60 transition-colors last:border-b-0 hover:bg-surface2 ${isPinned ? "bg-primarySoft/40" : ""}`}
                    onMouseEnter={() => {
                      if (range) setHoveredLap(range);
                    }}
                    onMouseLeave={() => setHoveredLap(null)}
                    onClick={() => {
                      // Toggle pin: if already pinned, unpin; otherwise pin this lap.
                      if (isPinned) {
                        setPinnedLap(null);
                      } else if (range) {
                        setPinnedLap(range);
                      }
                    }}
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
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Sources footer */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="text-[14px] font-medium text-ink2">{t("activities.source_label")}</div>
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
    <div className="rounded-[var(--radius-control)] bg-surface2 px-2.5 py-2">
      <div className="truncate text-[14px] font-medium text-ink2">{label}</div>
      <div className="num mt-1 text-[14px] font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}

function LapTh({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <th className={`text-[14px] font-semibold text-ink2 px-3 py-2.5 ${className}`}>{children}</th>;
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

/* ----------------------------------------------------------- Multi-line stream chart */

/**
 * StreamCharts — single chart with all metrics overlaid as multi-colored lines.
 * Each metric is normalized to its own min/max range so they can share one
 * chart without one metric dominating the others.
 *
 * Hover shows a crosshair + tooltip with all 5 metric values at that time.
 * Lap range highlight shows as a tinted band.
 */
function StreamCharts({
  streams,
  startTime,
  duration_s,
  t,
  lapRange,
}: {
  streams: ActivityStream;
  startTime: string;
  duration_s: number;
  t: (p: string) => string;
  lapRange?: { startIdx: number; endIdx: number } | null;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const endTime = new Date(new Date(startTime).getTime() + duration_s * 1000).toISOString();
  const streamCount = streams.t.length;
  const hoverPct = hoverIdx !== null ? (hoverIdx / Math.max(1, streamCount - 1)) * 100 : 0;

  // Define the metrics to plot
  const metrics = [
    { key: "hr", label: t("activities.hr"), unit: "bpm", data: streams.columns.hr, color: "var(--c-alert)" },
    { key: "power", label: t("activities.power"), unit: "W", data: streams.columns.power, color: "var(--c-primary)" },
    { key: "speed", label: t("activities.speed_stream"), unit: "km/h", data: streams.columns.speed, color: "var(--c-positive)" },
    { key: "alt", label: t("activities.altitude"), unit: "m", data: streams.columns.alt, color: "var(--c-text-2)" },
    { key: "cadence", label: t("activities.cadence"), unit: "rpm", data: streams.columns.cadence, color: "var(--c-warning)" },
  ].filter((m) => m.data.some((v) => v !== null && Number.isFinite(v)));

  // Chart dimensions
  const W = 1000;
  const H = 200;
  const padL = 48;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Compute normalized paths for each metric
  const metricPaths = metrics.map((m) => {
    const validData = m.data.filter((v): v is number => v !== null && Number.isFinite(v));
    if (validData.length < 2) return { ...m, path: "", min: 0, max: 0 };
    const min = Math.min(...validData);
    const max = Math.max(...validData);
    const range = max - min || 1;
    const stepX = plotW / Math.max(1, m.data.length - 1);
    let path = "";
    let started = false;
    m.data.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) return;
      const x = padL + i * stepX;
      const y = padT + plotH - ((v - min) / range) * plotH;
      if (!started) { path += `M${x.toFixed(1)},${y.toFixed(1)}`; started = true; }
      else { path += ` L${x.toFixed(1)},${y.toFixed(1)}`; }
    });
    return { ...m, path, min, max };
  });

  // Hover tooltip data
  const hoverTimeStr = hoverIdx !== null
    ? (() => {
        try {
          const startMs = new Date(startTime).getTime();
          const endMs = new Date(endTime).getTime();
          const tMs = startMs + ((endMs - startMs) * hoverIdx) / Math.max(1, streamCount - 1);
          return new Date(tMs).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
        } catch { return null; }
      })()
    : null;

  // Mouse handler
  const handleMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relX = (e.clientX - rect.left) / rect.width;
    setHoverIdx(Math.max(0, Math.min(streamCount - 1, Math.round(relX * (streamCount - 1)))));
  };

  // X-axis time labels
  const xLabels = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const ms = new Date(startTime).getTime() + duration_s * f * 1000;
    return new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  });

  return (
    <div className="relative p-4" ref={containerRef}>
      {/* Legend */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {metricPaths.map((m) => (
          <div key={m.key} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: m.color }} />
            <span className="text-[12px] font-medium text-muted">{m.label}</span>
            <span className="num text-[12px] text-faint">{Math.round(m.min)}–{Math.round(m.max)}</span>
          </div>
        ))}
      </div>

      {/* Lap range band */}
      {lapRange && (
        <div
          className="pointer-events-none absolute top-[60px] bottom-[50px] z-10 bg-primarySoft border-x border-primary/30"
          style={{
            left: `calc(16px + (100% - 32px) * ${lapRange.startIdx / Math.max(1, streamCount - 1)})`,
            width: `calc((100% - 32px) * ${(lapRange.endIdx - lapRange.startIdx) / Math.max(1, streamCount - 1)})`,
          }}
          aria-hidden
        />
      )}

      {/* The chart */}
      <div onMouseMove={handleMove} onMouseLeave={() => setHoverIdx(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }} preserveAspectRatio="none">
          {/* Grid lines (horizontal) */}
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1={padL} y1={padT + plotH * f} x2={W - padR} y2={padT + plotH * f}
              stroke="var(--c-hairline)" strokeWidth="0.5" strokeDasharray="2 3" />
          ))}

          {/* Multi-line paths */}
          {metricPaths.map((m) => (
            <path key={m.key} d={m.path} fill="none" stroke={m.color} strokeWidth="1.5"
              strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          ))}

          {/* Hover crosshair */}
          {hoverIdx !== null && (
            <>
              <line
                x1={padL + hoverPct / 100 * plotW} y1={padT}
                x2={padL + hoverPct / 100 * plotW} y2={padT + plotH}
                stroke="var(--c-text-muted)" strokeWidth="0.5" strokeDasharray="2 3"
                vectorEffect="non-scaling-stroke"
              />
              {/* Dots at hover position for each metric */}
              {metricPaths.map((m) => {
                const v = m.data[hoverIdx];
                if (v === null || !Number.isFinite(v)) return null;
                const range = m.max - m.min || 1;
                const y = padT + plotH - ((v - m.min) / range) * plotH;
                return (
                  <circle key={m.key} cx={padL + hoverPct / 100 * plotW} cy={y} r="3"
                    fill={m.color} stroke="var(--c-surface)" strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke" />
                );
              })}
            </>
          )}
        </svg>
      </div>

      {/* X-axis labels */}
      <div className="num mt-1 flex justify-between px-12 text-[12px] text-faint">
        {xLabels.map((label, i) => <span key={i}>{label}</span>)}
      </div>

      {/* Hover tooltip */}
      {hoverIdx !== null && hoverTimeStr && (
        <div
          className="pointer-events-none absolute z-30 w-[220px] rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
          style={{
            top: 8,
            left: hoverPct > 65 ? undefined : `calc(${hoverPct}% - 110px)`,
            right: hoverPct > 65 ? `calc(${100 - hoverPct}% - 110px)` : undefined,
          }}
          role="status" aria-live="polite"
        >
          <div className="flex items-center justify-between border-b border-hairline px-3 py-1.5">
            <span className="text-[14px] font-medium text-ink2">{hoverTimeStr}</span>
            <span className="num text-[12px] text-faint">{hoverIdx + 1}/{streamCount}</span>
          </div>
          <ul className="px-3 py-1.5">
            {metricPaths.map((m) => {
              const v = m.data[hoverIdx];
              return (
                <li key={m.key} className="flex items-center justify-between gap-2 py-0.5 text-[12px]">
                  <span className="flex items-center gap-1.5 min-w-0">
                    <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: m.color }} />
                    <span className="text-muted truncate">{m.label}</span>
                  </span>
                  <span className="num font-semibold tabular-nums shrink-0"
                    style={{ color: v === null || !Number.isFinite(v) ? "var(--c-text-faint)" : "var(--c-text)" }}>
                    {v === null || !Number.isFinite(v) ? "—" : `${Math.round(v)} ${m.unit}`}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
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
            className="rounded-[var(--radius-control)] bg-surface2 px-2.5 py-2"
          >
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: colors[i] }} />
              <span className="truncate text-[14px] font-medium text-ink2">{labels[i]}</span>
            </div>
            <div className="num mt-1 text-[16px] font-bold tabular-nums text-ink">
              {z.toFixed(0)}
              <span className="text-[12px] font-medium text-muted">%</span>
            </div>
            <div className="num mt-0.5 text-[12px] text-faint">{hrRanges[i]} bpm</div>
          </div>
        ))}
      </div>
    </div>
  );
}
