"use client";

/**
 * Apex Health — Activity Comparison modal.
 *
 * Lets the user compare 2-3 activities side-by-side on key metrics:
 *   - Distance / Duration / Elevation / Avg HR / Max HR / Avg Power / NP / Calories / Load
 *
 * Visual law: monochrome table with semantic tones for "best" values per row
 * (e.g. longest distance, highest power, lowest HR for recovery rides).
 * Each activity column shows a colored header bar with the discipline.
 *
 * Behavior:
 *   - Selectable activities are limited to those with avg_hr != null (data-rich)
 *   - User can pick 2 or 3 (3rd is optional)
 *   - When closed, selection is cleared
 *   - "Best" cells in each row are tinted primarySoft/positiveSoft depending on metric
 */

import { useEffect, useMemo, useState } from "react";
import { X, GitCompare, ChevronRight, Check } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { activities } from "@/lib/apex/data";
import { ApexButton, Eyebrow, Hairline, SportIcon, Badge } from "@/components/apex/kit";
import {
  fmtClock,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  friendlyDiscipline,
} from "@/lib/apex/format";
import type { ActivityCard, Locale } from "@/lib/apex/types";

interface MetricRow {
  key: string;
  label: string;
  /** returns the value to compare (number); null = no data */
  value: (a: ActivityCard) => number | null;
  /** renders the value as a string */
  format: (v: number) => string;
  /** "high" = higher is better, "low" = lower is better, "none" = neutral */
  best: "high" | "low" | "none";
}

const METRICS: MetricRow[] = [
  { key: "distance", label: "Distance", value: (a) => a.distance_m, format: (v) => fmtDistance(v, "metric", 1) + " km", best: "high" },
  { key: "duration", label: "Duration", value: (a) => a.duration_s, format: (v) => fmtDuration(v), best: "none" },
  { key: "elevation", label: "Elevation", value: (a) => a.elevation_gain_m, format: (v) => fmtElevation(v) + " m", best: "high" },
  { key: "avg_hr", label: "Avg HR", value: (a) => a.avg_hr, format: (v) => `${v} bpm`, best: "low" },
  { key: "max_hr", label: "Max HR", value: (a) => a.max_hr, format: (v) => `${v} bpm`, best: "none" },
  { key: "avg_power", label: "Avg Power", value: (a) => a.avg_power, format: (v) => `${v} W`, best: "high" },
  { key: "np_power", label: "Norm Power", value: (a) => a.np_power, format: (v) => `${v} W`, best: "high" },
  { key: "calories", label: "Calories", value: (a) => a.calories, format: (v) => `${v} kcal`, best: "none" },
  { key: "load", label: "Strain & Load", value: (a) => a.training_load, format: (v) => `${v} TSS`, best: "high" },
];

