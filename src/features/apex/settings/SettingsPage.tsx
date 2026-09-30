"use client";

/**
 * Apex Health — Settings page.
 *
 * Route purpose: "How do I control the system?"
 *
 * Sectioned layout — each section is a Card with a SectionHeader. Profile and
 * Devices & Integrations span the full row; Appearance + Security, and
 * Owner + About pair on a 2-col grid on desktop. Inputs are uncontrolled and
 * prefilled from `me`. State-affecting controls (theme, locale, units, sign
 * out) actually work via the store. Cosmetic actions (invite, disconnect
 * device, save changes) fire a toast via the radix `useToast` hook.
 *
 * Design law: monochrome + 3 semantic colors, hairlines, label-caps eyebrows,
 * tabular figures, mono where appropriate. No new visual vocabulary.
 */

import { useState } from "react";
import { useTheme } from "next-themes";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { devices, me } from "@/lib/apex/data";
import { fmtDate, timeAgo } from "@/lib/apex/format";
import { useToast } from "@/hooks/use-toast";
import {
  ApexButton,
  Badge,
  Card,
  Eyebrow,
  Hairline,
  PageHeader,
  SectionHeader,
  Segmented,
} from "@/components/apex/kit";
import { ThemePreviewCard } from "@/components/apex/ThemePreviewCard";

/* ----------------------------------------------------------- input styles */

const inputCls =
  "num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2 text-[13px] text-ink placeholder:text-faint transition-colors";

const labelCls = "eyebrow mb-1.5 block";

/* ------------------------------------------------------------ main page */

