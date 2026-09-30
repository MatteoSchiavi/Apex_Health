"use client";

/**
 * Apex Health — Welcome / public landing.
 *
 * Design law: more expressive than the dashboard, but still part of the same
 * visual system. Uses the product itself as the hero — no stock photos, no
 * fake AI imagery. Subtle motion reveals more through scroll.
 *
 * First viewport: brand + concise statement + primary CTA + sign-in / invite
 * entries + a strong product preview (the Overview dashboard, rendered).
 * Then: three pillars (Data / Composition / Context), a preview grid of the
 * five main pages, and a closing statement.
 */

import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  ChevronRight,
  Database,
  HandCoins,
  HeartPulse,
  Layers,
  Moon,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useApexUi } from "@/lib/apex";
import { useT } from "@/lib/apex/i18nContext";
import { useTheme } from "next-themes";
import { ApexButton, Sparkline, Eyebrow, Hairline } from "@/components/apex/kit";

export function WelcomeScreen() {
  const ui = useApexUi();
  const t = useT();
  const { theme, setTheme } = useTheme();

  // Lock dark theme on welcome? No — respect user's persisted theme.
  // Apply theme on mount in case no class is set yet (SSR safe).
  useEffect(() => {
    if (theme === undefined) {
      setTheme("dark");
    }
  }, [theme, setTheme]);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* top nav strip */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-hairline bg-canvas/95 px-5 backdrop-blur lg:px-10">
        <div className="flex items-center gap-2.5">
          <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="7" className="fill-primary/15" />
            <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
          </svg>
          <div className="flex items-baseline gap-1.5">
            <span className="text-[14px] font-bold tracking-[0.02em]">{t("app.name")}</span>
            <span className="text-[10px] font-medium tracking-[0.22em] text-muted">{t("app.suffix")}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => ui.setView("login")}
            className="num inline-flex h-8 items-center rounded-[var(--radius-control)] border border-hairline bg-surface px-3 text-[12px] font-semibold text-ink transition-colors hover:bg-surface2"
          >
            {t("auth.login")}
          </button>
          <ApexButton size="sm" onClick={() => ui.setView("join")}>
            {t("auth.redeem")}
          </ApexButton>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-[1240px] px-5 pb-12 pt-12 lg:px-10 lg:pb-20 lg:pt-20">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div className="flex flex-col justify-center">
            <Eyebrow>{t("welcome.eyebrow")}</Eyebrow>
            <h1 className="mt-3 text-[36px] font-semibold leading-[1.08] tracking-[-0.025em] text-ink sm:text-[44px] lg:text-[52px]">
              {t("welcome.title")}
            </h1>
            <p className="mt-5 max-w-[560px] text-[16px] leading-[1.6] text-ink2 lg:text-[17px]">
              {t("welcome.lead")}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
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
            <div className="mt-10 flex items-center gap-3 text-[11px] uppercase tracking-[0.08em] text-faint">
              <span className="flex items-center gap-1.5">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-positive" />
                </span>
                Garmin · Whoop · Strava · Oura · COROS
              </span>
            </div>
          </div>

          {/* Product preview — a synthesized dashboard snapshot */}
          <ProductPreview />
        </div>
      </section>

      <Hairline className="mx-auto max-w-[1240px] opacity-60" />

      {/* Three pillars */}
      <section className="mx-auto max-w-[1240px] px-5 py-14 lg:px-10 lg:py-20">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
          <Pillar
            icon={Database}
            title={t("welcome.pillar_data_title")}
            body={t("welcome.pillar_data_body")}
            spark={buildSpark(48, 7)}
          />
          <Pillar
            icon={Layers}
            title={t("welcome.pillar_composition_title")}
            body={t("welcome.pillar_composition_body")}
            spark={buildSpark(60, 7)}
          />
          <Pillar
            icon={HandCoins}
            title={t("welcome.pillar_context_title")}
            body={t("welcome.pillar_context_body")}
            spark={buildSpark(72, 7)}
          />
        </div>
      </section>

      <Hairline className="mx-auto max-w-[1240px] opacity-60" />

      {/* Preview grid */}
      <section className="mx-auto max-w-[1240px] px-5 py-14 lg:px-10 lg:py-20">
        <div className="mb-10 flex items-end justify-between gap-3">
          <div>
            <Eyebrow>{t("welcome.preview_title")}</Eyebrow>
            <h2 className="mt-2 text-[26px] font-semibold tracking-[-0.02em] lg:text-[30px]">
              {t("welcome.closing_title")}
            </h2>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <PreviewCard icon={Activity} label={t("nav.overview")} body={t("welcome.preview_overview")} onClick={() => ui.signIn()} />
          <PreviewCard icon={BarChart3} label={t("nav.activities")} body={t("welcome.preview_activities")} onClick={() => ui.signIn()} />
          <PreviewCard icon={Moon} label={t("nav.sleep")} body={t("welcome.preview_sleep")} onClick={() => ui.signIn()} />
          <PreviewCard icon={HeartPulse} label={t("nav.biometrics")} body={t("welcome.preview_biometrics")} onClick={() => ui.signIn()} />
          <PreviewCard icon={TrendingUp} label={t("nav.training")} body={t("welcome.preview_training")} onClick={() => ui.signIn()} />
          <PreviewCard icon={Bot} label={t("nav.coach")} body={t("welcome.preview_coach")} onClick={() => ui.signIn()} />
        </div>
      </section>

      <Hairline className="mx-auto max-w-[1240px] opacity-60" />

      {/* Closing */}
      <section className="mx-auto max-w-[1240px] px-5 py-16 text-center lg:px-10 lg:py-24">
        <Eyebrow className="flex justify-center">{t("welcome.closing_eyebrow")}</Eyebrow>
        <h2 className="mx-auto mt-4 max-w-[760px] text-[28px] font-semibold tracking-[-0.02em] lg:text-[36px]">
          {t("welcome.closing_title")}
        </h2>
        <p className="mx-auto mt-5 max-w-[680px] text-[15px] leading-[1.65] text-ink2 lg:text-[16px]">
          {t("welcome.closing_body")}
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
      </section>

      {/* Footer */}
      <footer className="border-t border-hairline bg-bg">
        <div className="mx-auto flex max-w-[1240px] flex-col gap-3 px-5 py-6 text-[11px] text-faint sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <div className="flex items-center gap-2">
            <span className="num font-semibold tracking-[0.08em] text-muted">APEX HEALTH</span>
            <span>·</span>
            <span>{t("app.tagline")}</span>
          </div>
          <div className="num tracking-[0.06em]">v0.9 · build 38a4 · {new Date().getFullYear()}</div>
        </div>
      </footer>
    </div>
  );
}

