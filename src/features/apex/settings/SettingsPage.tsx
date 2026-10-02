"use client";

/**
 * Apex Health — Settings page.
 *
 * Re-skinned per ui-language/RULES.md (9 principles):
 *   1. One answer: "Tune the app to your units, theme, and connected devices."
 *   2. No big hero — settings are about control, not data.
 *   3. No outlines on cards; no card-in-card. No nested bordered tiles.
 *   4. Sentence-case labels, 13px minimum (no all-caps eyebrows).
 *   5. Numbers stay white; status = dot + word (StatusDot).
 *   6. Accent (orange) is not a status colour — used for accent picker + actions.
 *   7. Plain words ("Settings", not "SETTINGS").
 *   8. Charts: n/a.
 *   9. Sections: use `Section` label + content. Devices table is rows.
 *
 * State-affecting controls (theme, locale, units, sign out) actually work via
 * the store. Cosmetic actions (invite, disconnect device) fire a toast.
 *
 * `GarminConnectForm` is left intact (off-limits per task) — it renders inside
 * the Devices section without any extra wrapping from this page.
 */

import { useState } from "react";
import { Volume2, Loader2, Square, RefreshCw } from "lucide-react";
import { useTheme } from "next-themes";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { devices, me } from "@/lib/apex/data";
import { fmtDate, timeAgo } from "@/lib/apex/format";
import { GarminConnectForm } from "./GarminConnectForm";
import { useToast } from "@/hooks/use-toast";
import {
  ApexButton,
  Card,
  Hairline,
  PageSentence,
  Section,
  Segmented,
  StatusDot,
} from "@/components/apex/kit";
import { ThemePreviewCard } from "@/components/apex/ThemePreviewCard";

/* ----------------------------------------------------------- accent colors */

/** Accent colors — only 3, all distinct from the status colours (green/amber/red).
 * RULES principle 6: "The accent is not a status colour." Orange is the default. */
const ACCENT_COLORS = [
  { name: "Orange", value: "#FF7A1A" },
  { name: "Ice blue", value: "#4CC9F0" },
  { name: "Lime", value: "#B6F24A" },
] as const;

/* ----------------------------------------------------------- input styles */

const inputCls =
  "num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2 text-[14px] text-ink placeholder:text-faint transition-colors";

/* ------------------------------------------------------------ main page */

