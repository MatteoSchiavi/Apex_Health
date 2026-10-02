"use client";

/**
 * Apex Health — Notifications dropdown.
 *
 * Surfaces the alerts from the daily overview (info / warning / alert severity)
 * as a small popover in the desktop topbar and mobile topbar. The badge shows
 * the count of unread alerts (we treat all overview alerts as "today's"). Click
 * anywhere on a notification to navigate to Overview.
 *
 * Visual law: monochrome + semantic dot colors (positive / warning / alert).
 */

import { useEffect, useRef, useState } from "react";
import { Bell, ChevronRight, CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { useT } from "@/lib/apex/i18nContext";
import { overview } from "@/lib/apex/data";
import { timeAgo } from "@/lib/apex/format";
import type { LucideIcon } from "lucide-react";

interface AlertItem {
  type: string;
  severity: "info" | "warning" | "alert";
  message: string;
}

export function NotificationsBell() {
  const ui = useApexUi();
  const t = useT();
  const [open, setOpen] = useState(false);
  const [readAlerts, setReadAlerts] = useState<Set<string>>(new Set());
  const ref = useRef<HTMLDivElement>(null);

  // Load read-alert ids from localStorage on mount
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("apex-read-alerts");
      if (raw) setReadAlerts(new Set(JSON.parse(raw)));
    } catch {
      /* ignore */
    }
  }, []);

  // Persist read-alert ids whenever they change
  useEffect(() => {
    try {
      window.localStorage.setItem("apex-read-alerts", JSON.stringify(Array.from(readAlerts)));
    } catch {
      /* ignore */
    }
  }, [readAlerts]);

  // Close on outside click + Escape
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const alerts = overview.alerts as AlertItem[];
  // Unread = alerts whose type+message hash is not in readAlerts
  const alertKey = (a: AlertItem) => `${a.type}:${a.message.slice(0, 40)}`;
  const unreadAlerts = alerts.filter((a) => !readAlerts.has(alertKey(a)));
  const unreadCount = unreadAlerts.length;

  // Mark a single alert as read (used on row click)
  const markRead = (a: AlertItem) => {
    setReadAlerts((cur) => {
      const next = new Set(cur);
      next.add(alertKey(a));
      return next;
    });
  };

  // Mark all as read when the dropdown is opened
  const markAllRead = () => {
    setReadAlerts(new Set(alerts.map(alertKey)));
  };

  // For severity color, consider only unread alerts
  const unreadHasAlerts = unreadAlerts.some((a) => a.severity === "alert");
  const unreadHasWarnings = unreadAlerts.some((a) => a.severity === "warning");

  // Bell tone reflects the highest severity among UNREAD alerts
  const bellTone = unreadHasAlerts
    ? "text-alertText border-alert/40 bg-alertSoft"
    : unreadHasWarnings
    ? "text-warningText border-warning/40 bg-warningSoft"
    : "text-muted border-hairline bg-surface hover:bg-surface2";

  // Bell dot color matches severity (only when unread)
  const dotColor = unreadHasAlerts ? "bg-alert" : unreadHasWarnings ? "bg-warning" : "bg-primary";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          // Mark all as read when opening (after a brief delay so the badge is visible)
          if (!open && unreadCount > 0) {
            setTimeout(() => markAllRead(), 1500);
          }
        }}
        className={`relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] border transition-colors ${bellTone} hover:text-ink`}
        aria-label={`Notifications (${unreadCount} unread)`}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Bell size={14} />
        {unreadCount > 0 && (
          <span
            className={`absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full ${dotColor} px-1 text-[8px] font-bold text-white`}
            aria-hidden
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-1.5 w-[360px] overflow-hidden rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
          role="dialog"
          aria-modal="false"
          aria-label={`${t("overview.open_alerts")} — ${unreadCount} ${unreadCount === 1 ? "alert" : "alerts"}`}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-hairline px-3 py-2.5">
            <div className="eyebrow">{t("overview.open_alerts")}</div>
            <div className="flex items-center gap-3">
              <span className="num text-[12px] text-faint">
                {unreadCount > 0 ? `${unreadCount} unread` : "All read"}
              </span>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={markAllRead}
                  className="num text-[12px] font-semibold text-primaryText hover:text-primaryText/80"
                >
                  Mark all read
                </button>
              )}
            </div>
          </div>

          {/* List */}
          <div className="scroll-area max-h-[360px] overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-[12px] text-muted">{t("common.no_data")}</div>
            ) : (
              <ul className="divide-y divide-hairline">
                {alerts.map((a, i) => {
                  const Icon: LucideIcon =
                    a.severity === "alert" ? AlertCircle : a.severity === "warning" ? AlertTriangle : CheckCircle2;
                  const iconColor =
                    a.severity === "alert"
                      ? "text-alertText bg-alertSoft"
                      : a.severity === "warning"
                      ? "text-warningText bg-warningSoft"
                      : "text-positiveText bg-positiveSoft";
                  const isRead = readAlerts.has(alertKey(a));
                  return (
                    <li key={i} className={isRead ? "opacity-60" : ""}>
                      <button
                        type="button"
                        onClick={() => {
                          markRead(a);
                          ui.setView("overview");
                          setOpen(false);
                        }}
                        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-surface2"
                      >
                        <div
                          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] ${iconColor}`}
                        >
                          <Icon size={11} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="eyebrow !text-[12px] uppercase">{a.type}</span>
                            {!isRead && (
                              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-label="unread" />
                            )}
                            <span className="num text-[12px] text-faint">
                              {timeAgo(new Date(Date.now() - i * 3600_000).toISOString(), ui.locale)}
                            </span>
                          </div>
                          <div className="mt-0.5 text-[12px] leading-[1.45] text-ink2">{a.message}</div>
                        </div>
                        <ChevronRight size={12} className="mt-2 text-faint" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-hairline px-3 py-2 text-center">
            <button
              type="button"
              onClick={() => {
                ui.setView("overview");
                setOpen(false);
              }}
              className="num text-[12px] font-semibold text-primaryText hover:text-primaryText/80"
            >
              {t("overview.title")} →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
