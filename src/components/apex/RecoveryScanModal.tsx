"use client";

/**
 * Apex Health — Recovery Scan modal.
 *
 * Opens a centered modal that calls /api/recovery-scan with the current
 * overview data. Shows a calm loading state, then renders the structured AI
 * scan: one-sentence summary, highlights, watch items, recommendation, and an
 * always-present medical disclaimer.
 *
 * Design law: AI is subordinate to the data. The modal feels like a quiet,
 * factual interpretation — not a flashy "AI INSIGHT" card. Kind-badged sections
 * match the Coach page (data / recommendation / disclaimer).
 */

import { useEffect, useState } from "react";
import { Activity, CheckCircle2, AlertTriangle, Lightbulb, ShieldAlert, X, Loader2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { overview } from "@/lib/apex/data";
import { fmtNum } from "@/lib/apex/format";
import { ApexButton, Eyebrow, Hairline } from "@/components/apex/kit";

interface ScanResult {
  one_sentence_summary: string;
  highlights: string[];
  watch_items: string[];
  recommendation: string;
  disclaimer: string;
}

export function RecoveryScanModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset + fetch when opened
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setScan(null);
    setError(null);
    setLoading(true);

    (async () => {
      try {
        const resp = await fetch("/api/recovery-scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(overview),
        });
        const json = await resp.json();
        if (cancelled) return;
        if (!json.ok) {
          throw new Error(json.error || "Failed to generate scan");
        }
        setScan(json.scan as ScanResult);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Unknown error");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open]);

  // Close on Esc
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[8vh] sm:pt-[12vh]"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Recovery scan"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className="relative w-full max-w-[560px] overflow-hidden rounded-[var(--radius-card)] border border-hairline2 bg-surface shadow-[var(--c-shadow-flyout)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
              <Activity size={16} />
            </div>
            <div>
              <div className="eyebrow">{t("overview.adaptive_readiness")}</div>
              <div className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
                Recovery Scan
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
        <div className="scroll-area max-h-[60vh] overflow-y-auto px-5 py-4">
          {/* Loading */}
          {loading && (
            <div
              className="flex flex-col items-center justify-center py-12 text-center"
              aria-live="polite"
              aria-busy="true"
              role="status"
            >
              <Loader2 size={28} className="animate-spin text-primaryText" />
              <div className="mt-3 text-[13px] text-muted">{t("coach.loading")}</div>
              <div className="num mt-1 text-[10px] text-faint">
                Readiness {fmtNum(overview.readiness.value, 0)} · HRV {fmtNum(overview.hrv_ms, 0)} ms · ACWR {fmtNum(overview.acwr, 2)}
              </div>
            </div>
          )}

          {/* Error */}
          {!loading && error && (
            <div
              className="flex flex-col items-center justify-center gap-3 py-12 text-center"
              aria-live="assertive"
              role="alert"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-control)] bg-alertSoft text-alertText">
                <AlertTriangle size={18} />
              </div>
              <div className="text-[13px] font-medium text-ink">{t("common.error")}</div>
              <div className="max-w-[320px] text-[11px] text-muted">{error}</div>
            </div>
          )}

          {/* Result */}
          {!loading && !error && scan && (
            <div aria-live="polite" role="status">
              {/* One-sentence summary */}
              <div>
                <Eyebrow>Summary</Eyebrow>
                <p className="mt-1 text-[15px] leading-[1.55] text-ink">{scan.one_sentence_summary}</p>
              </div>

              <Hairline />

              {/* Highlights */}
              {scan.highlights?.length > 0 && (
                <div>
                  <Eyebrow>
                    <span className="flex items-center gap-1.5">
                      <CheckCircle2 size={10} className="text-positiveText" />
                      Positive findings
                    </span>
                  </Eyebrow>
                  <ul className="mt-2 space-y-1.5">
                    {scan.highlights.map((h, i) => (
                      <li key={i} className="flex items-start gap-2 text-[13px] leading-[1.5] text-ink2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-positive" />
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Watch items */}
              {scan.watch_items?.length > 0 && (
                <div>
                  <Eyebrow>
                    <span className="flex items-center gap-1.5">
                      <AlertTriangle size={10} className="text-warningText" />
                      Worth monitoring
                    </span>
                  </Eyebrow>
                  <ul className="mt-2 space-y-1.5">
                    {scan.watch_items.map((h, i) => (
                      <li key={i} className="flex items-start gap-2 text-[13px] leading-[1.5] text-ink2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-warning" />
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <Hairline />

              {/* Recommendation */}
              {scan.recommendation && (
                <div className="rounded-[var(--radius-card)] border border-primary/30 bg-primarySoft p-3">
                  <Eyebrow>
                    <span className="flex items-center gap-1.5 text-primaryText">
                      <Lightbulb size={10} />
                      Recommendation
                    </span>
                  </Eyebrow>
                  <p className="mt-1 text-[13px] leading-[1.55] text-ink">{scan.recommendation}</p>
                </div>
              )}

              {/* Disclaimer */}
              <div className="flex items-start gap-2 rounded-[var(--radius-card)] border border-alert/20 bg-alertSoft/50 p-3">
                <ShieldAlert size={12} className="mt-0.5 shrink-0 text-alertText/70" />
                <p className="text-[11px] italic leading-[1.5] text-alertText/80">{scan.disclaimer}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3">
          <div className="num text-[10px] text-faint">
            {overview.date} · {t("overview.epoch")}
          </div>
          <div className="flex items-center gap-2">
            <ApexButton variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
              {t("common.close")}
            </ApexButton>
            <ApexButton
              size="sm"
              onClick={() => {
                ui_setView("coach");
                onOpenChange(false);
              }}
            >
              {t("nav.coach")} →
            </ApexButton>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper to navigate to coach from the modal footer
import { useApexUi } from "@/lib/apex";
function ui_setView(view: Parameters<ReturnType<typeof useApexUi>["setView"]>[0]) {
  useApexUi.getState().setView(view);
}
