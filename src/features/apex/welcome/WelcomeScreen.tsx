"use client";

/**
 * Apex Health — Welcome / public landing.
 *
 * DESIGN STUDY:
 * This is a LANDING page. People arrive here who are NOT logged in. They want
 * to understand: what is this product, why should I care, and how do I get in.
 * Showing their personal data here makes no sense — they haven't authenticated
 * yet. Use professional, aspirational demo data that tells the product story.
 *
 * WHAT TO PUT:
 * - Brand identity (name, logo)
 * - One clear value proposition (what does this product DO?)
 * - A visual of the product itself (not stock photos)
 * - Key features (concise — 3 max)
 * - Primary CTA (sign in / sign up)
 *
 * WHAT NOT TO PUT:
 * - Real user data (they're not logged in)
 * - Fake "live" sync indicators (dishonest)
 * - A wall of text
 * - Generic SaaS gradients
 */

import { useEffect, useState } from "react";
import { ChevronRight, Check } from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { useT } from "@/lib/apex/i18nContext";
import { useTheme } from "next-themes";
import { ApexButton, Eyebrow } from "@/components/apex/kit";
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
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-hairline bg-canvas/80 px-5 backdrop-blur-xl lg:px-10">
        <div className="flex items-center gap-2.5">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
          </svg>
          <div className="flex items-baseline gap-1.5">
            <span className="text-[14px] font-bold tracking-[0.02em]">APEX</span>
            <span className="text-[10px] font-medium tracking-[0.22em] text-muted">HEALTH</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => ui.setView("login")}
            className="num inline-flex h-8 items-center rounded-[var(--radius-control)] px-3 text-[12px] font-semibold text-muted transition-colors hover:text-ink"
          >
            {t("auth.login")}
          </button>
          <ApexButton size="sm" onClick={() => ui.setView("join")}>
            {t("auth.redeem")}
          </ApexButton>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-[960px] px-5 pb-24 pt-20 lg:px-10 lg:pt-32">
        {/* Subtle ambient glow */}
        <div
          className="absolute left-1/2 top-0 h-[400px] w-[600px] -translate-x-1/2 rounded-full opacity-[0.04] blur-[100px]"
          style={{ background: "var(--c-accent, #10b981)" }}
          aria-hidden
        />

        <div className="relative text-center">
          <Eyebrow className="flex justify-center">Personal health & performance analytics</Eyebrow>
          <h1 className="mt-6 text-[40px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink sm:text-[52px] lg:text-[60px]">
            Your body, decoded.
          </h1>
          <p className="mx-auto mt-6 max-w-[560px] text-[16px] leading-[1.6] text-ink2 lg:text-[17px]">
            Apex Health turns sleep, recovery, training load, and biometric data
            from your Garmin, Whoop, and Strava into one clear picture.
            No gamification. No noise. Just the signal that matters.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <ApexButton size="lg" onClick={() => ui.setView("login")} iconRight={<ChevronRight size={16} />}>
              {t("welcome.cta_primary")}
            </ApexButton>
            <button
              type="button"
              onClick={() => ui.setView("join")}
              className="num inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface px-5 text-[14px] font-semibold text-ink transition-colors hover:bg-surface2"
            >
              {t("welcome.cta_secondary")}
            </button>
          </div>
        </div>
      </section>

      {/* Product preview — a styled mockup of the dashboard, NOT real data */}
      <section className="border-t border-hairline px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[960px]">
          <Eyebrow className="flex justify-center">The product</Eyebrow>
          <h2 className="mt-3 text-center text-[24px] font-semibold tracking-[-0.02em] text-ink lg:text-[28px]">
            One dashboard. Every signal.
          </h2>

          {/* Mockup card — styled to look like the real dashboard but with clearly demo values */}
          <div className="mt-10 rounded-[1.25rem] border border-hairline bg-surface p-6 shadow-[var(--c-shadow-flyout)]">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <DemoMetric label="Readiness" value="84" unit="/100" />
              <DemoMetric label="HRV" value="64" unit="ms" />
              <DemoMetric label="Sleep" value="7h 42m" />
              <DemoMetric label="Resting HR" value="48" unit="bpm" />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="rounded-[var(--radius-card)] bg-surface2 p-4">
                <Eyebrow>Acute : Chronic Load</Eyebrow>
                <div className="num mt-2 text-[24px] font-bold text-ink">1.09</div>
                <div className="num mt-1 text-[10px] text-muted">Optimal window: 0.80–1.30</div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface3">
                  <div className="h-full bg-primary" style={{ width: "55%" }} />
                </div>
              </div>
              <div className="rounded-[var(--radius-card)] bg-surface2 p-4">
                <Eyebrow>Training Load</Eyebrow>
                <div className="num mt-2 text-[24px] font-bold text-ink">312 <span className="text-[11px] font-normal text-muted">TSS</span></div>
                <div className="num mt-1 text-[10px] text-muted">7-day rolling</div>
                {/* Simple bar chart mockup */}
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

      {/* What it does — concise feature list */}
      <section className="border-t border-hairline px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[960px]">
          <Eyebrow className="flex justify-center">What Apex Health does</Eyebrow>
          <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3 lg:gap-10">
            <Feature
              title="Connects your devices"
              body="Garmin, Whoop, Strava, Oura, COROS — all synced automatically. Your data stays yours."
            />
            <Feature
              title="Analyzes recovery & load"
              body="Sleep scores, HRV trends, ACWR, training load — computed from real data, not invented."
            />
            <Feature
              title="Explains what it means"
              body="An AI coach grounded in your measurements. Recommendations, not guesses. Medical disclaimers, always."
            />
          </div>
        </div>
      </section>

      {/* Supported devices */}
      <section className="border-t border-hairline px-5 py-12 lg:px-10">
        <div className="mx-auto max-w-[960px]">
          <div className="flex flex-wrap items-center justify-center gap-6 text-[13px] font-medium text-muted">
            <span>Garmin</span>
            <span className="text-faint">·</span>
            <span>Whoop</span>
            <span className="text-faint">·</span>
            <span>Strava</span>
            <span className="text-faint">·</span>
            <span>Oura</span>
            <span className="text-faint">·</span>
            <span>COROS</span>
            <span className="text-faint">·</span>
            <span>Manual entry</span>
          </div>
        </div>
      </section>

      {/* Closing */}
      <section className="border-t border-hairline px-5 py-20 text-center lg:px-10 lg:py-28">
        <div className="mx-auto max-w-[600px]">
          <h2 className="text-[24px] font-semibold tracking-[-0.02em] text-ink lg:text-[28px]">
            Ready to see your data?
          </h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <ApexButton size="lg" onClick={() => ui.setView("login")} iconRight={<ChevronRight size={16} />}>
              {t("welcome.cta_primary")}
            </ApexButton>
            <button
              type="button"
              onClick={() => ui.setView("join")}
              className="num inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface px-5 text-[14px] font-semibold text-ink transition-colors hover:bg-surface2"
            >
              {t("welcome.cta_secondary")}
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-[960px] flex-col gap-3 px-5 py-6 text-[11px] text-faint sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <div className="flex items-center gap-2">
            <span className="num font-semibold tracking-[0.08em] text-muted">APEX HEALTH</span>
            <span>·</span>
            <span>{t("app.tagline")}</span>
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              className="flex items-center gap-1 text-[10px] text-muted transition-colors hover:text-ink"
            >
              <kbd className="num rounded-[3px] border border-hairline bg-surface2 px-1.5 py-0.5 text-[9px]">?</kbd>
              shortcuts
            </button>
            <div className="num tracking-[0.06em]">v1.0 · {new Date().getFullYear()}</div>
          </div>
        </div>
      </footer>

      <ShortcutsHelpModal open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}

/* ----------------------------------------------------------- components */

function DemoMetric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-[var(--radius-card)] bg-surface2 p-4">
      <Eyebrow>{label}</Eyebrow>
      <div className="num mt-2 text-[28px] font-bold tracking-[-0.02em] text-ink">
        {value}
        {unit && <span className="text-[12px] font-medium text-muted"> {unit}</span>}
      </div>
    </div>
  );
}

function Feature({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)]" style={{ background: "var(--c-primary-soft)" }}>
        <Check size={14} className="text-primaryText" />
      </div>
      <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
      <p className="text-[14px] leading-[1.55] text-muted">{body}</p>
    </div>
  );
}
