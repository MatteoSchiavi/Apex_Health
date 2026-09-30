"use client";

/**
 * Apex Health — Activities list.
 *
 * Route purpose: "What have I done?"
 *
 * A compact, analytical table — not dozens of activity cards. The user gets a
 * high-density scan of every session in the selected window, with discipline
 * filter chips and a time-range segmented control. Rows are clickable; opening
 * one fires `ui.selectActivity(id)` + `ui.setView("activity-detail")`.
 *
 * Coherence law: nothing in this file invents visual vocabulary — every
 * surface is composed from the shared kit (Card, PageHeader, Segmented,
 * SportIcon, SourcePill, Badge, Empty, Hairline).
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { GitCompare, Search, X, ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { activities } from "@/lib/apex/data";
import {
  Card,
  PageHeader,
  Segmented,
  SportIcon,
  SourcePill,
  Badge,
  Empty,
  Hairline,
  ApexButton,
} from "@/components/apex/kit";
import { ActivityCompareModal } from "@/components/apex/ActivityCompareModal";
import {
  fmtClock,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  friendlyDiscipline,
} from "@/lib/apex/format";
import type { ActivityCard, Locale } from "@/lib/apex/types";

type RangeKey = "30d" | "90d" | "12m";
type FilterKey = "all" | "cycling" | "running" | "strength" | "swimming" | "other";
type SortKey = "date" | "distance" | "duration" | "elevation" | "avg_hr" | "avg_power" | "load";
type SortDir = "asc" | "desc";

const RANGE_DAYS: Record<RangeKey, number> = {
  "30d": 30,
  "90d": 90,
  "12m": 365,
};

/** Returns the numeric value for a given sort key, or null if missing. */
function sortValue(a: ActivityCard, key: SortKey): number | null {
  switch (key) {
    case "date": return new Date(a.start_time).getTime();
    case "distance": return a.distance_m;
    case "duration": return a.duration_s;
    case "elevation": return a.elevation_gain_m;
    case "avg_hr": return a.avg_hr;
    case "avg_power": return a.avg_power;
    case "load": return a.training_load;
  }
}

/** Returns true if an activity matches the discipline filter. "Other" pools rowing+hiking+walking. */
function matchesFilter(discipline: ActivityCard["discipline"], filter: FilterKey): boolean {
  if (filter === "all") return true;
  if (filter === "other") return discipline === "rowing" || discipline === "hiking" || discipline === "walking";
  return discipline === filter;
}