export function ActivityCompareModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const [selected, setSelected] = useState<number[]>([]); // activity ids
  const [search, setSearch] = useState("");

  // Load persisted selection from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-compare-activities");
      if (raw) {
        const ids = JSON.parse(raw);
        if (Array.isArray(ids)) setSelected(ids.slice(0, 3));
      }
    } catch {
      /* ignore */
    }
  }, []);

  // Persist selection whenever it changes
  useEffect(() => {
    try {
      window.localStorage.setItem("apex-compare-activities", JSON.stringify(selected));
    } catch {
      /* ignore */
    }
  }, [selected]);

  // Close on Esc
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // Clear search when reopening (selection is preserved)
  useEffect(() => {
    if (open) {
      setSearch("");
    }
  }, [open]);

  // Pickable activities (sorted by date desc, with avg_hr data)
  const pickable = useMemo(() => {
    const q = search.trim().toLowerCase();
    return activities
      .filter((a) => a.avg_hr !== null)
      .filter((a) => {
        if (!q) return true;
        return (
          a.title.toLowerCase().includes(q) ||
          a.discipline.toLowerCase().includes(q) ||
          friendlyDiscipline(a.discipline, "en").toLowerCase().includes(q)
        );
      })
      .sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
  }, [search]);

  const selectedActivities = useMemo(
    () => selected.map((id) => activities.find((a) => a.id === id)).filter((a): a is ActivityCard => !!a),
    [selected]
  );

  const toggleSelect = (id: number) => {
    setSelected((cur) => {
      if (cur.includes(id)) return cur.filter((x) => x !== id);
      if (cur.length >= 3) return cur; // max 3
      return [...cur, id];
    });
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[6vh] sm:pt-[10vh]"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Compare activities"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      <div
        className="relative w-full max-w-[960px] overflow-hidden rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
              <GitCompare size={16} />
            </div>
            <div>
              <div className="eyebrow">{t("activities.title")}</div>
              <div className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
                Compare Activities
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface2 hover:text-ink"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div className="scroll-area max-h-[72vh] overflow-y-auto px-5 py-4">
          {/* Picker (when fewer than 3 selected) */}
          {selectedActivities.length < 3 && (
            <div className="mb-4">
              <Eyebrow>
                Pick activities to compare ({selectedActivities.length}/3)
              </Eyebrow>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search activities…"
                className="num mt-2 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[12px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
              />
              <div className="scroll-area mt-2 max-h-[200px] overflow-y-auto">
                {pickable.length === 0 ? (
                  <div className="px-3 py-4 text-center text-[12px] text-muted">No matches</div>
                ) : (
                  <ul className="space-y-1">
                    {pickable.slice(0, 30).map((a) => {
                      const isSel = selected.includes(a.id);
                      return (
                        <li key={a.id}>
                          <button
                            type="button"
                            onClick={() => toggleSelect(a.id)}
                            className={`flex w-full items-center gap-2.5 rounded-[var(--radius-control)] border px-2.5 py-2 text-left transition-colors ${
                              isSel
                                ? "border-primary/40 bg-primarySoft"
                                : "border-hairline bg-surface2 hover:bg-surface3"
                            }`}
                          >
                            <span className={`flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] ${isSel ? "bg-primary text-white" : "bg-surface3 text-muted"}`}>
                              {isSel ? <Check size={11} /> : <SportIcon discipline={a.discipline} size={11} />}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[12px] font-semibold text-ink">{a.title}</div>
                              <div className="num text-[12px] text-muted">
                                {fmtDate(a.start_time, "en")} · {fmtClock(a.start_time, "en")} · {friendlyDiscipline(a.discipline, "en")}
                              </div>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}

          {/* Comparison table */}
          {selectedActivities.length >= 1 ? (
            <div className="overflow-x-auto scroll-area">
              <table className="w-full min-w-[640px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-hairline bg-surface2 text-left">
                    <th className="eyebrow !text-[12px] !font-semibold px-3 py-2.5 w-[160px]">Metric</th>
                    {selectedActivities.map((a) => (
                      <th key={a.id} className="px-3 py-2.5 text-left">
                        <div className="flex items-center gap-2">
                          <span className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted">
                            <SportIcon discipline={a.discipline} size={11} />
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-[12px] font-semibold text-ink">{a.title}</div>
                            <div className="num text-[12px] text-muted">
                              {fmtDate(a.start_time, "en")}
                            </div>
                          </div>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((metric) => {
                    const values = selectedActivities.map((a) => metric.value(a));
                    const maxV = Math.max(...values.filter((v): v is number => v !== null) as number[], -Infinity);
                    const minV = Math.min(...values.filter((v): v is number => v !== null) as number[], Infinity);
                    return (
                      <tr key={metric.key} className="border-b border-hairline/60 last:border-b-0">
                        <td className="eyebrow !text-[12px] px-3 py-2.5">{metric.label}</td>
                        {selectedActivities.map((a, i) => {
                          const v = values[i];
                          if (v === null || v === undefined || !Number.isFinite(v)) {
                            return (
                              <td key={a.id} className="num px-3 py-2.5 text-right text-faint">—</td>
                            );
                          }
                          // Determine if this is the "best"
                          let isBest = false;
                          if (metric.best === "high" && maxV !== -Infinity) {
                            isBest = v === maxV && selectedActivities.length > 1;
                          } else if (metric.best === "low" && minV !== Infinity) {
                            isBest = v === minV && selectedActivities.length > 1;
                          }
                          const cellCls = isBest
                            ? metric.best === "high"
                              ? "text-positiveText bg-positiveSoft/40"
                              : "text-primaryText bg-primarySoft/40"
                            : "text-ink2";
                          return (
                            <td
                              key={a.id}
                              className={`num px-3 py-2.5 text-right font-medium ${cellCls} ${isBest ? "rounded-[var(--radius-control)]" : ""}`}
                            >
                              {metric.format(v)}
                              {isBest && <span className="ml-1 text-[12px] opacity-80">★</span>}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="px-3 py-12 text-center text-[13px] text-muted">
              Pick at least one activity to start comparing.
            </div>
          )}

          {/* Selected chips + clear */}
          {selectedActivities.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="eyebrow !text-[12px]">Selected</span>
              {selectedActivities.map((a) => (
                <Badge
                  key={a.id}
                  tone="primary"
                  className="cursor-pointer"
                  dot
                >
                  <button
                    type="button"
                    onClick={() => toggleSelect(a.id)}
                    className="flex items-center gap-1.5"
                  >
                    {a.title}
                    <X size={10} />
                  </button>
                </Badge>
              ))}
              <button
                type="button"
                onClick={() => setSelected([])}
                className="num ml-auto text-[12px] font-semibold text-muted hover:text-ink"
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3">
          <div className="num text-[12px] text-faint">
            ★ = best value for this metric (higher is better where applicable)
          </div>
          <div className="flex items-center gap-2">
            <ApexButton variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              {t("common.close")}
            </ApexButton>
            <ApexButton
              size="sm"
              onClick={() => onOpenChange(false)}
              iconRight={<ChevronRight size={12} />}
              disabled={selectedActivities.length < 2}
            >
              Done
            </ApexButton>
          </div>
        </div>
      </div>
    </div>
  );
}
