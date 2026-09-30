"use client";

/**
 * Apex App Shell — the frame every authenticated page lives in.
 *
 * Desktop (≥lg): fixed LEFT sidebar — Apex logo, "Telemetry & Analysis" nav,
 * device sync footer, theme + locale, account chip.
 * Tablet/Mobile (<lg): sidebar collapses to a BOTTOM tab bar (thumb-reachable,
 * safe-area aware). Topbar condenses to a single breadcrumb row.
 *
 * Coherence law: ONE nav list drives both sidebar and bottom bar. The sidebar
 * shows section labels; the bottom bar shows icons + short labels.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  ChevronRight,
  HeartPulse,
  Moon,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  Trophy,
  Dumbbell,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { motion, useReducedMotion } from "framer-motion";
import { useApexUi } from "@/lib/apex/store";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { devices, me } from "@/lib/apex/data";
import type { ViewKey } from "@/lib/apex/types";
import { timeAgo } from "@/lib/apex/format";
import { SportIcon } from "../kit";
import { CommandPalette, useCommandPaletteHotkey } from "../CommandPalette";
import { NotificationsBell } from "../NotificationsBell";
import { RecoveryScanModal } from "../RecoveryScanModal";
import { ShortcutsHelpModal } from "../ShortcutsHelpModal";
import { useGlobalShortcuts } from "@/hooks/use-global-shortcuts";

interface NavItem {
  view: ViewKey;
  icon: LucideIcon;
  labelKey: string;
}

const NAV: NavItem[] = [
  { view: "overview", icon: Activity, labelKey: "nav.overview" },
  { view: "activities", icon: BarChart3, labelKey: "nav.activities" },
  { view: "sleep", icon: Moon, labelKey: "nav.sleep" },
  { view: "biometrics", icon: HeartPulse, labelKey: "nav.biometrics" },
  { view: "training", icon: Dumbbell, labelKey: "nav.training" },
  { view: "coach", icon: Bot, labelKey: "nav.coach" },
  { view: "social", icon: Trophy, labelKey: "nav.social" },
  { view: "settings", icon: Settings, labelKey: "nav.settings" },
];

/** Logo — monogram + wordmark, used in sidebar (full) and topbar (compact). */
function Logo({ compact = false }: { compact?: boolean }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2.5">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-primary/15" />
        <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
      </svg>
      {!compact && (
        <div className="flex items-baseline gap-1.5 tracking-tight">
          <span className="text-[15px] font-bold tracking-[0.02em] text-ink">{t("app.name")}</span>
          <span className="text-[11px] font-medium tracking-[0.22em] text-muted">{t("app.suffix")}</span>
        </div>
      )}
    </div>
  );
}

/** Theme segmented controller (Dark / Light). */
function ThemeSegmented() {
  const t = useT();
  const { theme, setTheme } = useTheme();
  const ui = useApexUi();
  const apply = (next: "dark" | "light") => {
    setTheme(next === "dark" ? "dark" : "light");
    ui.setTheme(next);
  };
  return (
    <div className="inline-flex items-center rounded-[var(--radius-control)] border border-hairline bg-bg p-0.5">
      {(["dark", "light"] as const).map((tname) => (
        <button
          key={tname}
          type="button"
          aria-label={t(`theme.${tname}`)}
          onClick={() => apply(tname)}
          className={`flex h-6 items-center gap-1.5 rounded-[calc(var(--radius-control)-1px)] px-2 text-[11px] font-medium transition-colors ${
            (theme === tname || (theme === undefined && tname === "dark"))
              ? "bg-surface2 text-ink"
              : "text-muted hover:text-ink2"
          }`}
        >
          {tname === "dark" ? <Moon size={11} /> : <Sun size={11} />}
          <span className="hidden sm:inline">{t(`theme.${tname}`)}</span>
        </button>
      ))}
    </div>
  );
}

