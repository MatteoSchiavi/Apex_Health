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

import { useMemo, useState, type ReactNode } from "react";
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
} from "@/components/apex/kit";
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

const RANGE_DAYS: Record<RangeKey, number> = {
  "30d": 30,
  "90d": 90,
  "12m": 365,
};

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

  const filtered = useMemo(() => {
    const now = Date.now();
    const cutoffMs = RANGE_DAYS[range] * 24 * 3600 * 1000;
    return activities
      .filter((a) => {
        const ageMs = now - new Date(a.start_time).getTime();
        if (ageMs > cutoffMs) return false;
        return matchesFilter(a.discipline, filter);
      })
      .sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
  }, [range, filter]);

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader
        title={t("activities.title")}
        subtitle={t("welcome.preview_activities")}
        actions={
          <Segmented
            value={range}
            onChange={(v) => setRange(v as RangeKey)}
            options={[
              { value: "30d", label: t("activities.30d") },
              { value: "90d", label: t("activities.90d") },
              { value: "12m", label: t("activities.12m") },
            ]}
          />
        }
      />

      {/* Filter chips */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
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
                    <Th className="w-[140px]">{t("activities.col_date")}</Th>
                    <Th className="w-[140px]">{t("activities.col_discipline")}</Th>
                    <Th>{t("activities.col_title")}</Th>
                    <Th className="w-[80px] text-right">{t("activities.distance")}</Th>
                    <Th className="w-[88px] text-right">{t("activities.duration")}</Th>
                    <Th className="w-[72px] text-right">{t("activities.col_elev")}</Th>
                    <Th className="w-[78px] text-right">{t("activities.avg_hr")}</Th>
                    <Th className="w-[88px] text-right">{t("activities.avg_power")}</Th>
                    <Th className="w-[72px] text-right">{t("activities.col_load")}</Th>
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
        {a.avg_hr === null ? <span className="text-faint">—</span> : a.avg_hr}
      </Td>

      {/* Avg Power */}
      <Td className="num whitespace-nowrap text-right tabular-nums text-ink2">
        {a.avg_power === null ? <span className="text-faint">—</span> : `${a.avg_power} W`}
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
