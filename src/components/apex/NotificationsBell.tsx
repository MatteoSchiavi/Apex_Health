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
  const ref = useRef<HTMLDivElement>(null);

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
  const unreadCount = alerts.length;
  const hasAlerts = alerts.some((a) => a.severity === "alert");
  const hasWarnings = alerts.some((a) => a.severity === "warning");

  // Bell tone reflects the highest severity
  const bellTone = hasAlerts
    ? "text-alertText border-alert/40 bg-alertSoft"
    : hasWarnings
    ? "text-warningText border-warning/40 bg-warningSoft"
    : "text-muted border-hairline bg-surface hover:bg-surface2";

  // Bell dot color matches severity (only when unread)
  const dotColor = hasAlerts ? "bg-alert" : hasWarnings ? "bg-warning" : "bg-primary";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`relative flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] border transition-colors ${bellTone} hover:text-ink`}
        aria-label={`Notifications (${unreadCount})`}
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
            <span className="num text-[10px] text-faint">
              {unreadCount} {unreadCount === 1 ? "alert" : "alerts"}
            </span>
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
                  return (
                    <li key={i}>
                      <button
                        type="button"
                        onClick={() => {
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
                            <span className="eyebrow !text-[9px] uppercase">{a.type}</span>
                            <span className="num text-[9px] text-faint">
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
              className="num text-[11px] font-semibold text-primaryText hover:text-primaryText/80"
            >
              {t("overview.title")} →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
