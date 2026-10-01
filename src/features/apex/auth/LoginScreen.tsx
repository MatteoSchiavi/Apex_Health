"use client";

/**
 * Apex Health — Login screen.
 *
 * Plan §10 fixes applied:
 *  - Three distinct error states instead of one generic "invalid credentials":
 *      401 → "Invalid email or password"   (t("auth.error"))
 *      429 → "Too many attempts. Try again later."  (t("auth_locked"))
 *      500 / network → "Something went wrong. Please try again."  (t("auth_server_error"))
 *    The backend (POST /auth/login) distinguishes these; the web UI no longer
 *    collapses them into one message so a locked-out user stops retrying.
 *  - Show / hide password toggle (t("auth_show_password")).
 *  - Deep link honoured: a `?from=<view>` query param (set by a redirect from
 *    a protected page) sends the user back to that view after a successful
 *    login instead of always landing on overview. The app is a state-based
 *    SPA, so "redirect" = `ui.setView(from)` for a valid ViewKey.
 *  - A small "← Apex Health" link (t("auth_back")) returns to the welcome view.
 *
 * Mock auth: the Zustand store's `signIn()` just flips `authed`. To make the
 * three error states demonstrable on the mock, `mockLogin` is deterministic:
 *    email contains "locked"        → 429 (lockout)
 *    email contains "error"/"server"→ 500 (network/server)
 *    empty password                 → 401 (wrong credentials)
 *    otherwise                      → success
 * Real auth will replace this once /auth/login is wired in.
 */

import { useState, type FormEvent } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { ApexButton, Eyebrow, Card } from "@/components/apex/kit";
import type { ViewKey } from "@/lib/apex/types";

/** All app views a deep link may legitimately target after login. */
const VALID_TARGET_VIEWS: ViewKey[] = [
  "overview",
  "activities",
  "activity-detail",
  "sleep",
  "sleep-night",
  "biometrics",
  "metric",
  "training",
  "coach",
  "social",
  "settings",
  "gear",
  "labs",
  "nutrition",
];

/** Deterministic mock of POST /auth/login — see header for the rules. */
async function mockLogin(
  email: string,
  password: string,
): Promise<{ ok: true } | { ok: false; status: 401 | 429 | 500 }> {
  // Simulate a network round-trip so the loading state is visible.
  await new Promise((r) => setTimeout(r, 450));
  const e = email.trim().toLowerCase();
  if (e.includes("locked")) return { ok: false, status: 429 };
  if (e.includes("error") || e.includes("server")) return { ok: false, status: 500 };
  if (!password) return { ok: false, status: 401 };
  return { ok: true };
}

export function LoginScreen() {
  const t = useT();
  const ui = useApexUi();

  const [email, setEmail] = useState("matteo.schiavi@apexhealth.app");
  const [password, setPassword] = useState("demo");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    const res = await mockLogin(email, password);
    setLoading(false);

    if (res.ok) {
      // Honour the deep link: a `?from=<view>` param (set by a redirect from a
      // protected page) returns the user to that view after login. The app is
      // a state-based SPA, so "redirect" = `ui.setView(from)`.
      let target: ViewKey | null = null;
      if (typeof window !== "undefined") {
        const from = new URLSearchParams(window.location.search).get("from");
        if (from && (VALID_TARGET_VIEWS as string[]).includes(from)) {
          target = from as ViewKey;
        }
      }
      ui.signIn(); // sets authed + view: "overview"
      if (target) ui.setView(target);
      return;
    }

    if (res.status === 401) setError(t("auth.error"));
    else if (res.status === 429) setError(t("auth_locked"));
    else setError(t("auth_server_error"));
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-5">
      <div className="w-full max-w-md">
        {/* "← Apex Health" — back to the welcome / landing view (plan §10). */}
        <button
          type="button"
          onClick={() => ui.setView("welcome")}
          className="num mb-3 text-[12px] font-medium text-muted transition-colors hover:text-ink"
        >
          {t("auth_back")}
        </button>

        <Eyebrow>{t("auth.login_title")}</Eyebrow>
        <h1 className="page-title mt-2">{t("auth.login_sub")}</h1>

        <Card className="mt-6">
          <form onSubmit={handleSubmit} className="space-y-3" noValidate>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("auth.email")}
              autoComplete="email"
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("auth.password")}
                autoComplete="current-password"
                className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 pr-10 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface2 hover:text-ink"
                aria-label={t("auth_show_password")}
                aria-pressed={showPassword}
                title={t("auth_show_password")}
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>

            {/* Three distinct error messages (plan §10). */ }
            {error && (
              <div
                role="alert"
                className="num rounded-[var(--radius-control)] border border-alert/40 bg-alertSoft px-3 py-2 text-[12px] font-medium text-alertText"
              >
                {error}
              </div>
            )}

            <ApexButton type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>{t("auth.login")}</span>
                </>
              ) : (
                t("auth.login")
              )}
            </ApexButton>
          </form>

          {/* Demo hint — how to trigger each of the three error states. */ }
          <p className="num mt-3 text-[10px] leading-[14px] text-faint">
            {/* TODO i18n — main agent will add an auth.demo_hint key */}
            {"Demo: leave password empty → wrong credentials · email contains \"locked\" → locked · email contains \"error\" → server error."}
          </p>
        </Card>

        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={() => ui.setView("welcome")}
            className="text-[12px] font-medium text-muted hover:text-ink"
          >
            {t("auth.back_to_welcome")}
          </button>
          <button
            type="button"
            onClick={() => ui.setView("join")}
            className="text-[12px] font-medium text-muted hover:text-ink"
          >
            {t("auth.have_invite")}
          </button>
        </div>
      </div>
    </div>
  );
}
