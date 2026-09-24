/**
 * App shell v2 — the frame every page lives in (approved mockups).
 *
 * ≥lg: fixed LEFT sidebar (logo, TELEMETRY & ANALYSIS nav, device sync
 * footer, theme protocol, account chip) + topbar (breadcrumb, measured-data
 * badge, ⌘K quick telemetry, avatar). <lg / portrait: sidebar collapses to
 * a BOTTOM tab bar (owner's screen-ratio law) and the topbar condenses.
 */

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Activity,
  BarChart3,
  Bot,
  ChevronRight,
  HeartPulse,
  Moon,
  Search,
  Settings,
  Sun,
  Trophy,
  X,
} from "lucide-react";
import { useUi } from "../../app/stores/ui";
import { api, type DeviceOut } from "../../app/api";
import { timeAgo } from "../kit";

const NAV: { to: string; icon: typeof Activity; key: string; end?: boolean }[] = [
  { to: "/app", icon: Activity, key: "nav.overview", end: true },
  { to: "/app/activities", icon: BarChart3, key: "nav.activities" },
  { to: "/app/sleep", icon: Moon, key: "nav.sleep" },
  { to: "/app/biometrics", icon: HeartPulse, key: "nav.biometrics" },
  { to: "/app/training", icon: Trophy, key: "nav.training" },
  { to: "/app/coach", icon: Bot, key: "nav.coach" },
  { to: "/app/social", icon: Trophy, key: "nav.social" },
];

function Logo({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2.5">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-primary/15" />
        <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
      </svg>
      {!compact && (
        <div className="flex items-baseline gap-1.5 tracking-tight">
          <span className="text-[15px] font-bold tracking-[0.02em] text-ink">APEX</span>
          <span className="text-[11px] font-medium tracking-[0.22em] text-muted">
            {t("app.suffix")}
          </span>
        </div>
      )}
    </div>
  );
}

function ThemeSegmented() {
  const { t } = useTranslation();
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  return (
    <div className="inline-flex items-center rounded-control border border-hairline bg-bg p-0.5">
      {(["dark", "light"] as const).map((tname) => (
        <button
          key={tname}
          type="button"
          aria-label={t(`theme.${tname}`)}
          onClick={() => setTheme(tname)}
          className={`flex h-6 items-center gap-1.5 rounded-[3px] px-2 text-[11px] font-medium transition-colors ${
            theme === tname ? "bg-surface2 text-ink" : "text-muted hover:text-ink2"
          }`}
        >
          {tname === "dark" ? <Moon size={11} /> : <Sun size={11} />}
          <span className="hidden sm:inline">{t(`theme.${tname}`)}</span>
        </button>
      ))}
    </div>
  );
}