export function SettingsPage() {
  const t = useT();
  const ui = useApexUi();
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  const [aiTier, setAiTier] = useState<"off" | "basic" | "pro">(
    (me.ai_access_tier as "off" | "basic" | "pro") ?? "pro"
  );
  const [previewState, setPreviewState] = useState<"idle" | "loading" | "playing">("idle");
  const [syncing, setSyncing] = useState(false);

  const applyTheme = (next: "dark" | "light") => {
    setTheme(next === "dark" ? "dark" : "light");
    ui.setTheme(next);
  };

  return (
    <div className="mx-auto max-w-[1240px] space-y-8 px-6 py-8">
      {/* ===== Title + page sentence ===== */}
      <div>
        <h1 className="page-title">Settings</h1>
        <PageSentence className="mt-2">
          Tune the app to your units, theme, and connected devices.
        </PageSentence>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* ===== Profile (full row) ===== */}
        <Card className="lg:col-span-2">
          <Section label={t("settings.profile_title")}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                toast({ title: t("settings.saved") });
              }}
              className="space-y-4"
            >
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label={t("settings.name")}>
                  <input className={inputCls} defaultValue={me.name} type="text" />
                </Field>
                <Field label={t("settings.email")}>
                  <input className={inputCls} defaultValue={me.email} type="email" />
                </Field>
                <Field label={t("settings.dob")}>
                  <input className={inputCls} defaultValue={me.dob ?? ""} type="date" />
                </Field>
                <Field label={t("settings.sex")}>
                  <select className={inputCls} defaultValue={me.sex ?? "other"}>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="other">Other</option>
                  </select>
                </Field>
                <Field label={t("settings.height")}>
                  <div className="flex items-center gap-2">
                    <input
                      className={inputCls}
                      type="number"
                      defaultValue={
                        ui.units === "metric"
                          ? me.height_cm ?? 0
                          : Math.round((me.height_cm ?? 0) / 30.48)
                      }
                    />
                    <span className="num shrink-0 text-[13px] font-medium text-ink2">
                      {ui.units === "metric" ? "cm" : "ft"}
                    </span>
                  </div>
                </Field>
                <Field label={t("settings.timezone")}>
                  <input className={inputCls} defaultValue={me.timezone} type="text" />
                </Field>
              </div>

              <div className="flex flex-wrap items-end justify-between gap-3">
                <Field label={t("settings.units")}>
                  <Segmented
                    value={ui.units}
                    onChange={(v) => ui.setUnits(v as "metric" | "imperial")}
                    options={[
                      { value: "metric", label: t("settings.metric") },
                      { value: "imperial", label: t("settings.imperial") },
                    ]}
                  />
                </Field>
                <ApexButton type="submit" variant="secondary" size="sm">
                  {t("settings.save_changes")}
                </ApexButton>
              </div>
            </form>
          </Section>
        </Card>

        {/* ===== Appearance ===== */}
        <Card>
          <Section label={t("settings.appearance_title")}>
            <div className="space-y-5">
              <Field label={t("settings.language")}>
                <Segmented
                  value={ui.locale}
                  onChange={(v) => ui.setLocale(v as "en" | "it")}
                  options={[
                    { value: "en", label: "EN" },
                    { value: "it", label: "IT" },
                  ]}
                />
                <LocalePreview locale={ui.locale} />
              </Field>

              <Field label={t("settings.theme")}>
                <div className="grid grid-cols-2 gap-2 sm:max-w-[400px]">
                  <ThemePreviewCard
                    previewTheme="dark"
                    isActive={(theme ?? "dark") === "dark"}
                    onApply={() => applyTheme("dark")}
                  />
                  <ThemePreviewCard
                    previewTheme="light"
                    isActive={theme === "light"}
                    onApply={() => applyTheme("light")}
                  />
                </div>
                <div className="mt-2">
                  <Segmented
                    value={(theme as "dark" | "light") ?? "dark"}
                    onChange={(v) => applyTheme(v as "dark" | "light")}
                    options={[
                      { value: "dark", label: t("theme.dark") },
                      { value: "light", label: t("theme.light") },
                    ]}
                  />
                </div>
              </Field>

              {/* Accent color selector — no borders on swatches */}
              <Field label="Accent color">
                <div className="flex flex-wrap items-center gap-3">
                  {ACCENT_COLORS.map((c) => {
                    const selected = ui.accentColor === c.value;
                    return (
                      <button
                        key={c.value}
                        type="button"
                        onClick={() => ui.setAccentColor(c.value)}
                        className="flex flex-col items-center gap-1.5"
                        aria-label={`Accent: ${c.name}`}
                        aria-pressed={selected}
                      >
                        <span
                          className="flex h-9 w-9 items-center justify-center rounded-full transition-transform"
                          style={{
                            background: c.value,
                            transform: selected ? "scale(1.08)" : "scale(1)",
                          }}
                        >
                          {selected && (
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                              <path
                                d="M3.5 8L6.5 11L12.5 5"
                                stroke="white"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          )}
                        </span>
                        <span className={`text-[13px] ${selected ? "font-medium text-ink" : "text-ink2"}`}>
                          {c.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <p className="num mt-2 text-[13px] text-ink2">
                  The accent color drives interactive states, active nav, buttons, and chart highlights across the entire app.
                </p>
              </Field>

              <p className="num text-[13px] text-ink2">{t("settings.theme_note")}</p>

              {/* TTS voice + auto-play — flat, no nested bordered tile */}
              <Hairline />
              <div>
                <div className="text-[14px] font-medium text-ink2">Coach voice (TTS)</div>
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <select
                    value={ui.ttsVoice}
                    onChange={(e) => ui.setTtsVoice(e.target.value)}
                    className={`${inputCls}`}
                    aria-label="TTS voice"
                  >
                    <option value="tongtong">tongtong — warm, friendly</option>
                    <option value="chuichui">chuichui — lively</option>
                    <option value="xiaochen">xiaochen — composed, professional</option>
                    <option value="jam">jam — British gentleman</option>
                    <option value="kazi">kazi — clear, standard</option>
                    <option value="douji">douji — natural, fluent</option>
                    <option value="luodo">luodo — expressive</option>
                  </select>
                  <label className="flex cursor-pointer items-center justify-between gap-2 rounded-[var(--radius-control)] bg-surface2 px-2.5 py-2">
                    <span className="text-[14px] text-ink2">Auto-play responses</span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={ui.ttsAutoPlay}
                      onClick={() => ui.setTtsAutoPlay(!ui.ttsAutoPlay)}
                      className={`relative h-5 w-9 rounded-full transition-colors ${ui.ttsAutoPlay ? "bg-primary" : "bg-surface3"}`}
                      aria-label="Toggle auto-play"
                    >
                      <span
                        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                          ui.ttsAutoPlay ? "translate-x-4" : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  </label>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <ApexButton
                    variant="secondary"
                    size="sm"
                    onClick={async () => {
                      setPreviewState("loading");
                      try {
                        const resp = await fetch("/api/tts", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            text: "Apex Health. Recovery score eighty-four. HRV sixty-four milliseconds.",
                            voice: ui.ttsVoice,
                            speed: 1.0,
                          }),
                        });
                        if (!resp.ok) throw new Error("TTS failed");
                        const blob = await resp.blob();
                        const url = URL.createObjectURL(blob);
                        const audio = new Audio(url);
                        audio.onplay = () => setPreviewState("playing");
                        audio.onended = () => setPreviewState("idle");
                        audio.onerror = () => setPreviewState("idle");
                        await audio.play();
                      } catch {
                        setPreviewState("idle");
                      }
                    }}
                    icon={
                      previewState === "loading" ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : previewState === "playing" ? (
                        <Square size={11} fill="currentColor" />
                      ) : (
                        <Volume2 size={13} />
                      )
                    }
                  >
                    <span className="hidden sm:inline">
                      {previewState === "loading"
                        ? "Loading…"
                        : previewState === "playing"
                        ? "Playing…"
                        : "Preview voice"}
                    </span>
                  </ApexButton>
                  <span className="num text-[13px] text-ink2">
                    Plays a short sample with the selected voice.
                  </span>
                </div>
                <p className="num mt-2 text-[13px] text-ink2">
                  Voice used when reading Coach messages aloud. Auto-play reads each new assistant response automatically.
                </p>
              </div>
            </div>
          </Section>
        </Card>

        {/* ===== Security & Sessions ===== */}
        <Card>
          <Section label={t("settings.security_title")}>
            <div className="space-y-4">
              <div>
                <div className="text-[14px] text-ink2">{t("settings.session_current")}</div>
                <div className="num mt-1 text-[16px] font-semibold text-ink">
                  {t("settings.signed_in_as", { email: me.email })}
                </div>
                <div className="num mt-0.5 text-[13px] text-ink2">{t("settings.last_active")}</div>
              </div>
              <ApexButton
                variant="danger"
                size="md"
                className="w-full"
                onClick={() => ui.signOut()}
              >
                {t("settings.sign_out")}
              </ApexButton>
            </div>
          </Section>
        </Card>

        {/* ===== Devices & Integrations (full row) ===== */}
        <Card pad={false} className="lg:col-span-2">
          <div className="p-6 pb-3">
            <div className="flex items-end justify-between gap-3">
              <div className="text-[14px] font-medium text-ink2">{t("settings.devices_title")}</div>
              <ApexButton
                variant="secondary"
                size="sm"
                onClick={async () => {
                  setSyncing(true);
                  try {
                    const resp = await fetch("/api/garmin/sync", { method: "POST" });
                    const data = await resp.json();
                    if (data.ok) {
                      toast({ title: `Synced ${data.report.activities} activities, ${data.report.sleepSessions} sleep sessions` });
                    } else {
                      toast({ title: `Sync failed: ${data.error}`, variant: "destructive" });
                    }
                  } catch (e) {
                    toast({ title: `Sync failed: ${e instanceof Error ? e.message : "unknown"}`, variant: "destructive" });
                  }
                  setSyncing(false);
                }}
                icon={syncing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                disabled={syncing}
              >
                <span className="hidden sm:inline">{syncing ? "Syncing…" : "Sync now"}</span>
              </ApexButton>
            </div>
          </div>
          <Hairline />
          <div className="overflow-x-auto">
            <table className="num w-full min-w-[640px] text-left text-[14px]">
              <thead>
                <tr className="border-b border-hairline text-ink2">
                  <th className="px-4 py-2 font-medium">{t("settings.provider")}</th>
                  <th className="px-4 py-2 font-medium">{t("settings.status")}</th>
                  <th className="px-4 py-2 font-medium">{t("settings.is_main")}</th>
                  <th className="px-4 py-2 font-medium">{t("settings.last_sync")}</th>
                  <th className="px-4 py-2 font-medium">{t("settings.connected_at")}</th>
                  <th className="px-4 py-2 text-right font-medium">{t("settings.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {devices.map((d) => (
                  <tr key={d.integration_id} className="border-b border-hairline last:border-0">
                    <td className="px-4 py-3 font-semibold text-ink">{d.provider}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={d.status} t={t} />
                    </td>
                    <td className="px-4 py-3">
                      {d.is_main ? (
                        <StatusDot tone="neutral" label={t("settings.main")} />
                      ) : (
                        <span className="text-ink2">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink2">
                      {d.last_synced_at ? timeAgo(d.last_synced_at, ui.locale) : "—"}
                    </td>
                    <td className="px-4 py-3 text-ink2">
                      {fmtDate(d.connected_at, ui.locale)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {!d.is_main && (
                          <ApexButton
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toast({ title: t("settings.toast_main", { provider: d.provider }) })
                            }
                          >
                            {t("settings.make_main")}
                          </ApexButton>
                        )}
                        {d.status === "active" ? (
                          <ApexButton
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toast({ title: t("settings.toast_paused", { provider: d.provider }) })
                            }
                          >
                            {t("settings.pause")}
                          </ApexButton>
                        ) : (
                          <ApexButton
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toast({ title: t("settings.toast_resumed", { provider: d.provider }) })
                            }
                          >
                            {t("settings.resume")}
                          </ApexButton>
                        )}
                        <ApexButton
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            toast({ title: t("settings.toast_disconnect", { provider: d.provider }) })
                          }
                        >
                          {t("settings.disconnect")}
                        </ApexButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Garmin Connect form — left intact (off-limits per task). */}
          <GarminConnectForm onConnected={() => { setSyncing(false); }} />
        </Card>

        {/* ===== Owner Settings (owner-only) ===== */}
        {me.role === "owner" && (
          <Card>
            <Section label={t("settings.owner_title")}>
              <div className="space-y-4">
                <OwnerInvite />
                <div>
                  <div className="text-[14px] font-medium text-ink2">{t("settings.ai_tier")}</div>
                  <div className="mt-2">
                    <Segmented
                      value={aiTier}
                      onChange={(v) => setAiTier(v as "off" | "basic" | "pro")}
                      options={[
                        { value: "off", label: t("settings.ai_tier_off") },
                        { value: "basic", label: t("settings.ai_tier_basic") },
                        { value: "pro", label: t("settings.ai_tier_pro") },
                      ]}
                    />
                  </div>
                </div>
                <p className="num text-[13px] text-ink2">{t("settings.invite_disclaimer")}</p>
              </div>
            </Section>
          </Card>
        )}

        {/* ===== About ===== */}
        <Card className={me.role === "owner" ? "" : "lg:col-span-2"}>
          <Section label={t("settings.about")}>
            <div className="divide-y divide-[var(--c-divider)]">
              <AboutRow label={t("settings.version")} value={t("settings.version_value")} />
              <AboutRow label={t("settings.build")} value={t("settings.build_value")} />
              <AboutRow label={t("settings.stack")} value={t("settings.stack_value")} />
              <AboutRow label={t("settings.repo")} value={t("settings.repo_value")} />
            </div>
          </Section>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ sub-components */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="block">
      <div className="mb-1.5 text-[14px] font-medium text-ink2">{label}</div>
      {children}
    </div>
  );
}

function AboutRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2.5">
      <span className="text-[14px] text-ink2">{label}</span>
      <span className="num truncate text-[14px] font-medium text-ink">{value}</span>
    </div>
  );
}