/** Locale toggle. */
function LocaleToggle() {
  const t = useT();
  const { locale, setLocale } = useI18n();
  return (
    <button
      type="button"
      onClick={() => setLocale(locale === "en" ? "it" : "en")}
      className="num inline-flex h-6 items-center rounded-[var(--radius-control)] border border-hairline bg-bg px-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted transition-colors hover:text-ink"
      aria-label={t("locale.switch")}
    >
      {locale === "en" ? "EN" : "IT"}
    </button>
  );
}

/** Device sync footer — connected providers + freshest sync. */
function SyncFooter() {
  const t = useT();
  const { locale } = useI18n();
  const active = devices.filter((d) => d.status === "active");
  if (active.length === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-hairline bg-surface px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-hairline2" />
          <span className="eyebrow !text-[10px]">{t("overview.no_devices")}</span>
        </div>
      </div>
    );
  }
  const freshest = active
    .map((d) => d.last_synced_at)
    .filter((v): v is string => !!v)
    .sort()
    .at(-1);
  const names = active.map((d) => d.provider).join(" · ").toUpperCase();
  return (
    <div className="rounded-[var(--radius-card)] border border-hairline bg-surface px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-positive" />
          </span>
          <span className="num truncate text-[10px] font-medium tracking-[0.08em] text-ink2">
            {names}
          </span>
        </div>
      </div>
      <div className="num mt-1 flex items-center justify-between text-[10px] text-faint">
        <span className="eyebrow !text-[9px]">{t("overview.telemetry_state")}</span>
        <span>{freshest ? timeAgo(freshest, locale) : "—"}</span>
      </div>
    </div>
  );
}

