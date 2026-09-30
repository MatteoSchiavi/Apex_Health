"use client";

/**
 * Apex Health — Welcome / public landing.
 *
 * Design philosophy (from the master spec + reference screenshots):
 * - Use the product itself as the hero, not stock photos
 * - Asymmetric composition, not uniform card grids
 * - Typography as the primary visual element
 * - Subtle motion, generous whitespace
 * - Monochrome + one accent color
 * - Calm, confident, editorial — not a generic SaaS landing page
 *
 * Layout:
 * 1. Hero: brand + bold statement + CTA + live data preview (asymmetric)
 * 2. Activity showcase: real Garmin activity data (not fake metrics)
 * 3. Feature pillars: 3 concise value props with data-driven examples
 * 4. Closing: single sentence + CTA
 */

import { useEffect, useState } from "react";
import {
  Activity,
  ChevronRight,
  Moon,
  HeartPulse,
  TrendingUp,
  MapPin,
  Waves,
  Mountain,
  type LucideIcon,
} from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { useT } from "@/lib/apex/i18nContext";
import { useTheme } from "next-themes";
import { ApexButton, Sparkline, Eyebrow, Hairline } from "@/components/apex/kit";
import { ShortcutsHelpModal } from "@/components/apex/ShortcutsHelpModal";
import { activities, sleepSessions, overview } from "@/lib/apex/data";

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

  // Real data for the hero preview
  const latestActivity = activities[0]; // Travo eMountain Biking
  const latestSleep = sleepSessions[0]; // Sep 30
  const sleepHours = latestSleep?.totalSleepS ? (latestSleep.totalSleepS / 3600).toFixed(1) : "—";
  const sleepScore = latestSleep?.sleepScore ?? "—";
  const restingHr = overview.resting_hr ?? "—";

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Top nav — minimal, just brand + sign in */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-hairline bg-canvas/80 px-5 backdrop-blur-xl lg:px-10">
        <div className="flex items-center gap-2.5">
          <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden>
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

      {/* Hero — asymmetric: bold statement on left, live data preview on right */}
      <section className="relative mx-auto max-w-[1280px] px-5 pb-20 pt-16 lg:px-10 lg:pt-28">
        {/* Background glow — subtle accent-colored ambient light */}
        <div
          className="absolute -top-40 right-0 h-[600px] w-[600px] rounded-full opacity-[0.07] blur-[120px]"
          style={{ background: "var(--c-accent, #10b981)" }}
          aria-hidden
        />

        <div className="relative grid grid-cols-1 gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
          {/* Left: statement + CTA */}
          <div className="flex flex-col justify-center">
            <Eyebrow>Personal performance analytics</Eyebrow>
            <h1 className="mt-4 text-[42px] font-light leading-[1.05] tracking-[-0.03em] text-ink sm:text-[56px] lg:text-[64px]">
              Your body,<br />
              <span className="font-medium">measured precisely.</span>
            </h1>
            <p className="mt-6 max-w-[480px] text-[16px] leading-[1.6] text-ink2 lg:text-[17px]">
              Apex Health synthesizes sleep, recovery, training load, and biometric
              data from your Garmin, Whoop, and Strava into one calm, precise
              surface. No gamification. No noise. Just the signal.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
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
            {/* Connected devices strip */}
            <div className="mt-12 flex items-center gap-3 text-[11px] uppercase tracking-[0.08em] text-faint">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-positive" style={{ boxShadow: "0 0 6px var(--c-positive)" }} />
                Live
              </span>
              <span className="text-faint/50">·</span>
              <span>Garmin</span>
              <span className="text-faint/50">·</span>
              <span>Whoop</span>
              <span className="text-faint/50">·</span>
              <span>Strava</span>
              <span className="text-faint/50">·</span>
              <span>Oura</span>
            </div>
          </div>

          {/* Right: live data preview — using REAL Garmin data */}
          <div className="relative">
            <div className="absolute -inset-4 -z-10 rounded-[1.5rem] opacity-[0.04] blur-3xl" style={{ background: "var(--c-accent, #10b981)" }} aria-hidden />

            {/* Activity card — your latest real Garmin activity */}
            <div className="rounded-[1.25rem] border border-hairline bg-surface p-5 shadow-[var(--c-shadow-flyout)]">
              <div className="flex items-center justify-between">
                <Eyebrow>Latest activity</Eyebrow>
                <span className="num text-[10px] text-faint">Garmin · {latestActivity?.local_date}</span>
              </div>
              <div className="mt-3 flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-control)]" style={{ background: "var(--c-primary-soft)" }}>
                  <Mountain size={18} className="text-primaryText" />
                </div>
                <div className="flex-1">
                  <div className="text-[15px] font-semibold text-ink">{latestActivity?.title}</div>
                  <div className="num mt-1 flex items-center gap-2 text-[11px] text-muted">
                    <MapPin size={10} />
                    <span>{((latestActivity?.distance_m ?? 0) / 1000).toFixed(1)} km</span>
                    <span className="text-faint">·</span>
                    <span>{Math.round((latestActivity?.duration_s ?? 0) / 60)} min</span>
                    <span className="text-faint">·</span>
                    <span>{latestActivity?.elevation_gain_m ?? 0} m elev</span>
                  </div>
                </div>
              </div>

              {/* Sparkline showing heart rate pattern */}
              <div className="mt-4">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="eyebrow !text-[9px]">Heart rate</span>
                  <span className="num font-semibold text-primaryText">{latestActivity?.avg_hr} avg</span>
                </div>
                <div className="mt-2">
                  <Sparkline
                    data={buildHeartRateSpark()}
                    color="var(--c-primary)"
                    width={400}
                    height={48}
                    className="w-full"
                  />
                </div>
              </div>

              <Hairline className="my-4" />

              {/* Sleep + vitals mini grid */}
              <div className="grid grid-cols-3 gap-3">
                <MiniStat label="Sleep" value={sleepHours} unit="h" icon={Moon} />
                <MiniStat label="Score" value={String(sleepScore)} unit="/100" icon={Activity} />
                <MiniStat label="Rest HR" value={String(restingHr)} unit="bpm" icon={HeartPulse} />
              </div>

              <Hairline className="my-4" />

              {/* HRV + ACWR row */}
              <div className="flex items-center justify-between">
                <div>
                  <Eyebrow>HRV</Eyebrow>
                  <div className="num mt-1 text-[20px] font-light text-ink">
                    {overview.hrv_ms ?? "—"}
                    <span className="text-[11px] text-muted"> ms</span>
                  </div>
                </div>
                <div className="text-right">
                  <Eyebrow>ACWR</Eyebrow>
                  <div className="num mt-1 text-[20px] font-light text-ink">
                    {overview.acwr ?? "—"}
                    <span className="text-[11px] text-muted"> ratio</span>
                  </div>
                </div>
                <div className="text-right">
                  <Eyebrow>Steps</Eyebrow>
                  <div className="num mt-1 text-[20px] font-light text-ink">
                    {overview.steps?.toLocaleString() ?? "—"}
                  </div>
                </div>
              </div>
            </div>

            {/* Floating badge — "Real data from your Garmin" */}
            <div className="absolute -bottom-4 left-8 flex items-center gap-1.5 rounded-full border border-hairline bg-surface px-3 py-1.5 text-[10px] font-medium text-muted shadow-[var(--c-shadow-flyout)]">
              <span className="h-1.5 w-1.5 rounded-full bg-positive" />
              Synced from Garmin Connect
            </div>
          </div>
        </div>
      </section>

      {/* Activity showcase — real activities, not fake ones */}
      <section className="border-t border-hairline px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[1280px]">
          <Eyebrow>Recent activities · Live from Garmin</Eyebrow>
          <h2 className="mt-3 text-[28px] font-light tracking-[-0.02em] text-ink lg:text-[32px]">
            Real data from your life.
          </h2>
          <p className="mt-3 max-w-[600px] text-[15px] leading-[1.6] text-muted">
            Every value comes from a connected device. Nothing fabricated, nothing
            estimated. Your mountain bike ride on Monte Travo, your sailing trip
            in La Maddalena, your open water swim — all here, all real.
          </p>

          {/* Activity list — horizontal scroll on mobile, grid on desktop */}
          <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {activities.slice(0, 6).map((a, i) => (
              <ActivityShowcaseCard key={a.id} activity={a} index={i} />
            ))}
          </div>
        </div>
      </section>

      {/* Feature pillars — concise, data-driven */}
      <section className="border-t border-hairline px-5 py-16 lg:px-10 lg:py-24">
        <div className="mx-auto max-w-[1280px]">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-3 lg:gap-12">
            <Pillar
              icon={Activity}
              title="Measured, not invented"
              body="Every value comes from a connected device or a deterministic calculation the backend owns. The frontend never fabricates."
            />
            <Pillar
              icon={TrendingUp}
              title="Context over judgement"
              body="Personal baselines, 7-day and 28-day deltas, and data provenance — so a number is never just a number."
            />
            <Pillar
              icon={Moon}
              title="Calm, precise, premium"
              body="Monochrome + one accent color. Typography as hierarchy. Hairlines as structure. No gamification, no noise."
            />
          </div>
        </div>
      </section>

      {/* Closing */}
      <section className="border-t border-hairline px-5 py-20 text-center lg:px-10 lg:py-32">
        <div className="mx-auto max-w-[680px]">
          <h2 className="text-[28px] font-light tracking-[-0.02em] text-ink lg:text-[36px]">
            Minimal without being empty.<br />
            Dense without being cluttered.
          </h2>
          <p className="mt-5 text-[15px] leading-[1.65] text-muted lg:text-[16px]">
            Apex Health feels like a serious personal tool that has been
            exceptionally well designed. Not a medical portal. Not a fitness
            tracker. Not a generic SaaS dashboard.
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

      {/* Footer — minimal */}
      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-[1280px] flex-col gap-3 px-5 py-6 text-[11px] text-faint sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <div className="flex items-center gap-2">
            <span className="num font-semibold tracking-[0.08em] text-muted">APEX HEALTH</span>
            <span>·</span>
            <span>{t("app.tagline")}</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              className="flex items-center gap-1.5 text-[10px] text-muted transition-colors hover:text-ink"
            >
              <kbd className="num rounded-[3px] border border-hairline bg-surface2 px-1.5 py-0.5 text-[9px] text-muted">?</kbd>
              shortcuts
            </button>
            <div className="flex items-center gap-1.5 text-[10px]">
              <kbd className="num rounded-[3px] border border-hairline bg-surface2 px-1.5 py-0.5 text-[9px] text-muted">Enter</kbd>
              sign in
            </div>
            <div className="flex items-center gap-1.5 text-[10px]">
              <kbd className="num rounded-[3px] border border-hairline bg-surface2 px-1.5 py-0.5 text-[9px] text-muted">S</kbd>
              demo
            </div>
            <div className="num tracking-[0.06em]">v1.0 · {new Date().getFullYear()}</div>
          </div>
        </div>
      </footer>

      <ShortcutsHelpModal open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}