function StatusBadge({
  status,
  t,
}: {
  status: "active" | "paused" | "error";
  t: (p: string) => string;
}) {
  const tone = status === "active" ? "ok" : status === "paused" ? "watch" : "alert";
  return <StatusDot tone={tone} label={t(`settings.${status}`)} />;
}

function OwnerInvite() {
  const t = useT();
  const { toast } = useToast();
  const [email, setEmail] = useState("");

  const onInvite = (e: React.FormEvent) => {
    e.preventDefault();
    const code = `APEX-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
    toast({ title: t("settings.toast_invite", { code }) });
    setEmail("");
  };

  return (
    <form onSubmit={onInvite} className="space-y-2">
      <div className="text-[14px] font-medium text-ink2">{t("settings.invite_friend")}</div>
      <div className="flex items-center gap-2">
        <input
          className={inputCls}
          type="email"
          placeholder={t("settings.invite_placeholder")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <ApexButton type="submit" size="sm" className="shrink-0">
          {t("settings.invite_button")}
        </ApexButton>
      </div>
    </form>
  );
}

/* ----------------------------------------------------------- locale preview */

function LocalePreview({ locale }: { locale: "en" | "it" }) {
  const sampleDate = new Date();
  const localeTag = locale === "it" ? "it-IT" : "en-GB";
  const dateStr = sampleDate.toLocaleDateString(localeTag, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const timeStr = sampleDate.toLocaleTimeString(localeTag, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const numStr = (1234.5).toLocaleString(localeTag, { minimumFractionDigits: 1 });
  return (
    <div className="mt-3 rounded-[var(--radius-control)] bg-surface2 p-3">
      <div className="num flex items-center justify-between gap-2 text-[13px]">
        <span className="text-ink2">Preview ({localeTag})</span>
        <span className="text-ink2">{locale === "it" ? "Italiano" : "English"}</span>
      </div>
      <div className="num mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[14px] text-ink">
        <span className="font-semibold">{dateStr}</span>
        <span className="text-ink2" aria-hidden>·</span>
        <span className="tabular-nums">{timeStr}</span>
        <span className="text-ink2" aria-hidden>·</span>
        <span className="tabular-nums">{numStr}</span>
      </div>
    </div>
  );
}
