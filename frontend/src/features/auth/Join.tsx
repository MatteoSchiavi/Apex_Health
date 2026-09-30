import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Button, Input } from "../../components/kit";
import { useUi, type Locale, type Theme } from "../../app/stores/ui";

/** Onboarding: invite redeem + the two choices that live on the account —
 * language and theme (owner spec: set at account creation or in settings). */
export default function Join() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const setLocaleStore = useUi((s) => s.setLocale);
  const setThemeStore = useUi((s) => s.setTheme);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [locale, setLocale] = useState<Locale>(
    (i18n.language === "it" ? "it" : "en") as Locale,
  );
  const [theme, setTheme] = useState<Theme>(
    document.documentElement.classList.contains("light") ? "light" : "dark",
  );
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(false);
    try {
      await api.post("/auth/invite/redeem", {
        code: code.trim(),
        name,
        email,
        password,
        locale,
        theme,
      });
      setLocaleStore(locale, false);
      setThemeStore(theme, false);
      navigate("/app", { replace: true });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  const themeOptions: { value: Theme; label: string }[] = [
    { value: "dark", label: t("theme.dark") },
    { value: "light", label: t("theme.light") },
  ];
  const localeOptions: { value: Locale; label: string }[] = [
    { value: "en", label: "English" },
    { value: "it", label: "Italiano" },
  ];

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <svg width="44" height="44" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="8" className="fill-surface" />
            <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
          </svg>
          <div className="text-[20px] font-semibold tracking-tight text-ink">
            {t("auth.welcome")}
          </div>
        </div>

        <form
          onSubmit={submit}
          className="flex flex-col gap-3 rounded-card border border-hairline bg-surface p-5"
        >
          <Input label={t("auth.invite_code")} value={code} onChange={setCode} required />
          <Input label={t("auth.your_name")} value={name} onChange={setName} required />
          <Input
            label={t("auth.email")}
            type="email"
            value={email}
            onChange={setEmail}
            required
          />
          <Input
            label={t("auth.password")}
            type="password"
            value={password}
            onChange={setPassword}
            required
          />

          <div>
            <div className="eyebrow mb-1">{t("auth.choose_language")}</div>
            <div className="grid grid-cols-2 gap-2">
              {localeOptions.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => {
                    setLocale(o.value);
                    void i18n.changeLanguage(o.value);
                  }}
                  className={`rounded-control border px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    locale === o.value
                      ? "border-primary bg-primarySoft text-primaryText"
                      : "border-hairline text-ink2 hover:bg-surface3"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="eyebrow mb-1">{t("auth.choose_theme")}</div>
            <div className="grid grid-cols-2 gap-2">
              {themeOptions.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setTheme(o.value)}
                  className={`rounded-control border px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    theme === o.value
                      ? "border-primary bg-primarySoft text-primaryText"
                      : "border-hairline text-ink2 hover:bg-surface3"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="rounded-sm bg-alertSoft px-2.5 py-1.5 text-[12px] text-alertText">
              {t("auth.invite_error")}
            </div>
          )}
          <Button type="submit" disabled={busy} className="mt-1 w-full">
            {t("auth.redeem")}
          </Button>
        </form>
      </div>
    </div>
  );
}