export function ActivitiesPage() {
  const t = useT();
  const { locale } = useI18n();
  const ui = useApexUi();
  const [range, setRange] = useState<RangeKey>("30d");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [compareOpen, setCompareOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const searchRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut: "/" focuses search input (when not already in an input)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    const now = Date.now();
    const cutoffMs = RANGE_DAYS[range] * 24 * 3600 * 1000;
    const q = search.trim().toLowerCase();
    const out = activities.filter((a) => {
      const ageMs = now - new Date(a.start_time).getTime();
      if (ageMs > cutoffMs) return false;
      if (!matchesFilter(a.discipline, filter)) return false;
      if (q && !(a.title.toLowerCase().includes(q) || a.discipline.toLowerCase().includes(q))) return false;
      return true;
    });
    // Sort by active key + direction. Nulls always last regardless of direction.
    out.sort((a, b) => {
      const va = sortValue(a, sortKey);
      const vb = sortValue(b, sortKey);
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      const cmp = va - vb;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return out;
  }, [range, filter, search, sortKey, sortDir]);

  /** Toggle sort: same column flips direction, new column defaults to desc (asc for date). */
  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "date" ? "desc" : "desc");
    }
  };

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader
        title={t("activities.title")}
        subtitle={t("welcome.preview_activities")}
        actions={
          <div className="flex items-center gap-2">
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
                { value: "30d", label: t("activities.30d") },
                { value: "90d", label: t("activities.90d") },
                { value: "12m", label: t("activities.12m") },
              ]}
            />
          </div>
        }
      />
      <ActivityCompareModal open={compareOpen} onOpenChange={setCompareOpen} />

      {/* Filter chips + search */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <Segmented
          size="sm"
          value={filter}
          onChange={(v) => setFilter(v as FilterKey)}
          options={[
            { value: "all", label: t("activities.filter_all") },
            { value: "cycling", label: t("activities.filter_cycling") },
            { value: "running", label: t("activities.filter_running") },
            { value: "strength", label: t("activities.filter_strength") },
            { value: "swimming", label: t("activities.filter_swim") },
            { value: "other", label: t("activities.filter_other") },
          ]}
        />
        <div className="relative ml-auto">
          <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input
            ref={searchRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search activities…"
            className="num h-8 w-[200px] rounded-[var(--radius-control)] border border-hairline bg-surface2 pl-7 pr-7 text-[12px] text-ink placeholder:text-faint focus:border-primary focus:outline-none sm:w-[240px]"
            aria-label="Search activities"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface3 hover:text-ink"
              aria-label="Clear search"
            >
              <X size={11} />
            </button>
          )}
          <kbd className="num absolute right-2 top-1/2 hidden -translate-y-1/2 rounded-[3px] border border-hairline bg-surface3 px-1 py-0.5 text-[9px] text-faint sm:block" style={{ right: search ? "24px" : "8px" }}>
            /
          </kbd>
        </div>
      </div>

      {/* Table — desktop / tablet */}
      {filtered.length === 0 ? (
        <div className="mt-6">
          <Empty title={t("activities.empty")} />
        </div>
      ) : (
        <>
          <Card pad={false} className="mt-4 hidden overflow-hidden md:block">
            <div className="overflow-x-auto scroll-area">
              <table className="w-full min-w-[960px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-hairline bg-surface2 text-left">
                    <ThSortable k="date" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[140px]">{t("activities.col_date")}</ThSortable>
                    <Th className="w-[140px]">{t("activities.col_discipline")}</Th>
                    <Th>{t("activities.col_title")}</Th>
                    <ThSortable k="distance" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[80px] whitespace-nowrap text-right">{t("activities.distance")}</ThSortable>
                    <ThSortable k="duration" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[88px] whitespace-nowrap text-right">{t("activities.duration")}</ThSortable>
                    <ThSortable k="elevation" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[72px] whitespace-nowrap text-right">{t("activities.col_elev")}</ThSortable>
                    <ThSortable k="avg_hr" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[78px] whitespace-nowrap text-right">{t("activities.avg_hr")}</ThSortable>
                    <ThSortable k="avg_power" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[88px] whitespace-nowrap text-right">{t("activities.avg_power")}</ThSortable>
                    <ThSortable k="load" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} className="w-[72px] whitespace-nowrap text-right">{t("activities.col_load")}</ThSortable>
                    <Th className="w-[120px] text-right">{t("activities.sources")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <ActivityRow
                      key={a.id}
                      a={a}
                      locale={locale}
                      onClick={() => {
                        ui.selectActivity(a.id);
                        ui.setView("activity-detail");
                      }}
                    />
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-hairline bg-surface2">
                    <td colSpan={10} className="px-4 py-2.5">
                      <div className="flex items-center justify-between">
                        <span className="eyebrow !text-[10px]">{t("activities.total", { count: filtered.length })}</span>
                        <span className="num text-[10px] text-faint">
                          {t("activities.time_range")}: {t(`activities.${range}`)}
                        </span>
                      </div>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>

          {/* Mobile stacked cards */}
          <div className="mt-4 space-y-3 md:hidden">
            <div className="flex items-center justify-between px-1">
              <span className="eyebrow !text-[10px]">{t("activities.total", { count: filtered.length })}</span>
              <span className="num text-[10px] text-faint">
                {t("activities.time_range")}: {t(`activities.${range}`)}
              </span>
            </div>
            {filtered.map((a) => (
              <ActivityCardMobile
                key={a.id}
                a={a}
                locale={locale}
                onClick={() => {
                  ui.selectActivity(a.id);
                  ui.setView("activity-detail");
                }}
              />
            ))}
          </div>
        </>
      )}

      <Hairline className="mt-6 opacity-60" />
      <div className="mt-3 text-[11px] text-faint">
        <span className="num">{t("app.measured")}</span>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- table cell + row */

function Th({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <th
      className={`eyebrow !text-[10px] !font-semibold px-3 py-2.5 ${className}`}
    >
      {children}
    </th>
  );
}

/** Sortable column header. Click to toggle direction. Active column shows arrow indicator. */
function ThSortable({
  k,
  sortKey,
  sortDir,
  onToggle,
  children,
  className = "",
}: {
  k: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onToggle: (k: SortKey) => void;
  children: ReactNode;
  className?: string;
}) {
  const active = sortKey === k;
  const Icon = !active ? ArrowUpDown : sortDir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={`eyebrow !text-[10px] !font-semibold px-3 py-2.5 ${className}`}>
      <button
        type="button"
        onClick={() => onToggle(k)}
        className={`num inline-flex items-center gap-1 transition-colors hover:text-ink ${active ? "text-ink" : "text-muted"}`}
        aria-label={`Sort by ${typeof children === "string" ? children : k} ${active ? (sortDir === "asc" ? "descending" : "ascending") : "descending"}`}
      >
        <span>{children}</span>
        <Icon size={10} className={active ? "opacity-100" : "opacity-50"} />
      </button>
    </th>
  );
}

