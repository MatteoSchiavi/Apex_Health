/**
 * App shell — the responsive frame every page lives in.
 *
 * Screen-ratio law (owner spec): ≥ lg the nav is a fixed LEFT sidebar
 * (like the approved mockups); below lg / portrait the sidebar collapses to
 * a BOTTOM tab bar so vertical screens navigate with a thumb and the space
 * is used for content. The topbar carries breadcrumb context, the theme
 * protocol toggle and the account chip on wide screens only.
 */

import { type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity,
  BarChart3,
  Bot,
  HeartPulse,
  Moon,
  Settings,
  Sun,
  Trophy,
} from "lucide-react";
import { useUi } from "../../app/stores/ui";

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
        <rect width="32" height="32" rx="8" className="fill-surface3" />
        <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
      </svg>
      {!compact && (
        <div className="flex items-baseline gap-1.5 tracking-tight">
          <span className="text-[15px] font-bold text-ink">{t("app.name")}</span>
          <span className="text-[11px] font-medium tracking-[0.14em] text-muted">
            {t("app.suffix")}
          </span>
        </div>
      )}
    </div>
  );
}

function ThemeToggle() {
  const { t } = useTranslation();
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  return (
    <button
      type="button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      title={t("theme.toggle")}
      className="flex h-9 items-center gap-2 rounded-control border border-hairline px-2.5 text-[12px] font-medium text-ink2 hover:bg-surface3"
    >
      {theme === "dark" ? <Moon size={14} /> : <Sun size={14} />}
      <span className="hidden sm:inline">
        {theme === "dark" ? t("theme.dark") : t("theme.light")}
      </span>
    </button>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const navigate = useNavigate();

  const navItems = [...NAV, { to: "/app/settings", icon: Settings, key: "nav.settings" }];

  return (
    <div className="flex min-h-dvh bg-canvas">
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
                  `flex items-center gap-2.5 rounded-control px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? "bg-surface3 text-ink"
                      : "text-muted hover:bg-surface hover:text-ink2"
                  }`
                }
              >
                <Icon size={16} strokeWidth={1.8} />
                {t(key)}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between rounded-card border border-hairline bg-surface px-3 py-2.5">
            <span className="eyebrow">{t("theme.protocol")}</span>
            <ThemeToggle />
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
                <div className="truncate text-[11px] uppercase tracking-wider text-muted">
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
          <div className="hidden items-center gap-2 lg:flex">
            <span className="eyebrow">{t("app.measured")}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={t("nav.settings")}
              onClick={() => navigate("/app/settings")}
              className="flex h-9 w-9 items-center justify-center rounded-control border border-hairline text-muted hover:bg-surface3 lg:hidden"
            >
              <Settings size={15} />
            </button>
            <ThemeToggle />
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