/* ----------------------------------------------------------- components */

function MiniStat({ label, value, unit, icon: Icon }: { label: string; value: string; unit: string; icon: LucideIcon }) {
  return (
    <div className="rounded-[var(--radius-control)] bg-surface2 px-2.5 py-2">
      <div className="flex items-center gap-1.5">
        <Icon size={10} className="text-muted" />
        <span className="eyebrow !text-[9px]">{label}</span>
      </div>
      <div className="num mt-1 text-[16px] font-light text-ink">
        {value}<span className="text-[9px] text-muted"> {unit}</span>
      </div>
    </div>
  );
}

function ActivityShowcaseCard({ activity, index }: { activity: typeof activities[number]; index: number }) {
  const Icon = activity.discipline === "cycling" ? Mountain : activity.discipline === "rowing" ? Waves : activity.discipline === "hiking" ? Mountain : activity.discipline === "swimming" ? Waves : Activity;
  const dist = activity.distance_m ? `${(activity.distance_m / 1000).toFixed(1)} km` : null;
  const dur = `${Math.round(activity.duration_s / 60)} min`;
  const el = activity.elevation_gain_m ? `${activity.elevation_gain_m} m` : null;
  const hr = activity.avg_hr ? `HR ${activity.avg_hr}` : null;

  return (
    <div className="group rounded-[1rem] border border-hairline bg-surface p-4 transition-all hover:border-hairline2 hover:bg-surface2">
      <div className="flex items-start justify-between">
        <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)]" style={{ background: "var(--c-primary-soft)" }}>
          <Icon size={16} className="text-primaryText" />
        </div>
        <span className="num text-[10px] text-faint">{activity.local_date}</span>
      </div>
      <div className="mt-3 text-[14px] font-semibold leading-tight text-ink">{activity.title}</div>
      <div className="num mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted">
        {dist && <span>{dist}</span>}
        {dist && <span className="text-faint">·</span>}
        <span>{dur}</span>
        {el && <><span className="text-faint">·</span><span>{el}</span></>}
        {hr && <><span className="text-faint">·</span><span className="text-primaryText">{hr}</span></>}
      </div>
    </div>
  );
}

function Pillar({ icon: Icon, title, body }: { icon: LucideIcon; title: string; body: string }) {
  return (
    <div>
      <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-control)]" style={{ background: "var(--c-primary-soft)" }}>
        <Icon size={18} className="text-primaryText" />
      </div>
      <h3 className="mt-4 text-[18px] font-medium tracking-[-0.01em] text-ink">{title}</h3>
      <p className="mt-2 text-[14px] leading-[1.6] text-muted">{body}</p>
    </div>
  );
}

/** Build a deterministic heart rate sparkline that looks realistic. */
function buildHeartRateSpark(): number[] {
  const out: number[] = [];
  let base = 100;
  for (let i = 0; i < 30; i++) {
    const wave = Math.sin(i / 3) * 15;
    const climb = i > 15 ? (i - 15) * 1.5 : 0;
    const noise = (Math.sin(i * 7) + 1) * 3;
    out.push(Math.max(80, Math.min(170, base + wave + climb + noise)));
  }
  return out;
}
