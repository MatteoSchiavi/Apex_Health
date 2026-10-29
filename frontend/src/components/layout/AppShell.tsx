import {useSyncHealth} from "../../features/lab/syncHealth";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Activity,
  Bell,
  CalendarDays,
  FlaskConical,
  Wrench,
  ArrowUpRight,
  BarChart3,
  Bot,
  HeartPulse,
  Moon,
  LogOut,
  Search,
  Settings,
  Sun,
  Trophy,
  Users,
  X,
  ShieldCheck,
  MoreHorizontal,
  ChevronDown,
} from "lucide-react";
import { api, type DeviceOut } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { useLab } from "../../features/lab/shared";
import { ErrorNote, timeAgo } from "../kit";
import { NotificationPopover, type NotificationsData } from "../../features/lab/NotificationsPage";
import { FeedbackButton } from "../../features/feedback/FeedbackDialog";

import { SEARCH_TABS, searchText } from "./search-index";
import { METRIC_LABELS } from "../data";
import { friendlyDiscipline } from "../kit";

const NAV = [
  { to: "/app", icon: Activity, key: "redesign.shell.today", end: true },
  { to: "/app/training", icon: Trophy, key: "nav.training", end: false },
  { to: "/app/coach", icon: Bot, key: "nav.coach", end: false },
  { to: "/app/activities", icon: BarChart3, key: "nav.activities", end: false },
  { to: "/app/biometrics", icon: HeartPulse, key: "redesign.shell.health", end: false },
  { to: "/app/sleep", icon: Moon, key: "nav.sleep", end: false },
  { to: "/app/lab", icon: FlaskConical, key: "lab.nav", end: false },
  { to: "/app/calendar", icon: CalendarDays, key: "lab.calendar", end: false },
  { to: "/app/gear", icon: Wrench, key: "lab.gear", end: false },
  { to: "/app/social", icon: Users, key: "redesign.shell.challenges", end: false },
  { to: "/app/settings", icon: Settings, key: "nav.settings", end: false },
];
const TOOL_PATHS = ["/app/sleep", "/app/lab", "/app/calendar", "/app/gear", "/app/social"];
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
  const owner = useUi(s => s.me?.role === "owner");
  const uid = useUi(s => s.me?.user_id);
  const catalog = useQuery({ queryKey: ["metrics-catalog"], queryFn: () => api.get<Record<string, unknown>>("/metrics") });
  const recent = useQuery({ queryKey: ["search-activities", uid], queryFn: () => api.get<{ items: { id: number; local_date: string; discipline: string | null }[] }>("/activities?limit=50"), enabled: q.trim().length >= 2 });
  const destinations = [
    ...NAV.map(n => ({ to: n.to, label: t(n.key), terms: `${n.key} ${n.to}`, icon: n.icon })),
    ...(owner ? [{ to: "/admin", label: t("admin.title"), terms: "admin", icon: ShieldCheck }] : []),
    ...SEARCH_TABS.map(n => ({ to: n.to, label: `${t(n.parent)} · ${t(n.key)}`, terms: n.to, icon: Search })),
    ...Object.keys(catalog.data ?? {}).map(key => ({ to: `/app/biometrics/${key}`, label: METRIC_LABELS[key] ? t(METRIC_LABELS[key]) : key.replaceAll("_", " "), terms: key, icon: HeartPulse })),
    ...(recent.data?.items ?? []).map(a => ({ to: `/app/activities/${a.id}`, label: `${friendlyDiscipline(a.discipline, t)} · ${a.local_date}`, terms: a.discipline ?? "", icon: Activity })),
  ].filter(n => searchText(n.label + " " + n.terms).includes(searchText(q.trim())));
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
        className="w-full max-w-lg rounded-card border border-hairline bg-surface p-6"
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
            className="shell-icon"
          >
            <X size={18} />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto pt-3">
          {destinations.map((n) => (
            <button
              key={n.to}
              onClick={() => {
                navigate(n.to);
                onClose();
              }}
              className="flex min-h-11 w-full items-center gap-3 rounded-control px-3 py-3 text-left hover:bg-surface2"
            >
              <n.icon size={16} className="text-muted" />
              {n.label}
              <ArrowUpRight size={14} className="ml-auto text-muted" />
            </button>
          ))}
          {!destinations.length && <p className="py-6 text-muted">{t("search.no_results")}</p>}
        </div>
      </div>
    </div>
  );
}
export function AppShell({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const me = useUi((s) => s.me);
  const preferences = useLab<{ payload: { density: string } }[]>(
    "/lab/entries?kind=privacy_preferences",
  );
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const navigate = useNavigate();
  const location = useLocation();
  const preferenceSaving = useUi((s) => s.preferenceSaving);
  const preferenceError = useUi((s) => s.preferenceError);
  const qc = useQueryClient();
  const [search, setSearch] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(() => TOOL_PATHS.some(path => location.pathname === path || location.pathname.startsWith(path + "/")));
  const mobileMoreRoot = useRef<HTMLDivElement>(null);
  const notificationRoot = useRef<HTMLDivElement>(null);
  const notificationButton = useRef<HTMLButtonElement>(null);
  const notifications = useLab<NotificationsData>("/lab/notifications");
  const unread = notifications.data?.items.filter((n) => n.state === "created").length ?? 0;
  const syncHealth = useSyncHealth();
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get<DeviceOut[]>("/settings/devices"),
    refetchInterval: 120_000,
  });
  const searchOpener = useRef<HTMLElement | null>(null);
  const mobileMoreButton = useRef<HTMLButtonElement>(null);
  const latestSync = [...(devices.data ?? []).map(d=>d.last_synced_at), ...(syncHealth.data?.accounts ?? []).map(a=>a.last_success_at), ...(syncHealth.data?.feeds ?? []).map(f=>f.last_success_at)]
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
    if (!notificationsOpen) return;
    const onPointer = (e: PointerEvent) => {
      if (!notificationRoot.current?.contains(e.target as Node)) {
        setNotificationsOpen(false);
        notificationButton.current?.focus();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setNotificationsOpen(false);
        notificationButton.current?.focus();
      }
    };
    notificationRoot.current?.querySelector<HTMLElement>('[role="dialog"] a')?.focus();
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [notificationsOpen]);
  useEffect(() => {
    setNotificationsOpen(false);
    setMobileMoreOpen(false);
    if (TOOL_PATHS.some(path => location.pathname === path || location.pathname.startsWith(path + "/"))) setToolsOpen(true);
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const closeSearch = useCallback(() => setSearch(false), []);
  const inTraining = location.pathname.startsWith("/app/sports/");
  const inSharing = location.pathname.startsWith("/app/sharing");
  const isSectionActive = (to: string, end?: boolean) => (to === "/app/training" && inTraining) || (to === "/app/settings" && inSharing) || (end ? location.pathname === to : location.pathname === to || location.pathname.startsWith(to+"/"));
  const dailyPaths = ["/app", "/app/training", "/app/coach", "/app/activities"];
  const allNav = me?.role === "owner" ? [...NAV, { to: "/admin", icon: ShieldCheck, key: "admin.title", end: true }] : NAV;
  const mobilePrimary = dailyPaths.map(path => allNav.find(item => item.to === path)!);
  const dailyNav = NAV.filter(item => dailyPaths.includes(item.to) || item.to === "/app/biometrics");
  const toolsNav = NAV.filter(item => TOOL_PATHS.includes(item.to));
  const accountNav = allNav.filter(item => item.to === "/app/settings" || item.to === "/admin");
  const mobileMore = allNav.filter(item => !dailyPaths.includes(item.to));
  const mobileMoreActive = mobileMore.some(n => isSectionActive(n.to, n.end));
  const toolActive = toolsNav.some(n => isSectionActive(n.to, n.end));
  useEffect(() => {
    if (!mobileMoreOpen) return;
    const panel = mobileMoreRoot.current;
    panel?.querySelector<HTMLElement>("a,button")?.focus();
    const onPointer = (e: PointerEvent) => {
      if (!panel?.contains(e.target as Node) && !mobileMoreButton.current?.contains(e.target as Node)) {
        setMobileMoreOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileMoreOpen(false);
        mobileMoreButton.current?.focus();
      }
      if (e.key !== "Tab") return;
      const nodes = Array.from(panel?.querySelectorAll<HTMLElement>("a,button") ?? []);
      if (e.shiftKey && document.activeElement === nodes[0]) {
        e.preventDefault(); nodes.at(-1)?.focus();
      } else if (!e.shiftKey && document.activeElement === nodes.at(-1)) {
        e.preventDefault(); nodes[0]?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [mobileMoreOpen]);
  const navItem = ({ to, icon: Icon, key, end }: typeof NAV[number]) => (
    <Link key={to} to={to} aria-current={isSectionActive(to, end) ? "page" : undefined}
      className={`shell-nav-link ${isSectionActive(to, end) ? "is-active" : ""}`}>
      <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
      <span className="truncate">{t(key)}</span>
    </Link>
  );
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
    <div
      className="focus-workspace flex min-h-dvh bg-canvas"
      data-density={preferences.data?.[0]?.payload.density ?? "comfortable"}
    >
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
      <aside className="shell-sidebar sticky top-0 hidden h-dvh w-[224px] min-h-0 shrink-0 flex-col overflow-hidden border-r border-hairline px-4 py-6 lg:flex">
        <NavLink to="/app" aria-label="Apex Health" className="mx-3 mb-9 flex min-h-8 shrink-0 items-center text-ink">
          <Logo />
        </NavLink>
        <nav aria-label={t("design.navigation")} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <p className="focus-kicker mb-3 px-3">{t("redesign.shell.daily")}</p>
          <div className="space-y-1">{dailyNav.map(navItem)}</div>
          <button type="button" aria-expanded={toolsOpen} aria-controls="workspace-tools" onClick={() => setToolsOpen(open => !open)}
            className={`shell-nav-link mt-5 w-full text-left ${toolActive ? "is-active" : ""}`}>
            <MoreHorizontal size={18} aria-hidden="true" />
            <span className="flex-1">{t("redesign.shell.tools")}</span>
            <ChevronDown size={15} className={toolsOpen ? "rotate-180" : ""} aria-hidden="true" />
          </button>
          {toolsOpen && <div id="workspace-tools" className="mt-1 space-y-1 border-l border-hairline pl-2 ml-5">{toolsNav.map(navItem)}</div>}
          <div className="mt-auto space-y-1 pt-6">{accountNav.map(navItem)}</div>
        </nav>
        <div className="shrink-0 border-t border-hairline pt-4 mt-4">
          <NavLink to="/app/settings?tab=devices" className="block rounded-control px-3 py-2 hover:bg-surface2">
            <span className="status text-muted">
              {devices.isError ? t("design.sync_unavailable") : connected ? t("design.devices_count", { count: connected }) : t("sync.no_devices")}
            </span>
            <div className="mt-1 text-[11px] text-muted">
              {latestSync ? t("design.last_sync", { time: timeAgo(latestSync) }) : (syncHealth.data?.accounts?.some(a => a.has_successful_sync) || syncHealth.data?.feeds?.some(f => f.has_checkpoint || f.last_success_at || f.latest_measurement_at)) ? t("design.sync_time_missing") : t("design.sync_unavailable")}
            </div>
          </NavLink>
          <div className="mt-2 flex items-center gap-3 px-3">
            <button onClick={logout} aria-label={t("auth.logout")} title={t("auth.logout")} className="shell-icon"><LogOut size={17} /></button>
            <div className="min-w-0 flex-1"><p className="truncate text-[13px] font-medium">{me?.name}</p><span className="text-[12px] text-muted">{t("auth.logout")}</span></div>
          </div>
          {logoutError && <ErrorNote />}
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="shell-header flex min-h-16 items-center justify-between gap-3 border-b border-hairline px-4 lg:px-9">
          <div className="lg:hidden"><Logo /></div>
          <div className="hidden items-center gap-3 lg:flex">
            <span className="text-[12px] text-muted">{new Date().toLocaleDateString(i18n.language, { weekday: "long", month: "short", day: "numeric", timeZone: me?.timezone })}</span>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <div className="hidden sm:block"><FeedbackButton /></div>
            <div className="relative" ref={notificationRoot}>
              <button ref={notificationButton} type="button" aria-label={t("lab.notifications")}
                aria-expanded={notificationsOpen} aria-haspopup="dialog" onClick={() => setNotificationsOpen((v) => !v)}
                className="shell-icon relative">
                <Bell size={18} />
                {unread > 0 && <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-ink px-1 text-[10px] text-canvas">{unread > 9 ? "9+" : unread}</span>}
              </button>
              {notificationsOpen && <div role="dialog" aria-label={t("lab.notifications")}
                className="fixed inset-x-4 top-20 z-40 rounded-card border border-hairline bg-surface shadow-xl md:absolute md:left-auto md:right-0 md:top-full md:mt-2 md:w-[420px]">
                <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
                  <strong className="text-[14px]">{t("lab.notifications")}</strong>
                  <NavLink to="/app/settings?tab=notifications" onClick={() => setNotificationsOpen(false)} className="text-link text-[12px]">{t("lab.notification_preferences")}</NavLink>
                </div>
                <NotificationPopover onNavigate={() => setNotificationsOpen(false)} />
              </div>}
            </div>
            <button
              disabled={preferenceSaving}
              aria-label={t("theme.toggle")}
              title={t("theme.toggle")}
              className="shell-icon"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <div className="hidden md:block"><button
              className="shell-icon gap-2 md:!w-auto md:px-3"
              aria-label={t("search.placeholder")}
              onClick={(e) => {
                searchOpener.current = e.currentTarget;
                setSearch(true);
              }}
            >
              <Search size={18} className="shrink-0" />
              <span className="hidden whitespace-nowrap text-[12px] xl:inline">⌘ K</span>
            </button></div>
          </div>
        </header>
        <main
          id="main"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1440px] px-4 py-6 pb-28 focus:outline-none sm:px-6 lg:px-9 lg:py-8 lg:pb-8"
        >
          {logoutError && <div className="mb-5 lg:hidden"><ErrorNote /></div>}
          {preferenceError && (
            <div className="mb-5">
              <ErrorNote message={t("design.preference_failed")} />
            </div>
          )}
          {children}
        </main>
        <footer className="mx-5 mb-20 lg:mb-0 flex flex-wrap items-center justify-between gap-4 border-t border-hairline py-6 text-[12px] text-muted lg:mx-10">
          <span>Apex Health · {t("design.footer")}</span>
          <div className="flex items-center gap-4 lg:hidden"><FeedbackButton /><button onClick={logout} className="min-h-11">
            {t("auth.logout")}
          </button></div>
        </footer>
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
          {mobileMoreOpen && <div id="workspace-more" ref={mobileMoreRoot} role="dialog" aria-modal="true" aria-label={t("admin.more_navigation")} className="absolute bottom-full right-3 mb-3 max-h-[65dvh] w-72 overflow-y-auto rounded-card border border-hairline bg-surface p-2 shadow-xl"><nav aria-label={t("admin.more_navigation")}>
            {mobileMore.map(({ to, icon: Icon, key, end }) => <Link key={to} to={to} aria-current={isSectionActive(to,end) ? "page" : undefined} className={`shell-nav-link ${isSectionActive(to,end) ? "is-active" : ""}`}><Icon size={17} aria-hidden="true" />{t(key)}</Link>)}
            <button type="button" onClick={() => { searchOpener.current = mobileMoreButton.current; setMobileMoreOpen(false); setSearch(true); }} className="flex items-center gap-3 px-3 py-3 text-left text-sm text-muted hover:bg-surface2"><Search size={17} aria-hidden="true" />{t("search.placeholder")}</button>
            <button type="button" onClick={logout} className="border-t border-hairline px-3 py-3 text-left text-sm text-muted">{t("auth.logout")}</button>
          </nav></div>}
          <nav aria-label={t("design.navigation")} className="mx-auto grid max-w-xl grid-cols-5">
            {mobilePrimary.map(({ to, icon: Icon, key, end }) => <Link key={to} to={to} aria-current={isSectionActive(to,end) ? "page" : undefined} className={ `flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] ${isSectionActive(to,end) ? "text-ink" : "text-muted"}`}><Icon size={18} aria-hidden="true" /><span>{t(key)}</span></Link>)}
            <button ref={mobileMoreButton} type="button" aria-label={t("admin.more_navigation")} aria-expanded={mobileMoreOpen} aria-controls="workspace-more" aria-haspopup="dialog" onClick={() => setMobileMoreOpen((open) => !open)} className={`flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] ${mobileMoreActive || mobileMoreOpen ? "text-ink" : "text-muted"}`}><MoreHorizontal size={18} aria-hidden="true" /><span>{t("admin.more_navigation")}</span></button>
          </nav>
        </div>
      </div>
    </div>
  );
}