/** Device sync footer — connected providers + freshest sync (mockup). */
function SyncFooter() {
  const { t } = useTranslation();
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<DeviceOut[]>("/settings/devices"),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
  const rows = devices.data ?? [];
  const active = rows.filter((d) => d.status === "active");
  if (devices.isLoading || active.length === 0) {
    return (
      <div className="rounded-card border border-hairline bg-surface px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-hairline2" />
          <span className="eyebrow !text-[10px]">{t("sync.no_devices")}</span>
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
    <div className="rounded-card border border-hairline bg-surface px-3 py-2.5">
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
        <span className="num shrink-0 text-[10px] text-faint">
          {freshest ? timeAgo(freshest) : "—"}
        </span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------- command palette */

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  useEffect(() => {
    if (open) setQ("");
  }, [open]);
  const items = useMemo(
    () => [
      ...NAV,
      { to: "/app/settings", icon: Settings, key: "nav.settings", end: false },
    ],
    [],
  );
  const filtered = items.filter((i) => t(i.key).toLowerCase().includes(q.toLowerCase()));
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-xl border border-hairline bg-surface2 shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-hairline px-3">
          <Search size={14} className="text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("search.placeholder")}
            className="h-11 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-faint"
          />
          <button onClick={onClose} aria-label="close" className="text-muted hover:text-ink">
            <X size={14} />
          </button>
        </div>
        <div className="max-h-72 overflow-y-auto p-1.5">
          {filtered.length === 0 && (
            <div className="px-3 py-6 text-center text-[12px] text-muted">{t("search.no_results")}</div>
          )}
          {filtered.map(({ to, icon: Icon, key }) => (
            <button
              key={to}
              type="button"
              onClick={() => {
                navigate(to);
                onClose();
              }}
              className="flex w-full items-center gap-2.5 rounded-control px-3 py-2 text-left text-[13px] text-ink2 hover:bg-surface3 hover:text-ink"
            >
              <Icon size={15} strokeWidth={1.8} className="text-muted" />
              {t(key)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Breadcrumb from the active route: "Apex Health / <page>". */
function Breadcrumb() {
  const { t } = useTranslation();
  const location = useLocation();
  const current =
    [...NAV, { to: "/app/settings", key: "nav.settings" }].find((n) =>
      n.to === "/app" ? location.pathname === "/app" : location.pathname.startsWith(n.to),
    ) ?? NAV[0];
  return (
    <nav className="hidden items-center gap-1.5 text-[12px] lg:flex" aria-label="breadcrumb">
      <span className="text-muted">{t("app.name")}</span>
      <ChevronRight size={12} className="text-faint" />
      <span className="font-medium text-ink2">{t(current.key)}</span>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const navItems = [...NAV, { to: "/app/settings", icon: Settings, key: "nav.settings", end: false }];

  return (
    <div className="flex min-h-dvh bg-canvas">
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {/* ---------------- sidebar (≥lg / landscape) ---------------- */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col justify-between border-r border-hairline bg-bg p-4 lg:flex">
        <div>
          <div className="mb-6 px-1">
            <Logo />
          </div>
          <div className="eyebrow mb-2 px-2">{t("app.section")}</div>
          <nav className="flex flex-col gap-0.5">
            {navItems.map(({ to, icon: Icon, key, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-control border px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? "border-hairline bg-surface2 text-ink"
                      : "border-transparent text-muted hover:bg-surface hover:text-ink2"
                  }`
                }
              >
                <Icon size={16} strokeWidth={1.8} />
                {t(key)}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex flex-col gap-2.5">
          <SyncFooter />
          <div className="flex items-center justify-between rounded-card border border-hairline bg-surface px-3 py-2">
            <span className="eyebrow">{t("theme.protocol")}</span>
            <ThemeSegmented />
          </div>
          {me && (
            <button
              type="button"
              onClick={() => navigate("/app/settings")}
              className="flex items-center gap-2.5 rounded-card border border-hairline bg-surface px-3 py-2.5 text-left hover:bg-surface2"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primarySoft text-[12px] font-bold text-primaryText">
                {me.name.slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold text-ink">{me.name}</div>
                <div className="truncate text-[10px] uppercase tracking-[0.14em] text-muted">
                  {me.role === "owner" ? t("settings.owner") : t("settings.friend")}
                </div>
              </div>
            </button>
          )}
        </div>
      </aside>

      {/* ---------------- content column ---------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-hairline bg-canvas/90 px-4 backdrop-blur lg:px-6">
          <div className="lg:hidden">
            <Logo compact />
          </div>
          <div className="hidden min-w-0 flex-1 items-center gap-3 lg:flex">
            <Breadcrumb />
            <span className="flex items-center gap-1.5 rounded-sm border border-hairline bg-surface px-1.5 py-1">
              <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden>
                <circle cx="6" cy="6" r="5" className="fill-positive/20" />
                <path d="M3.5 6.2 L5.2 7.9 L8.6 4.2" fill="none" className="stroke-positive" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              <span className="eyebrow !text-[10px]">{t("app.measured")}</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={t("search.placeholder")}
              onClick={() => setPaletteOpen(true)}
              className="hidden h-8 items-center gap-2 rounded-control border border-hairline bg-surface px-2.5 text-[12px] text-muted transition-colors hover:text-ink2 md:flex"
            >
              <Search size={13} />
              <span>{t("search.placeholder")}</span>
              <span className="num rounded-sm bg-hairline px-1 py-0.5 text-[9px] tracking-wide">⌘K</span>
            </button>
            <button
              type="button"
              aria-label={t("search.placeholder")}
              onClick={() => setPaletteOpen(true)}
              className="flex h-8 w-8 items-center justify-center rounded-control border border-hairline text-muted hover:bg-surface3 md:hidden"
            >
              <Search size={14} />
            </button>
            <button
              type="button"
              aria-label={t("nav.settings")}
              onClick={() => navigate("/app/settings")}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-primarySoft text-[11px] font-bold text-primaryText"
            >
              {(me?.name ?? "?").slice(0, 1).toUpperCase()}
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-24 pt-5 lg:px-6 lg:pb-10">
          {children}
        </main>
      </div>

      {/* ---------------- bottom nav (<lg / portrait) ---------------- */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-hairline bg-bg/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        <div className="grid grid-cols-7">
          {NAV.map(({ to, icon: Icon, key, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-1 py-2.5 text-[9px] font-medium transition-colors ${
                  isActive ? "text-primary" : "text-muted"
                }`
              }
            >
              <Icon size={19} strokeWidth={1.8} />
              <span className="max-w-full truncate px-0.5">{t(key)}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
