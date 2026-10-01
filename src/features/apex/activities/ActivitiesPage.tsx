"use client";

/**
 * Apex Health — Activities list (redesign per plan §3).
 *
 * The page's job: find and review sessions, and see how much you have trained.
 *
 * Layout:
 *   Header: title + range Segmented (30d / 90d / 12m) + Compare / CSV actions
 *   Filter row: discipline multi-select chips (coloured) + source chips + removable
 *     active-filter chips + "Clear filters"
 *   Row 1, Summary strip (col-12): sessions, total time, total distance, total load —
 *     each with a DeltaChip against the previous equal-length window.
 *     Computed server-side in the `summary` block of /api/activities.
 *   Row 2, Weekly volume (col-12): stacked-bar SVG, one column per ISO week,
 *     stacked by discipline. Toggle Hours / Load / Distance. Clicking a column
 *     filters the LIST to that week. Hidden when fewer than 2 weeks of data.
 *   Row 3, The list (col-12): grouped by week, with a sticky week header showing
 *     that week's totals. Each activity is a COMPACT ROW — discipline colour + label
 *     and start time, duration, the primary metric for that sport, avg HR, a load
 *     bar scaled to the heaviest session in the range, a data-completeness dot, and
 *     source chips (main device highlighted). On a phone each row is two lines.
 *   Below the list: "Load more" with "X of Y" counter (offset pagination).
 *
 * All data fetched from /api/activities and /api/activities/weekly.
 * Coherence law: nothing here invents visual vocabulary — every surface is composed
 * from the shared kit (Card, PageHeader, Segmented, DeltaChip, SportIcon,
 * SourcePill, Empty, Loading, Hairline, ApexButton).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { GitCompare, Download, Plus, Loader2, X } from "lucide-react";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  DeltaChip,
  Segmented,
  SportIcon,
  SourcePill,
  Empty,
  Loading,
  Hairline,
  ApexButton,
} from "@/components/apex/kit";
import { ActivityCompareModal } from "@/components/apex/ActivityCompareModal";
import { exportCsv } from "@/lib/apex/csv";
import {
  fmtClock,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtHours,
} from "@/lib/apex/format";
import {
  DISCIPLINE_COLORS,
  DisciplineDot,
  disciplineLabel,
  primaryMetricFor,
  weekKeyForISO,
} from "@/lib/apex/disciplines";
import type { ActivityCard, Locale, Units, WeeklyVolume } from "@/lib/apex/types";

type RangeKey = "30d" | "90d" | "12m";
type VolumeMetric = "hours" | "load" | "distance";

const RANGE_DAYS: Record<RangeKey, number> = { "30d": 30, "90d": 90, "12m": 365 };
const PAGE_SIZE = 60;
const WEEKS_SHOWN = 12;

interface SummaryBlock {
  sessions: number;
  total_time_s: number;
  total_distance_m: number;
  total_load: number;
  prev_sessions: number;
  prev_total_time_s: number;
  prev_total_distance_m: number;
  prev_total_load: number;
}

interface ActivitiesResponse {
  ok: boolean;
  error?: string;
  activities: ActivityCard[];
  count: number;
  total: number;
  offset: number;
  limit: number;
  summary: SummaryBlock;
}

interface WeeklyResponse {
  ok: boolean;
  error?: string;
  weekly: WeeklyVolume[];
}

export function ActivitiesPage() {
  const t = useT();
  const { locale } = useI18n();
  const ui = useApexUi();
  const units: Units = me.units ?? "metric";

  // Filters + range
  const [range, setRange] = useState<RangeKey>("30d");
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [volumeMetric, setVolumeMetric] = useState<VolumeMetric>("hours");
  const [weekFilter, setWeekFilter] = useState<string | null>(null);

  // Data
  const [activities, setActivities] = useState<ActivityCard[]>([]);
  const [summary, setSummary] = useState<SummaryBlock | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [weekly, setWeekly] = useState<WeeklyVolume[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);

  const days = RANGE_DAYS[range];

  // Stable query string for discipline + source params.
  const filterQ = useMemo(() => {
    const d = disciplines.map((x) => `discipline=${encodeURIComponent(x)}`).join("&");
    const s = sources.map((x) => `source=${encodeURIComponent(x)}`).join("&");
    return [d, s].filter(Boolean).join("&");
  }, [disciplines, sources]);

  // Fetch list + summary (offset 0 = replace; >0 = append for Load more).
  const fetchList = useCallback(
    async (off: number, append: boolean) => {
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      try {
        const url = `/api/activities?days=${days}&offset=${off}&limit=${PAGE_SIZE}${
          filterQ ? "&" + filterQ : ""
        }`;
        const res = await fetch(url);
        const data: ActivitiesResponse = await res.json();
        if (!data.ok) throw new Error(data.error || "Failed to load activities");
        setActivities((prev) => (append ? [...prev, ...data.activities] : data.activities));
        setSummary(data.summary);
        setTotal(data.total);
        setOffset(off);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [days, filterQ]
  );

  // Fetch weekly volume (silent failures — it's a supporting view).
  const fetchWeekly = useCallback(async () => {
    try {
      const url = `/api/activities/weekly?weeks=${WEEKS_SHOWN}${filterQ ? "&" + filterQ : ""}`;
      const res = await fetch(url);
      const data: WeeklyResponse = await res.json();
      if (data.ok) setWeekly(data.weekly);
    } catch {
      /* no-op */
    }
  }, [filterQ]);

  // Refetch when filters or range change.
  useEffect(() => {
    setWeekFilter(null);
    fetchList(0, false);
    fetchWeekly();
  }, [fetchList, fetchWeekly]);

  // The discipline + source chips are derived from what's currently loaded —
  // only show filters that have actual data behind them.
  const availableDisciplines = useMemo(() => {
    const set = new Set<string>();
    for (const a of activities) set.add(a.discipline);
    return Array.from(set).sort();
  }, [activities]);

  const availableSources = useMemo(() => {
    const set = new Set<string>();
    for (const a of activities) for (const s of a.sources) set.add(s);
    return Array.from(set).sort();
  }, [activities]);

  // Filter list to the clicked week (ISO week_start), if any.
  const filteredByWeek = useMemo(() => {
    if (!weekFilter) return activities;
    return activities.filter((a) => weekKeyForISO(a.start_time) === weekFilter);
  }, [activities, weekFilter]);

  // Group the filtered list by ISO week.
  const weeklyGroups = useMemo(() => {
    const map = new Map<string, ActivityCard[]>();
    for (const a of filteredByWeek) {
      const k = weekKeyForISO(a.start_time);
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(a);
    }
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [filteredByWeek]);

  // Heaviest session in the loaded range → load-bar scale.
  const maxLoad = useMemo(() => {
    let m = 0;
    for (const a of activities) {
      if (a.training_load !== null && Number.isFinite(a.training_load))
        m = Math.max(m, a.training_load);
    }
    return m;
  }, [activities]);

  // Reset week filter when filters change so the user sees the full list again.
  // (Already handled in the fetchList effect.)

  const hasFilters = disciplines.length > 0 || sources.length > 0 || weekFilter !== null;
  const clearAllFilters = () => {
    setDisciplines([]);
    setSources([]);
    setWeekFilter(null);
  };

  const handleExportCsv = () => {
    exportCsv(
      `apex-activities-${range}`,
      [
        "Date",
        "Time",
        "Discipline",
        "Title",
        "Distance (km)",
        "Duration",
        "Elevation (m)",
        "Avg HR",
        "Avg Power (W)",
        "Load",
        "Sources",
      ],
      filteredByWeek.map((a) => [
        a.local_date,
        fmtClock(a.start_time, locale),
        a.discipline,
        a.title,
        a.distance_m === null ? "" : fmtDistance(a.distance_m, "metric", 2),
        fmtDuration(a.duration_s),
        a.elevation_gain_m ?? "",
        a.avg_hr ?? "",
        a.avg_power ?? "",
        a.training_load ?? "",
        a.sources.join(" + "),
      ])
    );
  };

  return (
    <div className="mx-auto max-w-[1240px]">
      {/* Header */}
      <PageHeader
        title={t("activities.title")}
        subtitle={t("welcome.preview_activities")}
        actions={
          <div className="flex items-center gap-2">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={handleExportCsv}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">CSV</span>
            </ApexButton>
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={() => setCompareOpen(true)}
              icon={<GitCompare size={13} />}
            >
              <span className="hidden sm:inline">Compare</span>
            </ApexButton>
            <Segmented
              value={range}
              onChange={(v) => setRange(v as RangeKey)}
              options={[
                { value: "30d", label: t("act_range_30d") },
                { value: "90d", label: t("act_range_90d") },
                { value: "12m", label: t("act_range_12m") },
              ]}
            />
          </div>
        }
      />
      <ActivityCompareModal open={compareOpen} onOpenChange={setCompareOpen} />

      {/* Filter row */}
      {(availableDisciplines.length > 0 || availableSources.length > 0) && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <FilterGroup label={t("act_filter_discipline")}>
            {availableDisciplines.map((d) => {
              const active = disciplines.includes(d);
              const color = DISCIPLINE_COLORS[d] ?? "var(--c-hairline2)";
              return (
                <FilterChip
                  key={d}
                  active={active}
                  color={color}
                  onClick={() =>
                    setDisciplines((prev) =>
                      active ? prev.filter((x) => x !== d) : [...prev, d]
                    )
                  }
                >
                  <DisciplineDot discipline={d} size={7} />
                  <span>{disciplineLabel(d, locale)}</span>
                </FilterChip>
              );
            })}
          </FilterGroup>

          {availableSources.length > 0 && (
            <FilterGroup label={t("act_filter_source")}>
              {availableSources.map((s) => {
                const active = sources.includes(s);
                return (
                  <FilterChip
                    key={s}
                    active={active}
                    onClick={() =>
                      setSources((prev) =>
                        active ? prev.filter((x) => x !== s) : [...prev, s]
                      )
                    }
                  >
                    <span>{s}</span>
                  </FilterChip>
                );
              })}
            </FilterGroup>
          )}

          {hasFilters && (
            <div className="flex flex-wrap items-center gap-1.5">
              {disciplines.map((d) => (
                <ActiveChip
                  key={`d-${d}`}
                  onClear={() => setDisciplines((prev) => prev.filter((x) => x !== d))}
                >
                  <DisciplineDot discipline={d} size={6} />
                  <span>{disciplineLabel(d, locale)}</span>
                </ActiveChip>
              ))}
              {sources.map((s) => (
                <ActiveChip
                  key={`s-${s}`}
                  onClear={() => setSources((prev) => prev.filter((x) => x !== s))}
                >
                  <span>{s}</span>
                </ActiveChip>
              ))}
              {weekFilter && (
                <ActiveChip
                  key={`w-${weekFilter}`}
                  onClear={() => setWeekFilter(null)}
                >
                  <span>
                    {/* TODO i18n */}
                    Week of {fmtDate(weekFilter, locale)}
                  </span>
                </ActiveChip>
              )}
              <button
                type="button"
                onClick={clearAllFilters}
                className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] px-1.5 py-0.5 text-[11px] font-medium text-muted transition-colors hover:bg-surface2 hover:text-ink"
              >
                <X size={11} />
                {t("act_clear_filters")}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Loading */}
      {loading && <Loading className="mt-6" label="Loading activities…" />}

      {/* Error */}
      {error && !loading && (
        <div className="mt-6">
          <Empty title={error} body="Reload or adjust filters." />
        </div>
      )}

      {/* Row 1: Summary strip */}
      {!loading && !error && summary && (
        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryStat
            label={t("act_summary_sessions")}
            value={String(summary.sessions)}
            delta={summary.sessions - summary.prev_sessions}
          />
          <SummaryStat
            label={t("act_summary_time")}
            value={fmtHours(summary.total_time_s)}
            delta={summary.total_time_s - summary.prev_total_time_s}
          />
          <SummaryStat
            label={t("act_summary_distance")}
            value={fmtDistance(summary.total_distance_m, units, 0)}
            unit={units === "imperial" ? "mi" : "km"}
            delta={summary.total_distance_m - summary.prev_total_distance_m}
          />
          <SummaryStat
            label={t("act_summary_load")}
            value={
              summary.total_load > 0
                ? String(Math.round(summary.total_load))
                : "—"
            }
            delta={
              summary.total_load > 0
                ? summary.total_load - summary.prev_total_load
                : null
            }
          />
        </div>
      )}

      {/* Row 2: Weekly volume */}
      {!loading && !error && weekly.length >= 2 && (
        <Card className="mt-4" pad={false}>
          <div className="flex items-start justify-between gap-3 px-4 pt-4">
            <div>
              <div className="eyebrow">{t("act_weekly_volume")}</div>
              {/* TODO i18n — "last N weeks" */}
              <div className="mt-0.5 text-[12px] text-muted">
                Last {WEEKS_SHOWN} weeks · click a bar to filter the list
              </div>
            </div>
            <Segmented
              size="sm"
              value={volumeMetric}
              onChange={(v) => setVolumeMetric(v as VolumeMetric)}
              options={[
                { value: "hours", label: t("act_volume_hours") },
                { value: "load", label: t("act_volume_load") },
                { value: "distance", label: t("act_volume_distance") },
              ]}
            />
          </div>
          <div className="px-3 pb-3 pt-2">
            <WeeklyVolumeChart
              weekly={weekly}
              metric={volumeMetric}
              selectedWeek={weekFilter}
              onSelectWeek={(k) => setWeekFilter(k === weekFilter ? null : k)}
              locale={locale}
              units={units}
            />
          </div>
        </Card>
      )}

      {/* Row 3: The list, grouped by week */}
      {!loading && !error && (
        <div className="mt-4">
          {weeklyGroups.length === 0 ? (
            <Empty
              title={t("act_no_activities")}
              body={hasFilters ? "Try clearing filters or widening the range." : undefined}
              action={
                hasFilters ? (
                  <ApexButton size="sm" variant="secondary" onClick={clearAllFilters}>
                    {t("act_clear_filters")}
                  </ApexButton>
                ) : undefined
              }
            />
          ) : (
            <>
              {weeklyGroups.map(([weekKey, items]) => (
                <WeekGroup
                  key={weekKey}
                  weekKey={weekKey}
                  items={items}
                  locale={locale}
                  units={units}
                  maxLoad={maxLoad}
                  onRowClick={(id) => {
                    ui.selectActivity(id);
                    ui.setView("activity-detail");
                  }}
                />
              ))}

              {/* Load more */}
              <div className="mt-4 flex flex-col items-center gap-2">
                <div className="num text-[11px] text-faint">
                  {t("act_showing", { shown: activities.length, total })}
                </div>
                {activities.length < total && (
                  <ApexButton
                    size="sm"
                    variant="secondary"
                    onClick={() => fetchList(offset + PAGE_SIZE, true)}
                    disabled={loadingMore}
                    icon={
                      loadingMore ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Plus size={13} />
                      )
                    }
                  >
                    {t("act_load_more")}
                  </ApexButton>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <Hairline className="mt-6 opacity-60" />
      <div className="mt-3 text-[11px] text-faint">
        <span className="num">{t("app.measured")}</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- Filter chips */

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="eyebrow !text-[10px] text-faint">{label}</span>
      {children}
    </div>
  );
}

function FilterChip({
  active,
  color,
  onClick,
  children,
}: {
  active: boolean;
  color?: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`num inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2 py-1 text-[11px] font-medium transition-colors ${
        active
          ? "border-primary bg-primarySoft text-primaryText"
          : "border-hairline bg-surface text-muted hover:bg-surface2 hover:text-ink"
      }`}
    >
      {color && !active && (
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: color }}
        />
      )}
      {children}
    </button>
  );
}

function ActiveChip({
  onClear,
  children,
}: {
  onClear: () => void;
  children: React.ReactNode;
}) {
  return (
    <span className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-surface2 px-1.5 py-0.5 text-[11px] font-medium text-ink2">
      {children}
      <button
        type="button"
        onClick={onClear}
        className="flex h-4 w-4 items-center justify-center rounded-[calc(var(--radius-control)-1px)] text-muted hover:bg-surface3 hover:text-ink"
        aria-label="Remove filter"
      >
        <X size={10} />
      </button>
    </span>
  );
}

/* ----------------------------------------------------------- Summary stat */

function SummaryStat({
  label,
  value,
  unit,
  delta,
}: {
  label: string;
  value: string;
  unit?: string;
  delta: number | null;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-hairline bg-surface2 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="eyebrow truncate !text-[10px]">{label}</div>
        <DeltaChip delta={delta} compact goodWhen="up" showSuffix={false} />
      </div>
      <div className="num mt-1 flex items-baseline gap-1 text-[22px] font-bold leading-7 text-ink tabular-nums">
        {value}
        {unit && <span className="text-[10px] font-medium text-muted">{unit}</span>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- Weekly volume chart */

function WeeklyVolumeChart({
  weekly,
  metric,
  selectedWeek,
  onSelectWeek,
  locale,
  units,
}: {
  weekly: WeeklyVolume[];
  metric: VolumeMetric;
  selectedWeek: string | null;
  onSelectWeek: (weekStart: string) => void;
  locale: Locale;
  units: Units;
}) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);

  // Value accessor per metric.
  const valueOf = (w: WeeklyVolume): number => {
    if (metric === "hours") return w.total_hours;
    if (metric === "load") return w.total_load;
    return w.total_distance_m;
  };

  // Y-axis max: max value across all weeks, with a 10% headroom (min 1 to avoid /0).
  const maxValue = useMemo(() => {
    let m = 0;
    for (const w of weekly) {
      const v =
        metric === "hours" ? w.total_hours : metric === "load" ? w.total_load : w.total_distance_m;
      if (v > m) m = v;
    }
    return m === 0 ? 1 : m * 1.1;
    // metric is captured by valueOf below; explicit dep satisfies the compiler.
  }, [weekly, metric]);

  // SVG layout (viewBox scales to container width via `w-full`).
  const W = 1200;
  const H = 180;
  const padL = 32;
  const padR = 12;
  const padT = 16;
  const padB = 28;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const n = weekly.length;
  const slot = chartW / n;
  const barW = Math.max(6, slot * 0.6);
  const gap = slot - barW;

  // For each discipline present in the data (sorted for stable stacking).
  const disciplines = useMemo(() => {
    const set = new Set<string>();
    for (const w of weekly) for (const k of Object.keys(w.by_discipline)) set.add(k);
    return Array.from(set).sort();
  }, [weekly]);

  // Y-axis ticks: 0, 25%, 50%, 75%, 100% of maxValue.
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  // Y-axis label formatter per metric.
  const fmtY = (v: number): string => {
    if (metric === "hours") return `${v.toFixed(0)}h`;
    if (metric === "load") return String(Math.round(v));
    // Distance: convert to km (or mi).
    if (units === "imperial") return `${(v / 1609.344).toFixed(0)}mi`;
    return `${(v / 1000).toFixed(0)}k`;
  };

  // Column hit-area + per-discipline stacked rects.
  const renderColumn = (w: WeeklyVolume, i: number) => {
    const x = padL + i * slot + gap / 2;
    const total = valueOf(w);
    const isHover = hover === i;
    const isSelected = selectedWeek === w.week_start;

    // Stack segments from bottom up.
    const segs: { y: number; h: number; fill: string; key: string }[] = [];
    let yTop = padT + chartH; // bottom of chart area
    for (const d of disciplines) {
      const dv = w.by_discipline[d];
      const v = dv ? (metric === "hours" ? dv.hours : metric === "load" ? dv.load : dv.distance_m) : 0;
      if (v <= 0) continue;
      const h = (v / maxValue) * chartH;
      yTop -= h;
      segs.push({ y: yTop, h, fill: DISCIPLINE_COLORS[d] ?? "var(--c-hairline2)", key: d });
    }

    return (
      <g
        key={w.week_start}
        onClick={() => onSelectWeek(w.week_start)}
        onMouseEnter={() => setHover(i)}
        onMouseLeave={() => setHover((h) => (h === i ? null : h))}
        style={{ cursor: "pointer" }}
        role="button"
        aria-label={`Week of ${w.week_start}, ${total} ${metric}`}
      >
        {/* Selection / hover band */}
        {(isHover || isSelected) && (
          <rect
            x={padL + i * slot}
            y={padT}
            width={slot}
            height={chartH}
            fill="currentColor"
            className="text-primary"
            fillOpacity={isSelected ? 0.08 : 0.04}
          />
        )}
        {/* Stacked segments */}
        {total > 0 ? (
          segs.map((s, j) => (
            <rect
              key={s.key}
              x={x}
              y={s.y}
              width={barW}
              height={Math.max(0, s.h)}
              fill={s.fill}
              rx={1}
            />
          ))
        ) : (
          // Empty week — show a faint hairline tick so the gap is visible.
          <rect
            x={x}
            y={padT + chartH - 1}
            width={barW}
            height={1}
            fill="currentColor"
            className="text-hairline"
          />
        )}
        {/* Selection outline */}
        {isSelected && (
          <rect
            x={padL + i * slot + 0.5}
            y={padT + 0.5}
            width={slot - 1}
            height={chartH - 1}
            fill="none"
            stroke="currentColor"
            className="text-primary"
            strokeWidth={1}
            rx={2}
          />
        )}
      </g>
    );
  };

  // X-axis labels: week start date, formatted "12 Sep" (or every other week if crowded).
  const labelEvery = n > 16 ? 2 : 1;

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: 180 }}
        preserveAspectRatio="none"
        role="img"
        aria-label="Weekly training volume"
      >
        {/* Horizontal grid lines */}
        {ticks.map((t) => {
          const y = padT + chartH - t * chartH;
          return (
            <g key={t}>
              <line
                x1={padL}
                x2={W - padR}
                y1={y}
                y2={y}
                stroke="currentColor"
                className="text-hairline"
                strokeWidth={1}
                strokeDasharray={t === 0 ? "none" : "2 3"}
              />
              <text
                x={padL - 6}
                y={y + 3}
                textAnchor="end"
                className="num text-faint"
                fontSize={10}
                fill="currentColor"
                style={{ fontFeatureSettings: '"tnum" 1' }}
              >
                {fmtY(t * maxValue)}
              </text>
            </g>
          );
        })}

        {/* Stacked columns */}
        {weekly.map((w, i) => renderColumn(w, i))}

        {/* X-axis baseline */}
        <line
          x1={padL}
          x2={W - padR}
          y1={padT + chartH}
          y2={padT + chartH}
          stroke="currentColor"
          className="text-hairline2"
          strokeWidth={1}
        />

        {/* X-axis labels */}
        {weekly.map((w, i) =>
          i % labelEvery === 0 ? (
            <text
              key={`lbl-${w.week_start}`}
              x={padL + i * slot + slot / 2}
              y={H - 8}
              textAnchor="middle"
              className="num"
              fontSize={10}
              fill="currentColor"
              style={{ fontFeatureSettings: '"tnum" 1' }}
            >
              {fmtDate(w.week_start, locale)}
            </text>
          ) : null
        )}
      </svg>

      {/* Tooltip / hover summary */}
      {hover !== null && weekly[hover] && (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted">
          <span className="num font-medium text-ink">
            {fmtDate(weekly[hover].week_start, locale)}
          </span>
          <span>
            {t("act_volume_hours")}:{" "}
            <span className="num text-ink2">
              {weekly[hover].total_hours.toFixed(1)}h
            </span>
          </span>
          <span>
            {t("act_volume_load")}:{" "}
            <span className="num text-ink2">
              {weekly[hover].total_load > 0 ? Math.round(weekly[hover].total_load) : "—"}
            </span>
          </span>
          <span>
            {t("act_volume_distance")}:{" "}
            <span className="num text-ink2">
              {fmtDistance(weekly[hover].total_distance_m, units, 0)}{" "}
              {units === "imperial" ? "mi" : "km"}
            </span>
          </span>
          <span>
            {t("act_summary_sessions")}:{" "}
            <span className="num text-ink2">{weekly[hover].sessions}</span>
          </span>
        </div>
      )}

      {/* Legend */}
      {disciplines.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {disciplines.map((d) => (
            <span
              key={d}
              className="num inline-flex items-center gap-1.5 text-[10px] text-muted"
            >
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-[2px]"
                style={{ background: DISCIPLINE_COLORS[d] ?? "var(--c-hairline2)" }}
              />
              {disciplineLabel(d, locale)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- Week group + compact row */

function WeekGroup({
  weekKey,
  items,
  locale,
  units,
  maxLoad,
  onRowClick,
}: {
  weekKey: string;
  items: ActivityCard[];
  locale: Locale;
  units: Units;
  maxLoad: number;
  onRowClick: (id: number) => void;
}) {
  // Per-week totals (computed from the items shown — the API returns totals in
  // summary, but the week group only sees its own items, which is what's displayed).
  const weekTotalTime = items.reduce((s, a) => s + (a.duration_s || 0), 0);
  const weekTotalDist = items.reduce(
    (s, a) => s + (a.distance_m ?? 0),
    0
  );
  const weekTotalLoad = items.reduce(
    (s, a) => s + (a.training_load ?? 0),
    0
  );

  return (
    <div className="mb-3">
      {/* Sticky week header */}
      <div className="sticky top-0 z-10 -mx-1 flex items-center justify-between gap-3 border-b border-hairline bg-surface px-1 py-2 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-ink">
            {fmtDate(weekKey, locale)}
          </span>
          {/* TODO i18n — "Week of {date}" */}
          <span className="text-[11px] text-faint">Week of</span>
        </div>
        <div className="num flex items-center gap-3 text-[11px] text-muted tabular-nums">
          <span>
            {items.length} {items.length === 1 ? "session" : "sessions"}
          </span>
          <span className="text-faint" aria-hidden>
            ·
          </span>
          <span>{fmtDuration(weekTotalTime)}</span>
          {weekTotalDist > 0 && (
            <>
              <span className="text-faint" aria-hidden>
                ·
              </span>
              <span>
                {fmtDistance(weekTotalDist, units, 0)} {units === "imperial" ? "mi" : "km"}
              </span>
            </>
          )}
          {weekTotalLoad > 0 && (
            <>
              <span className="text-faint" aria-hidden>
                ·
              </span>
              <span>load {Math.round(weekTotalLoad)}</span>
            </>
          )}
        </div>
      </div>

      {/* Rows */}
      <div>
        {items.map((a) => (
          <ActivityCompactRow
            key={a.id}
            a={a}
            locale={locale}
            units={units}
            maxLoad={maxLoad}
            onClick={() => onRowClick(a.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ActivityCompactRow({
  a,
  locale,
  units,
  maxLoad,
  onClick,
}: {
  a: ActivityCard;
  locale: Locale;
  units: Units;
  maxLoad: number;
  onClick: () => void;
}) {
  const primary = primaryMetricFor(a, locale, units);
  const completeness = a.data_completeness;
  // Source highlight: first source is treated as the main device.
  const mainSource = a.sources[0] ?? null;
  const otherSources = a.sources.slice(1);

  // Load bar width: scaled to heaviest session in the range.
  const loadPct =
    a.training_load !== null && maxLoad > 0
      ? Math.max(2, Math.min(100, (a.training_load / maxLoad) * 100))
      : 0;

  return (
    <div
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      role="button"
      tabIndex={0}
      className="group flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline/50 px-1 py-2 transition-colors last:border-b-0 hover:bg-surface2"
    >
      {/* Discipline dot + label + start time */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: DISCIPLINE_COLORS[a.discipline] ?? "var(--c-hairline2)" }}
        />
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted transition-colors group-hover:bg-primarySoft group-hover:text-primaryText">
          <SportIcon discipline={a.discipline} size={12} />
        </span>
        <div className="min-w-0">
          <div className="truncate text-[12px] font-semibold leading-tight text-ink">
            {disciplineLabel(a.discipline, locale)}
          </div>
          <div className="num text-[10px] text-faint tabular-nums">
            {fmtDate(a.start_time, locale)} · {fmtClock(a.start_time, locale)}
          </div>
        </div>
      </div>

      {/* Duration */}
      <div className="num w-[60px] shrink-0 text-right text-[11px] text-ink2 tabular-nums">
        {fmtDuration(a.duration_s)}
      </div>

      {/* Primary metric (discipline-aware) */}
      <div className="num w-[80px] shrink-0 text-right text-[11px] text-ink2 tabular-nums">
        {primary ? primary.value : <span className="text-faint">—</span>}
      </div>

      {/* Avg HR */}
      <div className="num hidden w-[60px] shrink-0 text-right text-[11px] text-ink2 tabular-nums sm:block">
        {a.avg_hr !== null && Number.isFinite(a.avg_hr) ? (
          `${a.avg_hr}`
        ) : (
          <span className="text-faint">—</span>
        )}
      </div>

      {/* Load bar */}
      <div className="hidden w-[80px] shrink-0 items-center gap-1.5 md:flex">
        <div className="num h-1.5 flex-1 overflow-hidden rounded-full bg-surface3">
          {loadPct > 0 && (
            <div
              className="h-full bg-primary"
              style={{ width: `${loadPct}%` }}
            />
          )}
        </div>
        <span className="num w-[28px] text-right text-[10px] text-muted tabular-nums">
          {a.training_load !== null ? Math.round(a.training_load) : "—"}
        </span>
      </div>

      {/* Completeness dot */}
      <div className="hidden w-[20px] shrink-0 items-center justify-center sm:flex">
        <span
          aria-label={`Data completeness: ${completeness}`}
          title={`Data completeness: ${completeness}`}
          className="inline-block h-2 w-2 rounded-full"
          style={{
            background:
              completeness === "complete"
                ? "var(--c-positive)"
                : completeness === "partial"
                ? "var(--c-warning)"
                : "var(--c-alert)",
          }}
        />
      </div>

      {/* Sources (main highlighted) */}
      <div className="hidden w-[110px] shrink-0 items-center justify-end gap-1 lg:flex">
        {mainSource && (
          <SourcePill key={mainSource}>
            <span className="font-semibold text-ink">{mainSource}</span>
          </SourcePill>
        )}
        {otherSources.map((s) => (
          <SourcePill key={s}>{s}</SourcePill>
        ))}
      </div>

      {/* Mobile-only secondary line: HR + load + sources */}
      <div className="flex w-full items-center gap-3 sm:hidden">
        <div className="num text-[10px] text-muted tabular-nums">
          HR {a.avg_hr ?? "—"}
        </div>
        <div className="num flex items-center gap-1.5 text-[10px] text-muted tabular-nums">
          <span>Load</span>
          <span className="num h-1 flex-1 overflow-hidden rounded-full bg-surface3" style={{ minWidth: 36 }}>
            {loadPct > 0 && (
              <span className="block h-full bg-primary" style={{ width: `${loadPct}%` }} />
            )}
          </span>
          <span className="num w-[24px] text-right">
            {a.training_load !== null ? Math.round(a.training_load) : "—"}
          </span>
        </div>
        <div className="flex flex-1 items-center justify-end gap-1">
          {mainSource && (
            <SourcePill key={mainSource}>
              <span className="font-semibold text-ink">{mainSource}</span>
            </SourcePill>
          )}
          {otherSources.map((s) => (
            <SourcePill key={s}>{s}</SourcePill>
          ))}
        </div>
      </div>
    </div>
  );
}
