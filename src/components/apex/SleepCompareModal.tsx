"use client";

/**
 * Apex Health — Sleep Night Comparison modal.
 *
 * Lets the user compare 2-3 sleep nights side-by-side on key metrics:
 *   - Sleep Score / Total Sleep / Efficiency / Deep / REM / Light / Awake
 *   - Bedtime / Wake / Respiration / SpO₂ / Restlessness
 *
 * Visual law: monochrome table with semantic tones for "best" values per row
 * (e.g. highest sleep score, longest deep sleep, lowest restlessness).
 * Each night column shows a colored header bar with the date.
 *
 * Behavior:
 *   - User picks 2 or 3 nights (3rd optional)
 *   - Search by date (formatted as e.g. "30 Sept")
 *   - Selected nights are removable via chips
 */

import { useEffect, useMemo, useState } from "react";
import { X, GitCompare, ChevronRight, Check, Moon } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { sleepSessions } from "@/lib/apex/data";
import { ApexButton, Eyebrow, Hairline, Badge } from "@/components/apex/kit";
import { fmtDate, fmtHours, fmtClock } from "@/lib/apex/format";
import type { SleepSession, Locale } from "@/lib/apex/types";

interface MetricRow {
  key: string;
  label: string;
  value: (s: SleepSession) => number | null;
  format: (v: number) => string;
  best: "high" | "low" | "none";
}

const METRICS: MetricRow[] = [
  { key: "score", label: "Sleep Score", value: (s) => s.sleep_score, format: (v) => `${v} /100`, best: "high" },
  { key: "total", label: "Total Sleep", value: (s) => s.total_sleep_s, format: (v) => fmtHours(v), best: "high" },
  { key: "deep", label: "Deep Sleep", value: (s) => s.deep_s, format: (v) => fmtHours(v), best: "high" },
  { key: "rem", label: "REM Sleep", value: (s) => s.rem_s, format: (v) => fmtHours(v), best: "high" },
  { key: "light", label: "Light Sleep", value: (s) => s.light_s, format: (v) => fmtHours(v), best: "none" },
  { key: "awake", label: "Awake", value: (s) => s.awake_s, format: (v) => fmtHours(v), best: "low" },
  { key: "resp", label: "Respiration", value: (s) => s.respiration_avg, format: (v) => `${v.toFixed(1)} brpm`, best: "low" },
  { key: "spo2", label: "SpO₂", value: (s) => s.spo2_avg, format: (v) => `${v.toFixed(1)} %`, best: "high" },
  { key: "restless", label: "Restlessness", value: (s) => s.restlessness, format: (v) => `${v} %`, best: "low" },
];

