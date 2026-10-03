import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bot,
  HeartPulse,
  Moon,
  Search,
  Settings,
  Sun,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { api, type DeviceOut } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { ErrorNote, timeAgo } from "../kit";

const NAV = [
  { to: "/app", icon: Activity, key: "nav.overview", end: true },
  {
    to: "/app/biometrics",
    icon: HeartPulse,
    key: "nav.biometrics",
    end: false,
  },
  { to: "/app/activities", icon: BarChart3, key: "nav.activities", end: false },
  { to: "/app/sleep", icon: Moon, key: "nav.sleep", end: false },
  { to: "/app/training", icon: Trophy, key: "nav.training", end: false },
  { to: "/app/coach", icon: Bot, key: "nav.coach", end: false },
  { to: "/app/social", icon: Users, key: "nav.social", end: false },
  { to: "/app/settings", icon: Settings, key: "nav.settings", end: false },
];
export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <svg width="30" height="32" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 2L31 29H23L16 15L9 29H1Z" fill="currentColor" />
      </svg>
      <span className="text-[19px] font-semibold tracking-[-.05em]">
        APEX<span className="ml-1.5 font-normal text-muted">Health</span>
      </span>
    </div>
  );
}
function SearchDialog({
  onClose,
  returnFocus,
}: {
  onClose: () => void;
  returnFocus: HTMLElement | null;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = returnFocus;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab") return;
      const nodes = Array.from(
        root.current?.querySelectorAll<HTMLElement>("input,button") ?? [],
      );
      const first = nodes[0],
        last = nodes.at(-1);
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, [onClose, returnFocus]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-5 pt-[15vh]"
      onMouseDown={onClose}
    >
      <div
        ref={root}
        role="dialog"
        aria-modal="true"
        aria-label={t("search.placeholder")}
        className="w-full max-w-lg bg-surface p-6"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-hairline pb-4">
          <Search size={18} className="text-muted" />
          <input
            autoFocus
            aria-label={t("search.placeholder")}
            placeholder={t("search.placeholder")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="min-w-0 flex-1 bg-transparent outline-none"
          />
          <button
            aria-label={t("common.close")}
            onClick={onClose}
            className="p-2"
          >
            <X size={18} />
          </button>
        </div>
        <div className="pt-3">
          {NAV.filter((n) =>
            t(n.key).toLowerCase().includes(q.toLowerCase()),
          ).map((n) => (
            <button
              key={n.to}
              onClick={() => {
                navigate(n.to);
                onClose();
              }}
              className="flex w-full items-center gap-3 px-2 py-3 text-left hover:bg-surface2"
            >
              <n.icon size={16} className="text-muted" />
              {t(n.key)}
              <ArrowUpRight size={14} className="ml-auto text-muted" />
            </button>
          ))}
          {!NAV.some((n) =>
            t(n.key).toLowerCase().includes(q.toLowerCase()),
          ) && <p className="py-6 text-muted">{t("search.no_results")}</p>}
        </div>
      </div>
    </div>
  );
}
export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const navigate = useNavigate();
  const location = useLocation();
  const preferenceSaving = useUi((s) => s.preferenceSaving);
  const preferenceError = useUi((s) => s.preferenceError);
  const qc = useQueryClient();
  const [search, setSearch] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<DeviceOut[]>("/settings/devices"),
    refetchInterval: 120_000,
  });
  const searchOpener = useRef<HTMLElement | null>(null);
  const latestSync = (devices.data ?? [])
    .map((d) => d.last_synced_at)
    .filter((v): v is string => !!v)
    .sort()
    .at(-1);
  const connected = (devices.data ?? []).filter(
    (d) => d.status === "active",
  ).length;
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchOpener.current = document.activeElement as HTMLElement;
        setSearch((v) => !v);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const closeSearch = useCallback(() => setSearch(false), []);
  const current =
    NAV.find((n) =>
      n.end ? location.pathname === n.to : location.pathname.startsWith(n.to),
    ) ?? NAV[0];
  async function logout() {
    try {
      await api.post("/auth/logout");
      qc.clear();
      useUi.getState().setMe(null);
      navigate("/login");
    } catch {
      setLogoutError(true);
    }
  }
  return (
    <div className="flex min-h-dvh bg-canvas">
      <a
        href="#main"
        className="absolute -top-20 left-4 z-50 bg-ink px-4 py-3 text-canvas focus:top-4"
      >
        {t("design.skip")}
      </a>
      {search && (
        <SearchDialog
          onClose={closeSearch}
          returnFocus={searchOpener.current}
        />
      )}
      <aside className="sticky top-0 hidden h-dvh w-[224px] shrink-0 flex-col border-r border-hairline px-6 py-8 lg:flex">
        <NavLink to="/app" className="mb-14" aria-label="Apex Health">
          <Logo />
        </NavLink>
        <div className="mb-4 text-[12px] text-muted">
          {t("design.workspace")}
        </div>
        <nav
          aria-label={t("design.navigation")}
          className="flex flex-col gap-1"
        >
          {NAV.map(({ to, icon: Icon, key, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                "flex items-center gap-3 px-3 py-3 text-[14px] transition-colors " +
                (isActive
                  ? "bg-ink font-medium text-canvas"
                  : "text-muted hover:bg-surface2 hover:text-ink")
              }
            >
              <Icon size={17} strokeWidth={1.6} />
              <span>{t(key)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto pt-10">
          <NavLink
            to="/app/settings?tab=devices"
            className="block border-b border-hairline pb-5"
          >
            <span className="status text-muted">
              {devices.isError
                ? t("design.sync_unavailable")
                : connected
                  ? t("design.devices_count", { count: connected })
                  : t("sync.no_devices")}
            </span>
            <div className="mt-2 text-[12px] text-muted">
              {latestSync
                ? t("design.last_sync", { time: timeAgo(latestSync) })
                : t("settings.never")}
            </div>
          </NavLink>
          <div className="mt-5 flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center bg-surface2 font-medium">
              {me?.name.slice(0, 1).toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium">{me?.name}</p>
              <button
                onClick={logout}
                className="text-[12px] text-muted hover:text-ink"
              >
                {t("auth.logout")}
              </button>
            </div>
          </div>
          {logoutError && <ErrorNote />}
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex h-[80px] items-center justify-between gap-4 border-b border-hairline px-5 lg:px-10">
          <div className="lg:hidden">
            <Logo />
          </div>
          <div className="hidden items-center gap-3 text-[13px] lg:flex">
            <span className="text-muted">Apex Health</span>
            <span className="text-faint">/</span>
            {t(current.key)}
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden text-[13px] text-muted md:inline">
              {new Date().toLocaleDateString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
                timeZone: me?.timezone,
              })}
            </span>
            <button
              disabled={preferenceSaving}
              aria-label={t("theme.toggle")}
              title={t("theme.toggle")}
              className="p-2 text-muted hover:text-ink"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <button
              aria-label={t("search.placeholder")}
              onClick={(e) => {
                searchOpener.current = e.currentTarget;
                setSearch(true);
              }}
              className="flex items-center gap-3 p-2 text-muted hover:text-ink"
            >
              <Search size={18} />
              <span className="hidden text-[12px] xl:inline">⌘ K</span>
            </button>
          </div>
        </header>
        <nav
          aria-label={t("design.navigation")}
          className="flex gap-6 overflow-x-auto border-b border-hairline px-5 lg:hidden"
        >
          {NAV.map((n) => (
            <NavLink
              to={n.to}
              end={n.end}
              key={n.to}
              className={({ isActive }) =>
                "shrink-0 border-b-2 py-4 text-[13px] " +
                (isActive
                  ? "border-ink font-semibold text-ink"
                  : "border-transparent text-muted")
              }
            >
              {t(n.key)}
            </NavLink>
          ))}
        </nav>
        <main
          id="main"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1600px] px-5 py-8 focus:outline-none md:px-8 lg:px-10 lg:py-10"
        >
          {preferenceError && (
            <div className="mb-5">
              <ErrorNote message={t("design.preference_failed")} />
            </div>
          )}
          {children}
        </main>
        <footer className="mx-5 flex flex-wrap items-center justify-between gap-4 border-t border-hairline py-6 text-[12px] text-muted lg:mx-10">
          <span>Apex Health · {t("design.footer")}</span>
          <button onClick={logout} className="lg:hidden">
            {t("auth.logout")}
          </button>
        </footer>
      </div>
    </div>
  );
}