export function SettingsPage() {
  const t = useT();
  const ui = useApexUi();
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  const [aiTier, setAiTier] = useState<"off" | "basic" | "pro">(
    (me.ai_access_tier as "off" | "basic" | "pro") ?? "pro"
  );

  const applyTheme = (next: "dark" | "light") => {
    setTheme(next === "dark" ? "dark" : "light");
    ui.setTheme(next);
  };

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader title={t("settings.title")} subtitle={t("settings.title_sub")} />

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* 1. Profile (full row) */}
        <Card className="lg:col-span-2">
          <SectionHeader eyebrow={t("settings.profile_title")} title={t("settings.profile_title")} />
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
                <select
                  className={inputCls}
                  defaultValue={me.sex ?? "other"}
                >
                  <option value="male">male</option>
                  <option value="female">female</option>
                  <option value="other">other</option>
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
                  <span className="num shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
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
        </Card>

        {/* 2. Appearance (half) */}
        <Card>
          <SectionHeader eyebrow={t("settings.appearance_title")} title={t("settings.appearance_title")} />
          <div className="space-y-4">
            <Field label={t("settings.language")}>
              <Segmented
                value={ui.locale}
                onChange={(v) => ui.setLocale(v as "en" | "it")}
                options={[
                  { value: "en", label: "EN" },
                  { value: "it", label: "IT" },
                ]}
              />
              {/* Locale-aware date/time preview */}
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
            <p className="num text-[11px] text-faint">
              {t("settings.theme_note")}
            </p>

            {/* TTS voice + auto-play settings */}
            <div className="mt-2 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3">
              <div className="eyebrow !text-[10px]">Coach voice (TTS)</div>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <select
                  value={ui.ttsVoice}
                  onChange={(e) => ui.setTtsVoice(e.target.value)}
                  className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-2 text-[12px] text-ink focus:border-primary focus:outline-none"
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
                <label className="flex cursor-pointer items-center justify-between gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-2">
                  <span className="text-[12px] text-ink2">Auto-play responses</span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={ui.ttsAutoPlay}
                    onClick={() => ui.setTtsAutoPlay(!ui.ttsAutoPlay)}
                    className={`relative h-4 w-7 rounded-full transition-colors ${ui.ttsAutoPlay ? "bg-primary" : "bg-surface3"}`}
                    aria-label="Toggle auto-play"
                  >
                    <span
                      className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform ${
                        ui.ttsAutoPlay ? "translate-x-3.5" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </label>
              </div>
              <p className="num mt-2 text-[10px] text-faint">
                Voice used when reading Coach messages aloud. Auto-play reads each new assistant response automatically.
              </p>
            </div>
          </div>
        </Card>

        {/* 3. Security & Sessions (half) */}
        <Card>
          <SectionHeader eyebrow={t("settings.security_title")} title={t("settings.security_title")} />
          <div className="space-y-3">
            <div className="rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3">
              <div className="eyebrow">{t("settings.session_current")}</div>
              <div className="num mt-1 text-[13px] font-semibold text-ink">
                {t("settings.signed_in_as", { email: me.email })}
              </div>
              <div className="num mt-0.5 text-[11px] text-muted">
                {t("settings.last_active")}
              </div>
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
        </Card>

        {/* 4. Devices & Integrations (full row) */}
        <Card pad={false} className="lg:col-span-2">
          <div className="p-4">
            <SectionHeader eyebrow={t("settings.devices_title")} title={t("settings.devices_title")} />
          </div>
          <Hairline />
          <div className="overflow-x-auto">
            <table className="num w-full min-w-[640px] text-left text-[12px]">
              <thead>
                <tr className="border-b border-hairline text-faint">
                  <th className="eyebrow px-4 py-2 font-semibold">{t("settings.provider")}</th>
                  <th className="eyebrow px-4 py-2 font-semibold">{t("settings.status")}</th>
                  <th className="eyebrow px-4 py-2 font-semibold">{t("settings.is_main")}</th>
                  <th className="eyebrow px-4 py-2 font-semibold">{t("settings.last_sync")}</th>
                  <th className="eyebrow px-4 py-2 font-semibold">{t("settings.connected_at")}</th>
                  <th className="eyebrow px-4 py-2 text-right font-semibold">{t("settings.actions")}</th>
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
                        <Badge tone="primary" dot>
                          {t("settings.main")}
                        </Badge>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {d.last_synced_at ? timeAgo(d.last_synced_at, ui.locale) : "—"}
                    </td>
                    <td className="px-4 py-3 text-muted">
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
        </Card>

        {/* 5. Owner Settings (half — owner-only) */}
        {me.role === "owner" && (
          <Card>
            <SectionHeader eyebrow={t("settings.owner_title")} title={t("settings.owner_title")} />
            <div className="space-y-4">
              <OwnerInvite />
              <div>
                <Eyebrow>{t("settings.ai_tier")}</Eyebrow>
                <div className="mt-1.5">
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
              <p className="num text-[11px] text-faint">
                {t("settings.invite_disclaimer")}
              </p>
            </div>
          </Card>
        )}

        {/* 6. About (half or full if not owner) */}
        <Card className={me.role === "owner" ? "" : "lg:col-span-2"}>
          <SectionHeader eyebrow={t("settings.about")} title={t("settings.about")} />
          <div className="space-y-2">
            <Row label={t("settings.version")} value={t("settings.version_value")} />
            <Row label={t("settings.build")} value={t("settings.build_value")} />
            <Row label={t("settings.stack")} value={t("settings.stack_value")} />
            <Row label={t("settings.repo")} value={t("settings.repo_value")} />
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ sub-components */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="block">
      <span className={labelCls}>{label}</span>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-hairline py-1.5 last:border-0">
      <span className="eyebrow shrink-0">{label}</span>
      <span className="num truncate text-[12px] font-medium text-ink2">{value}</span>
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
  if (status === "active") return <Badge tone="positive" dot>{t("settings.active")}</Badge>;
  if (status === "paused") return <Badge tone="warning" dot>{t("settings.paused")}</Badge>;
  return <Badge tone="alert" dot>{t("settings.error")}</Badge>;
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
    <form onSubmit={onInvite} className="space-y-1.5">
      <Eyebrow>{t("settings.invite_friend")}</Eyebrow>
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

/**
 * LocalePreview — shows how a date + time + number will format under the
 * selected locale, so users can preview the change before applying.
 */
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
    <div className="mt-2 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-2.5">
      <div className="num flex items-center justify-between gap-2 text-[11px]">
        <span className="text-muted">Preview ({localeTag})</span>
        <span className="text-faint">{locale === "it" ? "Italiano" : "English"}</span>
      </div>
      <div className="num mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px] text-ink2">
        <span className="font-semibold text-ink">{dateStr}</span>
        <span className="text-faint" aria-hidden>·</span>
        <span className="tabular-nums">{timeStr}</span>
        <span className="text-faint" aria-hidden>·</span>
        <span className="tabular-nums">{numStr}</span>
      </div>
    </div>
  );
}
