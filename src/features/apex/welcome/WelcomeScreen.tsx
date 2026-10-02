"use client";

/**
 * Apex Health — Welcome / public landing.
 *
 * Re-skinned against ui-language/RULES.md:
 *   - One hero line, not a wall of equal cards.
 *   - Plain words (no "telemetry", "biosignal", "calibrated").
 *   - Feature pillars are flat rows/sections, not bordered cards.
 *   - Sentence-case labels, 14px minimum.
 *   - No borders on demo surfaces (surface contrast only).
 *
 * WHAT TO PUT (unchanged intent):
 *  - Brand identity (name, logo)
 *  - One clear value proposition
 *  - A visual of the product (demo dashboard)
 *  - Key features (concise — 3 max)
 *  - Primary CTA (sign in / sign up)
 *
 * WHAT NOT TO PUT:
 *  - Real user data (they're not logged in)
 *  - Fake "live" sync indicators (dishonest)
 *  - A wall of text
 *  - Generic SaaS gradients
 */

import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { useT } from "@/lib/apex/i18nContext";
import { useTheme } from "next-themes";
import { ApexButton, PageSentence } from "@/components/apex/kit";
import { ShortcutsHelpModal } from "@/components/apex/ShortcutsHelpModal";

export function WelcomeScreen() {
  const ui = useApexUi();
  const t = useT();
  const { theme, setTheme } = useTheme();
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    if (theme === undefined) setTheme("dark");
  }, [theme, setTheme]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "?" || (e.key === "/" && e.shiftKey)) { e.preventDefault(); setHelpOpen(true); }
      else if (e.key === "Enter") { e.preventDefault(); ui.setView("login"); }
      else if (e.key.toLowerCase() === "j") { e.preventDefault(); ui.setView("join"); }
      else if (e.key.toLowerCase() === "s") { e.preventDefault(); ui.signIn(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ui]);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Nav */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-canvas/80 px-5 backdrop-blur-xl lg:px-10">
        <div className="flex items-center gap-2.5">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
          </svg>
          <div className="flex items-baseline gap-1.5">
            <span className="text-[14px] font-bold tracking-[0.02em]">Apex</span>
            <span className="text-[13px] font-medium text-muted">Health</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => ui.setView("login")}
            className="num inline-flex h-8 items-center rounded-[var(--radius-control)] px-3 text-[13px] font-semibold text-muted transition-colors hover:text-ink"
          >
            {t("auth.login")}
          </button>
          <ApexButton size="sm" onClick={() => ui.setView("join")}>
            {t("auth.redeem")}
          </ApexButton>
        </div>
      </header>

      {/* Hero — one big line, not a wall of cards */}
      <section className="relative mx-auto max-w-[960px] px-5 pb-24 pt-20 lg:px-10 lg:pt-32">
        {/* Subtle ambient glow (kept — it's decoration, not data) */}
        <div
          className="absolute left-1/2 top-0 h-[400px] w-[600px] -translate-x-1/2 rounded-full opacity-[0.04] blur-[100px]"
          style={{ background: "var(--c-accent)" }}
          aria-hidden
        />

        <div className="relative text-center">
          {/* One sentence, 20px, answering "what is Apex?" */}
          <PageSentence className="mx-auto max-w-[640px] !text-left sm:!text-center">
            Apex turns your sleep, recovery, training load, and labs into one clear picture — no gamification, no noise, just the signal that matters.
          </PageSentence>

          {/* Hero line — the one big thing on the page */}
          <h1 className="mt-8 text-[40px] font-semibold leading-[1.05] tracking-[-0.03em] text-ink sm:text-[52px] lg:text-[64px]">
            Your body, decoded.
          </h1>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <ApexButton size="lg" onClick={() => ui.setView("login")} iconRight={<ChevronRight size={16} />}>
              {t("welcome.cta_primary")}
            </ApexButton>
            <button
              type="button"
              onClick={() => ui.setView("join")}
              className="num inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-surface2 px-5 text-[14px] font-semibold text-ink transition-colors hover:bg-surface3"
            >
              {t("welcome.cta_secondary")}
            </button>
          </div>
        </div>
      </section>

      {/* Product preview — a styled mockup of the dashboard, NOT real data.
          Surface contrast only, no borders on the demo tiles. */}
      <section className="px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[960px]">
          <div className="text-[14px] font-medium text-ink2">The product</div>
          <div className="mt-2 text-[28px] font-semibold tracking-[-0.02em] text-ink">
            One dashboard. Every signal.
          </div>

          {/* Mockup surface — one borderless Card holding flat sub-surfaces */}
          <div className="mt-10 rounded-[var(--radius-card)] bg-surface p-6">
            {/* Top demo metrics row (flat, surface-2 contrast only) */}
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <DemoMetric label="Readiness" value="84" unit="/100" />
              <DemoMetric label="HRV" value="64" unit="ms" />
              <DemoMetric label="Sleep" value="7h 42m" />
              <DemoMetric label="Resting HR" value="48" unit="bpm" />
            </div>

            {/* Hairline divider between groups — allowed for grouping inside a Card */}
            <div className="my-7 h-px w-full bg-[var(--c-divider)]" />

            {/* Lower demo row — two flat sub-surfaces (no borders) */}
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div className="rounded-[var(--radius-control)] bg-surface2 p-5">
                <div className="text-[14px] font-medium text-ink2">Acute : Chronic Load</div>
                <div className="num mt-2 text-[32px] font-semibold leading-none text-ink">
                  1.09
                </div>
                <div className="num mt-1.5 text-[13px] text-ink2">
                  Optimal window: 0.80–1.30
                </div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface3">
                  <div className="h-full bg-primary" style={{ width: "55%" }} />
                </div>
              </div>
              <div className="rounded-[var(--radius-control)] bg-surface2 p-5">
                <div className="text-[14px] font-medium text-ink2">Training load</div>
                <div className="num mt-2 text-[32px] font-semibold leading-none text-ink">
                  312 <span className="text-[14px] font-medium text-ink2">TSS</span>
                </div>
                <div className="num mt-1.5 text-[13px] text-ink2">
                  7-day rolling
                </div>
                {/* Simple bar chart mockup — accent (orange) only, no per-bar state */}
                <div className="mt-3 flex h-10 items-end gap-1">
                  {[40, 55, 35, 70, 45, 60, 80].map((h, i) => (
                    <div key={i} className="flex-1 rounded-t bg-primary/30" style={{ height: `${h}%` }} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* What it does — flat feature rows (not bordered cards) */}
      <section className="px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[960px]">
          <div className="text-[14px] font-medium text-ink2">What Apex does</div>
          <div className="mt-6 divide-y divide-[var(--c-divider)]">
            <FeatureRow
              title="Connects your devices"
              body="Garmin, Whoop, Strava, Oura, COROS — synced automatically. Your data stays yours."
            />
            <FeatureRow
              title="Reads your recovery and load"
              body="Sleep scores, HRV trends, training load, ACWR — computed from real numbers, not invented."
            />
            <FeatureRow
              title="Explains what it means"
              body="An AI coach grounded in your measurements. Recommendations, not guesses. Medical disclaimers, always."
            />
          </div>
        </div>
      </section>

      {/* Supported devices */}
      <section className="px-5 py-12 lg:px-10">
        <div className="mx-auto max-w-[960px]">
          <div className="flex flex-wrap items-center justify-center gap-6 text-[14px] font-medium text-muted">
            <span>Garmin</span>
            <span className="text-ink3">·</span>
            <span>Whoop</span>
            <span className="text-ink3">·</span>
            <span>Strava</span>
            <span className="text-ink3">·</span>
            <span>Oura</span>
            <span className="text-ink3">·</span>
            <span>COROS</span>
            <span className="text-ink3">·</span>
            <span>Manual entry</span>
          </div>
        </div>
      </section>

      {/* Closing */}
      <section className="px-5 py-20 text-center lg:px-10 lg:py-28">
        <div className="mx-auto max-w-[600px]">
          <h2 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">
            Ready to see your data?
          </h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <ApexButton size="lg" onClick={() => ui.setView("login")} iconRight={<ChevronRight size={16} />}>
              {t("welcome.cta_primary")}
            </ApexButton>
            <button
              type="button"
              onClick={() => ui.setView("join")}
              className="num inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-surface2 px-5 text-[14px] font-semibold text-ink transition-colors hover:bg-surface3"
            >
              {t("welcome.cta_secondary")}
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--c-divider)]">
        <div className="mx-auto flex max-w-[960px] flex-col gap-3 px-5 py-6 text-[13px] text-ink3 sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <div className="flex items-center gap-2">
            <span className="num font-semibold tracking-[0.04em] text-muted">Apex Health</span>
            <span>·</span>
            <span>{t("app.tagline")}</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              className="flex items-center gap-1 text-[13px] text-muted transition-colors hover:text-ink"
            >
              <kbd className="num rounded-[3px] bg-surface2 px-1.5 py-0.5 text-[12px]">?</kbd>
              shortcuts
            </button>
            <div className="num tracking-[0.04em]">v1.0 · {new Date().getFullYear()}</div>
          </div>
        </div>
      </footer>

      <ShortcutsHelpModal open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}

/* ----------------------------------------------------------- components */

/** DemoMetric — a small flat stat in the mock dashboard. No border, no eyebrow
 *  caps. Sentence-case 14px label + 28px white number. */
function DemoMetric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="text-[14px] text-ink2">{label}</div>
      <div className="num mt-1 text-[28px] font-semibold tracking-[-0.02em] text-ink">
        {value}
        {unit && <span className="ml-1 text-[14px] font-medium text-ink2">{unit}</span>}
      </div>
    </div>
  );
}

/** FeatureRow — one row per feature. Label + body, separated by divider.
 *  Not a bordered card. */
function FeatureRow({ title, body }: { title: string; body: string }) {
  return (
    <div className="grid grid-cols-1 gap-2 py-6 sm:grid-cols-3 sm:gap-8">
      <h3 className="text-[20px] font-semibold tracking-[-0.01em] text-ink sm:col-span-1">
        {title}
      </h3>
      <p className="text-[16px] leading-[1.55] text-ink2 sm:col-span-2">{body}</p>
    </div>
  );
}