/** Sidebar (desktop) — retractable/collapsible. */
function Sidebar({ current, onNav, collapsed, onToggleCollapse }: { current: ViewKey; onNav: (v: ViewKey) => void; collapsed: boolean; onToggleCollapse: () => void }) {
  const t = useT();
  return (
    <aside
      className={`hidden lg:flex lg:fixed lg:inset-y-0 lg:left-0 flex-col border-r border-hairline bg-bg transition-[width] duration-200 ${
        collapsed ? "lg:w-[60px]" : "lg:w-[244px]"
      }`}
    >
      <div className="flex h-14 items-center justify-between px-3">
        <button
          type="button"
          onClick={() => onNav("overview")}
          className="transition-opacity hover:opacity-80"
        >
          {collapsed ? (
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
              <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
            </svg>
          ) : (
            <Logo />
          )}
        </button>
        {/* Toggle button — ALWAYS in the same position (top-right of header), 
            regardless of collapsed state. Fixes the inconsistency where collapse 
            was at top and expand was at bottom. */}
        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface2 hover:text-ink"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>
      </div>

      {!collapsed && (
        <div className="px-4 py-2">
          <div className="eyebrow !text-[10px]">{t("app.section")}</div>
        </div>
      )}

      <nav className="flex-1 scroll-area overflow-y-auto px-2">
        <ul className="space-y-0.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = current === item.view;
            return (
              <li key={item.view}>
                <button
                  type="button"
                  onClick={() => onNav(item.view)}
                  className={`group flex w-full items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    active
                      ? "bg-surface2 text-ink"
                      : "text-muted hover:bg-surface hover:text-ink2"
                  } ${collapsed ? "justify-center" : ""}`}
                  title={collapsed ? t(item.labelKey) : undefined}
                >
                  <Icon
                    size={18}
                    className={active ? "text-primaryText" : "text-muted group-hover:text-ink2"}
                    strokeWidth={2}
                  />
                  {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
                  {!collapsed && active && <ChevronRight size={12} className="ml-auto text-muted" />}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="px-2 pb-3 pt-2">
        {!collapsed && <SyncFooter />}
      </div>
    </aside>
  );
}

/** Topbar (mobile) — brand + theme/locale compact controls + search + scan. */
function Topbar({ current, onSearch, onScan }: { current: ViewKey; onSearch: () => void; onScan: () => void }) {
  const t = useT();
  const currentLabel = NAV.find((n) => n.view === current)?.labelKey;
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-2 border-b border-hairline bg-bg/95 px-4 backdrop-blur lg:hidden">
      <button
        type="button"
        onClick={() => useApexUi.getState().setView("overview")}
        className="transition-opacity hover:opacity-80"
      >
        <Logo />
      </button>
      <div className="num truncate text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
        {currentLabel ? t(currentLabel) : ""}
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={onSearch}
          className="inline-flex h-6 items-center justify-center rounded-[var(--radius-control)] border border-hairline bg-bg px-2 text-muted transition-colors hover:text-ink"
          aria-label={t("app.search")}
        >
          <Search size={12} />
        </button>
        <NotificationsBell />
      </div>
    </header>
  );
}

function ThemeSegmentedCompact() {
  const { theme, setTheme } = useTheme();
  const ui = useApexUi();
  return (
    <button
      type="button"
      onClick={() => {
        const next = theme === "light" ? "dark" : "light";
        setTheme(next === "dark" ? "dark" : "light");
        ui.setTheme(next as "dark" | "light");
      }}
      className="inline-flex h-6 items-center justify-center rounded-[var(--radius-control)] border border-hairline bg-bg px-2 text-muted transition-colors hover:text-ink"
      aria-label="Toggle theme"
    >
      {theme === "light" ? <Moon size={12} /> : <Sun size={12} />}
    </button>
  );
}

/** Bottom navigation (mobile). */
function BottomNav({ current, onNav }: { current: ViewKey; onNav: (v: ViewKey) => void }) {
  const t = useT();
  // 5 visible primary + 3 hidden in "more"
  const PRIMARY: NavItem[] = [
    NAV[0], // overview
    NAV[1], // activities
    NAV[2], // sleep
    NAV[4], // training
    NAV[7], // settings
  ];
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 border-t border-hairline bg-bg/95 backdrop-blur lg:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      <ul className="flex items-stretch justify-around">
        {PRIMARY.map((item) => {
          const Icon = item.icon;
          const active = current === item.view;
          return (
            <li key={item.view} className="flex-1">
              <button
                type="button"
                onClick={() => onNav(item.view)}
                className={`relative flex h-16 w-full flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors ${
                  active ? "text-primaryText" : "text-muted"
                }`}
                aria-current={active ? "page" : undefined}
              >
                {/* Top active indicator bar */}
                {active && (
                  <span
                    className="absolute left-1/2 top-0 h-0.5 w-8 -translate-x-1/2 rounded-b-full bg-primary"
                    aria-hidden
                  />
                )}
                <Icon size={20} strokeWidth={active ? 2.4 : 1.8} />
                <span className="num truncate text-[9px] tracking-[0.04em] uppercase">
                  {t(item.labelKey)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Account chip in the desktop topbar. */
function AccountChip() {
  const t = useT();
  const ui = useApexUi();
  return (
    <button
      type="button"
      onClick={() => ui.setView("settings")}
      className="flex items-center gap-2.5 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 transition-colors hover:bg-surface2"
    >
      <div className="num flex h-7 w-7 items-center justify-center rounded-full bg-primarySoft text-[12px] font-bold text-primaryText">
        {me.name
          .split(" ")
          .map((s) => s[0])
          .join("")
          .slice(0, 2)}
      </div>
      <div className="hidden text-left xl:block">
        <div className="num text-[12px] font-semibold leading-tight text-ink">{me.name}</div>
        <div className="num text-[10px] text-muted">{me.email}</div>
      </div>
    </button>
  );
}

/** Main app shell wrapping each authenticated page. */
export function AppShell({
  current,
  breadcrumb,
  onNav,
  children,
}: {
  current: ViewKey;
  breadcrumb?: ReactNode;
  onNav: (v: ViewKey) => void;
  children: ReactNode;
}) {
  // Disable body scroll restoration fighting with hash navigation
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.scrollTo(0, 0);
  }, [current]);

  // Command palette (⌘K) state
  const [cmdOpen, setCmdOpen] = useState(false);
  useCommandPaletteHotkey(() => setCmdOpen((o) => !o));

  // Recovery scan modal state
  const [scanOpen, setScanOpen] = useState(false);

  // Shortcuts help modal state
  const [helpOpen, setHelpOpen] = useState(false);

  // Sidebar collapsed state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Respect the user's OS-level prefers-reduced-motion setting
  const reducedMotion = useReducedMotion();

  // Global keyboard shortcuts: "?" opens help, "g+letter" navigates, "f" focuses first field
  useGlobalShortcuts({
    setView: onNav,
    setHelpOpen,
    onFocusFirstField: () => {
      // Find the first input/select/textarea on the page and focus it
      const first = document.querySelector("main input:not([type=hidden]):not([disabled]), main select:not([disabled]), main textarea:not([disabled])") as HTMLElement | null;
      first?.focus();
    },
  });

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Sidebar current={current} onNav={onNav} collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((v) => !v)} />
      <div className={sidebarCollapsed ? "lg:pl-[60px]" : "lg:pl-[244px]"}>
        {/* Desktop topbar */}
        <header className="sticky top-0 z-20 hidden h-14 items-center justify-between gap-3 border-b border-hairline bg-canvas/95 px-6 backdrop-blur lg:flex">
          <div className="flex min-w-0 items-center gap-3 text-[12px] text-muted">
            {breadcrumb}
          </div>
          <div className="flex items-center gap-2">
            <SearchTrigger onClick={() => setCmdOpen(true)} />
            <NotificationsBell />
            <ShortcutsHelpButton onClick={() => setHelpOpen(true)} />
            <AccountChip />
          </div>
        </header>

        {/* Mobile topbar */}
        <Topbar current={current} onSearch={() => setCmdOpen(true)} onScan={() => setScanOpen(true)} />

        {/* Page content — fades in on view change (respects prefers-reduced-motion) */}
        <main className="flex-1 px-4 pb-24 pt-4 lg:px-6 lg:pb-12 lg:pt-6">
          <motion.div
            key={current}
            initial={reducedMotion ? false : { opacity: 0, y: 6 }}
            animate={reducedMotion ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            {children}
          </motion.div>
        </main>
      </div>
      <BottomNav current={current} onNav={onNav} />

      {/* Global overlays */}
      <CommandPalette
        open={cmdOpen}
        onOpenChange={setCmdOpen}
        onOpenHelp={() => {
          setCmdOpen(false);
          setHelpOpen(true);
        }}
      />
      <RecoveryScanModal open={scanOpen} onOpenChange={setScanOpen} />
      <ShortcutsHelpModal open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}

/** Search trigger — opens the ⌘K command palette. */
function SearchTrigger({ onClick }: { onClick: () => void }) {
  const t = useT();
  return (
    <button
      type="button"
      onClick={onClick}
      className="num group flex h-8 items-center gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 text-[11px] text-muted transition-colors hover:bg-surface2 hover:text-ink"
      aria-label={t("app.search")}
    >
      <Search size={12} />
      <span className="hidden xl:inline">{t("app.search")}</span>
      <kbd className="num ml-1 hidden rounded-[3px] border border-hairline bg-surface3 px-1 py-0.5 text-[9px] text-faint xl:inline">
        ⌘K
      </kbd>
    </button>
  );
}

/** Shortcuts help trigger — opens the keyboard shortcuts modal. */
function ShortcutsHelpButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] border border-hairline bg-surface text-[12px] font-semibold text-muted transition-colors hover:bg-surface2 hover:text-ink"
      aria-label="Keyboard shortcuts (?)"
      title="Keyboard shortcuts (?)"
    >
      ?
    </button>
  );
}

/** Breadcrumb item with caret separators. */
export function Breadcrumb({ items }: { items: { label: ReactNode; onClick?: () => void }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={12} className="text-faint" />}
            {item.onClick && !isLast ? (
              <button
                type="button"
                onClick={item.onClick}
                className="num truncate font-medium text-muted transition-colors hover:text-ink"
              >
                {item.label}
              </button>
            ) : (
              <span
                className={`num truncate ${isLast ? "font-semibold text-ink" : "text-muted"}`}
              >
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