export function SleepCompareModal({
  open,
  onOpenChange,
  locale,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  locale: Locale;
}) {
  const t = useT();
  const [selected, setSelected] = useState<string[]>([]); // local_date values
  const [search, setSearch] = useState("");

  // Load persisted selection from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-compare-sleep");
      if (raw) {
        const dates = JSON.parse(raw);
        if (Array.isArray(dates)) setSelected(dates.slice(0, 3));
      }
    } catch {
      /* ignore */
    }
  }, []);

  // Persist selection whenever it changes
  useEffect(() => {
    try {
      window.localStorage.setItem("apex-compare-sleep", JSON.stringify(selected));
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

  // Pickable sleep sessions (filtered by search)
  const pickable = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sleepSessions.filter((s) => {
      if (!q) return true;
      return fmtDate(s.local_date, locale).toLowerCase().includes(q) || s.local_date.includes(q);
    });
  }, [search, locale]);

  const selectedSessions = useMemo(
    () => selected.map((d) => sleepSessions.find((s) => s.local_date === d)).filter((s): s is SleepSession => !!s),
    [selected]
  );

  const toggleSelect = (date: string) => {
    setSelected((cur) => {
      if (cur.includes(date)) return cur.filter((x) => x !== date);
      if (cur.length >= 3) return cur;
      return [...cur, date];
    });
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[6vh] sm:pt-[10vh]"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Compare sleep nights"
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
              <div className="eyebrow">{t("sleep.title")}</div>
              <div className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
                Compare Sleep Nights
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
          {/* Picker */}
          {selectedSessions.length < 3 && (
            <div className="mb-4">
              <Eyebrow>
                Pick nights to compare ({selectedSessions.length}/3)
              </Eyebrow>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by date…"
                className="num mt-2 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[12px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
              />
              <div className="scroll-area mt-2 max-h-[200px] overflow-y-auto">
                {pickable.length === 0 ? (
                  <div className="px-3 py-4 text-center text-[12px] text-muted">No matches</div>
                ) : (
                  <ul className="space-y-1">
                    {pickable.slice(0, 30).map((s) => {
                      const isSel = selected.includes(s.local_date);
                      return (
                        <li key={s.local_date}>
                          <button
                            type="button"
                            onClick={() => toggleSelect(s.local_date)}
                            className={`flex w-full items-center gap-2.5 rounded-[var(--radius-control)] border px-2.5 py-2 text-left transition-colors ${
                              isSel
                                ? "border-primary/40 bg-primarySoft"
                                : "border-hairline bg-surface2 hover:bg-surface3"
                            }`}
                          >
                            <span className={`flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] ${isSel ? "bg-primary text-white" : "bg-surface3 text-muted"}`}>
                              {isSel ? <Check size={11} /> : <Moon size={11} />}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[12px] font-semibold text-ink">
                                {fmtDate(s.local_date, locale)}
                              </div>
                              <div className="num text-[12px] text-muted">
                                {t("sleep.score")} {s.sleep_score ?? "—"} · {fmtHours(s.total_sleep_s ?? 0)}
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
          {selectedSessions.length >= 1 ? (
            <div className="overflow-x-auto scroll-area">
              <table className="w-full min-w-[640px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-hairline bg-surface2 text-left">
                    <th className="eyebrow !text-[12px] !font-semibold px-3 py-2.5 w-[160px]">Metric</th>
                    {selectedSessions.map((s) => (
                      <th key={s.local_date} className="px-3 py-2.5 text-left">
                        <div className="flex items-center gap-2">
                          <span className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted">
                            <Moon size={11} />
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-[12px] font-semibold text-ink">
                              {fmtDate(s.local_date, locale)}
                            </div>
                            <div className="num text-[12px] text-muted">
                              {fmtClock(s.start_time, locale)} → {fmtClock(s.end_time, locale)}
                            </div>
                          </div>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((metric) => {
                    const values = selectedSessions.map((s) => metric.value(s));
                    const maxV = Math.max(...values.filter((v): v is number => v !== null) as number[], -Infinity);
                    const minV = Math.min(...values.filter((v): v is number => v !== null) as number[], Infinity);
                    return (
                      <tr key={metric.key} className="border-b border-hairline/60 last:border-b-0">
                        <td className="eyebrow !text-[12px] px-3 py-2.5">{metric.label}</td>
                        {selectedSessions.map((s, i) => {
                          const v = values[i];
                          if (v === null || v === undefined || !Number.isFinite(v)) {
                            return (
                              <td key={s.local_date} className="num px-3 py-2.5 text-right text-faint">—</td>
                            );
                          }
                          let isBest = false;
                          if (metric.best === "high" && maxV !== -Infinity) {
                            isBest = v === maxV && selectedSessions.length > 1;
                          } else if (metric.best === "low" && minV !== Infinity) {
                            isBest = v === minV && selectedSessions.length > 1;
                          }
                          const cellCls = isBest
                            ? metric.best === "high"
                              ? "text-positiveText bg-positiveSoft/40"
                              : "text-primaryText bg-primarySoft/40"
                            : "text-ink2";
                          return (
                            <td
                              key={s.local_date}
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
              Pick at least one night to start comparing.
            </div>
          )}

          {/* Selected chips */}
          {selectedSessions.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="eyebrow !text-[12px]">Selected</span>
              {selectedSessions.map((s) => (
                <Badge key={s.local_date} tone="primary" className="cursor-pointer" dot>
                  <button
                    type="button"
                    onClick={() => toggleSelect(s.local_date)}
                    className="flex items-center gap-1.5"
                  >
                    {fmtDate(s.local_date, locale)}
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
            ★ = best value for this metric
          </div>
          <div className="flex items-center gap-2">
            <ApexButton variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              {t("common.close")}
            </ApexButton>
            <ApexButton
              size="sm"
              onClick={() => onOpenChange(false)}
              iconRight={<ChevronRight size={12} />}
              disabled={selectedSessions.length < 2}
            >
              Done
            </ApexButton>
          </div>
        </div>
      </div>
    </div>
  );
}
