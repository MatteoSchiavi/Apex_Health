"use client";

/**
 * Apex Health — Command Palette (⌘K / Ctrl+K).
 *
 * Opens a modal with fuzzy search across:
 *  - All navigation views (Overview, Activities, Sleep, Biometrics, Training, Coach, Social, Settings)
 *  - Quick actions (Sign out, Toggle theme, Switch language, Open recovery scan, Export overview)
 *  - Recently viewed metrics / activities / sleep nights (mock: lists the first few from data)
 *
 * Keyboard:
 *  - ⌘K / Ctrl+K to open
 *  - Esc to close
 *  - ↑ / ↓ to navigate, Enter to execute, Tab to filter scope (optional)
 *
 * Visual: monochrome + primary accent. Floats above app with the apex shadow flyout.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  ChevronRight,
  Dumbbell,
  HeartPulse,
  CornerDownLeft,
  Download,
  Languages,
  LogOut,
  Moon,
  Search,
  Settings,
  Sparkles,
  Sun,
  Trophy,
  X,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useApexUi } from "@/lib/apex";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import type { ViewKey } from "@/lib/apex/types";
import { metricCatalog, activities, sleepSessions } from "@/lib/apex/data";
import { fmtDate } from "@/lib/apex/format";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  group: "navigation" | "actions" | "metrics" | "activities" | "sleep";
  icon: LucideIcon;
  run: () => void;
  keywords?: string;
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const ui = useApexUi();
  const t = useT();
  const { locale, setLocale } = useI18n();
  const { theme, setTheme } = useTheme();
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const [recent, setRecent] = useState<string[]>([]); // recently-executed command ids (localStorage-persisted)
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Load recent selections from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-cmd-recent");
      if (raw) setRecent(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  // Reset query when palette opens
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Record recent selection (helper passed to commands below via wrapper)
  const recordRecent = (id: string) => {
    setRecent((cur) => {
      const next = [id, ...cur.filter((x) => x !== id)].slice(0, 5);
      try {
        window.localStorage.setItem("apex-cmd-recent", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  // Build commands
  const items: CommandItem[] = useMemo(() => {
    const nav: CommandItem[] = [
      { id: "nav-overview", label: t("nav.overview"), group: "navigation", icon: Activity, run: () => ui.setView("overview") },
      { id: "nav-activities", label: t("nav.activities"), group: "navigation", icon: BarChart3, run: () => ui.setView("activities") },
      { id: "nav-sleep", label: t("nav.sleep"), group: "navigation", icon: Moon, run: () => ui.setView("sleep") },
      { id: "nav-biometrics", label: t("nav.biometrics"), group: "navigation", icon: HeartPulse, run: () => ui.setView("biometrics") },
      { id: "nav-training", label: t("nav.training"), group: "navigation", icon: Dumbbell, run: () => ui.setView("training") },
      { id: "nav-coach", label: t("nav.coach"), group: "navigation", icon: Bot, run: () => ui.setView("coach") },
      { id: "nav-social", label: t("nav.social"), group: "navigation", icon: Trophy, run: () => ui.setView("social") },
      { id: "nav-settings", label: t("nav.settings"), group: "navigation", icon: Settings, run: () => ui.setView("settings") },
    ];

    const actions: CommandItem[] = [
      {
        id: "act-theme-toggle",
        label: theme === "light" ? t("theme.dark") : t("theme.light"),
        group: "actions",
        icon: theme === "light" ? Moon : Sun,
        hint: t("theme.toggle"),
        run: () => {
          const next = theme === "light" ? "dark" : "light";
          setTheme(next === "dark" ? "dark" : "light");
          ui.setTheme(next as "dark" | "light");
        },
      },
      {
        id: "act-locale",
        label: locale === "en" ? t("locale.it") : t("locale.en"),
        group: "actions",
        icon: Languages,
        hint: t("locale.switch"),
        run: () => setLocale(locale === "en" ? "it" : "en"),
      },
      {
        id: "act-signout",
        label: t("settings.sign_out"),
        group: "actions",
        icon: LogOut,
        run: () => ui.signOut(),
      },
      {
        id: "act-export",
        label: t("overview.title") + " — Export",
        group: "actions",
        icon: Download,
        hint: "PDF",
        run: () => window.print(),
      },
    ];

    const metrics: CommandItem[] = metricCatalog.slice(0, 8).map((m) => ({
      id: `metric-${m.key}`,
      label: m.label,
      hint: `${m.unit} · ${m.source}`,
      group: "metrics",
      icon: HeartPulse,
      keywords: m.key,
      run: () => {
        ui.selectMetric(m.key);
        ui.setView("metric");
      },
    }));

    const acts: CommandItem[] = activities.slice(0, 6).map((a) => ({
      id: `act-${a.id}`,
      label: a.title,
      hint: `${fmtDate(a.local_date, locale)} · ${a.discipline}`,
      group: "activities",
      icon: BarChart3,
      keywords: a.discipline,
      run: () => {
        ui.selectActivity(a.id);
        ui.setView("activity-detail");
      },
    }));

    const slp: CommandItem[] = sleepSessions.slice(0, 5).map((s) => ({
      id: `slp-${s.local_date}`,
      label: `${t("sleep.night")} ${fmtDate(s.local_date, locale)}`,
      hint: `${t("sleep.score")} ${s.sleep_score ?? "—"}`,
      group: "sleep",
      icon: Moon,
      run: () => {
        ui.selectSleepDate(s.local_date);
        ui.setView("sleep-night");
      },
    }));

    return [...nav, ...actions, ...metrics, ...acts, ...slp];
  }, [ui, t, locale, theme, setLocale, setTheme]);

  // Filter
  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter(
      (it) =>
        it.label.toLowerCase().includes(q) ||
        it.hint?.toLowerCase().includes(q) ||
        it.keywords?.toLowerCase().includes(q) ||
        it.group.includes(q)
    );
  }, [items, query]);

  // Close on Esc + global ⌘K handler (declared AFTER items so the closure can reference it)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered[activeIdx];
        if (item) {
          recordRecent(item.id);
          item.run();
          onOpenChange(false);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, activeIdx, onOpenChange, filtered]);

  // Scroll active item into view (must run before any early return so hooks order is stable)
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector(`[data-idx="${activeIdx}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx, open]);

  // Build the flat filtered list (used by the active index)
  const flatFiltered = filtered;

  // Pre-pend "Recent" group when no query and we have recent items
  const recentItems = useMemo(() => {
    if (query.trim()) return [];
    return recent
      .map((id) => items.find((it) => it.id === id))
      .filter((it): it is CommandItem => !!it);
  }, [recent, items, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    // Recent section first (only when no query)
    if (recentItems.length > 0) {
      map.set("recent", recentItems);
    }
    filtered.forEach((it) => {
      // Skip items already shown in recent (avoid duplicate display)
      if (recentItems.includes(it)) return;
      const arr = map.get(it.group) ?? [];
      arr.push(it);
      map.set(it.group, arr);
    });
    return Array.from(map.entries());
  }, [filtered, recentItems]);

  // Build the flat list for active index (includes recent + filtered minus recent duplicates)
  const flatWithRecent = useMemo(() => {
    if (recentItems.length === 0) return filtered;
    const seen = new Set(recentItems.map((r) => r.id));
    return [...recentItems, ...filtered.filter((it) => !seen.has(it.id))];
  }, [filtered, recentItems]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className="relative w-full max-w-[640px] overflow-hidden rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search header */}
        <div className="flex items-center gap-3 border-b border-hairline px-4 py-3">
          <Search size={16} className="text-muted" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIdx(0);
            }}
            placeholder={t("app.search")}
            className="num flex-1 bg-transparent text-[14px] text-ink placeholder:text-faint focus:outline-none"
            aria-label="Command search"
          />
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface2 hover:text-ink"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        {/* Results */}
        <div ref={listRef} className="scroll-area max-h-[440px] overflow-y-auto py-1">
          {flatWithRecent.length === 0 ? (
            <div className="px-4 py-8 text-center text-[13px] text-muted">No matches for "{query}"</div>
          ) : (
            grouped.map(([group, groupItems]) => {
              const groupLabel: Record<string, string> = {
                recent: "Recent",
                navigation: t("nav.overview") + " & " + t("nav.settings").toLowerCase(),
                actions: "Quick actions",
                metrics: t("nav.biometrics"),
                activities: t("nav.activities"),
                sleep: t("nav.sleep"),
              };
              return (
                <div key={group} className="mb-1">
                  <div className="eyebrow px-4 py-1.5">{groupLabel[group] ?? group}</div>
                  {groupItems.map((item) => {
                    const idx = flatWithRecent.indexOf(item);
                    const active = idx === activeIdx;
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        data-idx={idx}
                        onMouseEnter={() => setActiveIdx(idx)}
                        onClick={() => {
                          recordRecent(item.id);
                          item.run();
                          onOpenChange(false);
                        }}
                        className={`flex w-full items-center gap-3 px-4 py-2 text-left transition-colors ${
                          active ? "bg-surface2" : "hover:bg-surface2/60"
                        }`}
                      >
                        <div
                          className={`flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] ${
                            active ? "bg-primarySoft text-primaryText" : "bg-surface3 text-muted"
                          }`}
                        >
                          <Icon size={14} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13px] font-medium text-ink">{item.label}</div>
                          {item.hint && (
                            <div className="num truncate text-[11px] text-muted">{item.hint}</div>
                          )}
                        </div>
                        {active && (
                          <div className="flex items-center gap-1 text-[10px] text-faint">
                            <CornerDownLeft size={10} />
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-hairline px-4 py-2 text-[10px] text-faint">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1.5 py-0.5 text-[9px] text-muted">↑↓</kbd>
              navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1.5 py-0.5 text-[9px] text-muted">↵</kbd>
              select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="num rounded-[3px] border border-hairline bg-surface3 px-1.5 py-0.5 text-[9px] text-muted">esc</kbd>
              close
            </span>
          </div>
          <div className="num flex items-center gap-1">
            <Sparkles size={10} />
            <span>{flatWithRecent.length} results</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Hook that registers the global ⌘K / Ctrl+K hotkey. */
export function useCommandPaletteHotkey(onToggle: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onToggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onToggle]);
}