function ProductPreview() {
  const t = useT();
  // Synthesized readout — uses deterministic values, no random data
  const spark = buildSpark(48, 14);
  return (
    <div className="relative">
      <div className="absolute -inset-3 -z-10 rounded-[18px] bg-primarySoft opacity-50 blur-2xl" />
      <div className="rounded-[14px] border border-hairline bg-surface p-4 shadow-[var(--c-shadow-flyout)]">
        {/* status strip */}
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-hairline pb-3">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-positive" />
            </span>
            <span className="eyebrow !text-[10px]">{t("overview.live")}</span>
          </div>
          <div className="num text-[10px] tracking-[0.08em] text-faint">
            {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} · EPOCH
          </div>
        </div>

        {/* hero readiness */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-[var(--radius-card)] border border-hairline bg-surface2 p-4">
            <div className="flex items-center justify-between">
              <span className="eyebrow">{t("overview.adaptive_readiness")}</span>
              <span className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-positiveSoft px-1.5 py-0.5 text-[10px] font-semibold text-positiveText">
                +7 {t("overview.vs7d")}
              </span>
            </div>
            <div className="num mt-2 flex items-baseline gap-1.5 text-[44px] font-bold tracking-[-0.03em] text-ink">
              84
              <span className="text-[12px] font-medium text-muted">/100</span>
            </div>
            <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface3">
              <div className="h-full bg-primary" style={{ width: "84%" }} />
            </div>
            <div className="num mt-2 flex justify-between text-[10px] text-faint">
              <span>{t("overview.floor")}: 70</span>
              <span>{t("overview.cap")}: 92</span>
            </div>
          </div>
          <div className="rounded-[var(--radius-card)] border border-hairline bg-surface2 p-4">
            <div className="flex items-center justify-between">
              <span className="eyebrow">{t("overview.hrv_ms")}</span>
              <span className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-positiveSoft px-1.5 py-0.5 text-[10px] font-semibold text-positiveText">
                +8% {t("overview.vs_baseline")}
              </span>
            </div>
            <div className="num mt-2 flex items-baseline gap-1.5 text-[28px] font-bold text-ink">
              64<span className="text-[10px] font-medium text-muted">ms</span>
            </div>
            <div className="num mt-1 text-[10px] text-faint">
              {t("overview.baseline7")}: 59 ms · {t("overview.norm30")}: 62 ms
            </div>
            <div className="mt-3 flex h-7 items-end">
              <Sparkline data={spark} color="var(--c-primary)" width={220} height={28} className="w-full" />
            </div>
          </div>
        </div>

        {/* supporting strip */}
        <div className="mt-3 grid grid-cols-3 gap-2">
          {[
            { label: t("overview.resting_hr"), value: "48", unit: "bpm", delta: "−2", deltaTone: "text-positiveText" },
            { label: t("overview.spo2"), value: "97.4", unit: "%", delta: "+0.2", deltaTone: "text-positiveText" },
            { label: t("overview.sleep_score"), value: "88", unit: "/100", delta: "+5", deltaTone: "text-positiveText" },
          ].map((s) => (
            <div key={s.label} className="rounded-[var(--radius-card)] border border-hairline bg-surface2 p-2.5">
              <div className="eyebrow !text-[9px] truncate">{s.label}</div>
              <div className="num mt-1 flex items-baseline gap-1 text-[18px] font-bold text-ink">
                {s.value}
                <span className="text-[9px] font-medium text-muted">{s.unit}</span>
              </div>
              <div className={`num mt-0.5 text-[10px] font-semibold ${s.deltaTone}`}>{s.delta} {t("overview.vs7d")}</div>
            </div>
          ))}
        </div>

        {/* ACWR strip */}
        <div className="mt-3 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3">
          <div className="flex items-center justify-between">
            <span className="eyebrow !text-[9px]">{t("overview.acwr_index")}</span>
            <span className="num text-[10px] text-faint">{t("overview.optimal_window")}: 0.80–1.30</span>
          </div>
          <div className="num mt-2 flex items-baseline gap-1.5 text-[20px] font-bold text-ink">
            1.09<span className="text-[10px] font-medium text-muted">ratio</span>
          </div>
          <div className="mt-2 relative h-1.5 w-full overflow-hidden rounded-full bg-surface3">
            <div className="absolute inset-y-0 left-[20%] w-[55%] bg-positiveSoft/40" />
            <div className="absolute left-[34%] top-1/2 h-3 w-[3px] -translate-y-1/2 rounded-full bg-primary" />
          </div>
          <div className="num mt-1.5 flex justify-between text-[9px] text-faint">
            <span>0.5</span>
            <span>1.0</span>
            <span>1.5</span>
            <span>2.0</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Pillar({
  icon: Icon,
  title,
  body,
  spark,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  spark: number[];
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-hairline bg-surface p-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
        <Icon size={18} />
      </div>
      <div className="mt-4 text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</div>
      <p className="mt-2 text-[13px] leading-[1.6] text-muted">{body}</p>
      <div className="mt-4 flex h-7 items-end">
        <Sparkline data={spark} color="var(--c-positive)" width={220} height={28} className="w-full" />
      </div>
    </div>
  );
}

function PreviewCard({
  icon: Icon,
  label,
  body,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  body: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full flex-col rounded-[var(--radius-card)] border border-hairline bg-surface p-5 text-left transition-all hover:border-hairline2 hover:bg-surface2"
    >
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted transition-colors group-hover:bg-primarySoft group-hover:text-primaryText">
          <Icon size={14} />
        </div>
        <span className="eyebrow !text-[10px]">{label}</span>
      </div>
      <p className="mt-3 flex-1 text-[13px] leading-[1.55] text-ink2">{body}</p>
      <div className="num mt-4 flex items-center gap-1 text-[11px] font-semibold text-primaryText opacity-0 transition-opacity group-hover:opacity-100">
        {label}
        <ChevronRight size={12} />
      </div>
    </button>
  );
}

/** Build a deterministic sparkline. */
function buildSpark(seed: number, count: number): number[] {
  const out: number[] = [];
  let s = seed;
  for (let i = 0; i < count; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    out.push(40 + Math.sin(i / 2) * 18 + r * 12);
  }
  return out;
}