function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-3 py-2.5 ${className}`}>{children}</td>;
}

/** A single table row. Clickable, hover highlight, tabular figures on numbers. */
function ActivityRow({ a, locale, onClick }: { a: ActivityCard; locale: Locale; onClick: () => void }) {
  return (
    <tr
      onClick={onClick}
      className="group cursor-pointer border-b border-hairline/60 transition-colors last:border-b-0 hover:bg-surface2"
    >
      {/* Date */}
      <Td className="num whitespace-nowrap">
        <div className="flex flex-col">
          <span className="font-medium text-ink">{fmtDate(a.start_time, locale)}</span>
          <span className="text-[10px] text-faint">{fmtClock(a.start_time, locale)}</span>
        </div>
      </Td>

      {/* Discipline */}
      <Td>
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted group-hover:bg-primarySoft group-hover:text-primaryText">
            <SportIcon discipline={a.discipline} size={12} />
          </span>
          <span className="text-[12px] text-ink2">{friendlyDiscipline(a.discipline, locale)}</span>
        </div>
      </Td>

      {/* Title */}
      <Td>
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold text-ink">{a.title}</span>
          {a.data_completeness !== "complete" && (
            <Badge tone={a.data_completeness === "missing" ? "alert" : "warning"} dot>
              {a.data_completeness}
            </Badge>
          )}
        </div>
      </Td>

      {/* Distance */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {a.distance_m === null ? <span className="text-faint">—</span> : fmtDistance(a.distance_m, "metric", 1)}
      </Td>

      {/* Duration */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {fmtDuration(a.duration_s)}
      </Td>

      {/* Elevation */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {a.elevation_gain_m === null ? <span className="text-faint">—</span> : fmtElevation(a.elevation_gain_m)}
      </Td>

      {/* Avg HR */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {a.avg_hr === null || a.avg_hr === undefined || !Number.isFinite(a.avg_hr) ? (
          <span className="text-faint">—</span>
        ) : (
          a.avg_hr
        )}
      </Td>

      {/* Avg Power */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {a.avg_power === null || a.avg_power === undefined || !Number.isFinite(a.avg_power) ? (
          <span className="text-faint">—</span>
        ) : (
          `${a.avg_power} W`
        )}
      </Td>

      {/* Load */}
      <Td className="num whitespace-nowrap text-right">
        {a.training_load === null ? (
          <span className="text-faint">—</span>
        ) : (
          <Badge tone="primary">{a.training_load}</Badge>
        )}
      </Td>

      {/* Sources */}
      <Td>
        <div className="flex flex-wrap items-center justify-end gap-1">
          {a.sources.map((s) => (
            <SourcePill key={s}>{s}</SourcePill>
          ))}
        </div>
      </Td>
    </tr>
  );
}

/** Compact stacked card for mobile — appears below the scrollable table on small screens. */
function ActivityCardMobile({ a, locale, onClick }: { a: ActivityCard; locale: Locale; onClick: () => void }) {
  const t = useT();
  return (
    <Card
      onClick={onClick}
      className="cursor-pointer transition-colors hover:border-hairline2 hover:bg-surface2"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted">
            <SportIcon discipline={a.discipline} size={13} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold text-ink">{a.title}</div>
            <div className="num mt-0.5 text-[10px] text-faint">
              {fmtDate(a.start_time, locale)} · {fmtClock(a.start_time, locale)} · {friendlyDiscipline(a.discipline, locale)}
            </div>
          </div>
        </div>
        {a.training_load !== null && <Badge tone="primary">{a.training_load}</Badge>}
      </div>
      <div className="num mt-3 grid grid-cols-4 gap-2 text-[11px]">
        <Metric label={t("activities.distance")} value={a.distance_m === null ? "—" : fmtDistance(a.distance_m, "metric", 1)} />
        <Metric label={t("activities.duration")} value={fmtDuration(a.duration_s)} />
        <Metric label={t("activities.avg_hr")} value={a.avg_hr === null ? "—" : String(a.avg_hr)} />
        <Metric label={t("activities.avg_power")} value={a.avg_power === null ? "—" : `${a.avg_power}W`} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1">
        {a.sources.map((s) => (
          <SourcePill key={s}>{s}</SourcePill>
        ))}
      </div>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2 py-1.5">
      <div className="eyebrow !text-[9px] truncate">{label}</div>
      <div className="num mt-0.5 text-[12px] font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}
