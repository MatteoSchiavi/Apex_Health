import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Button, Input } from "../../components/kit";

/** Login screen — bootstrap surface, locale falls back to the browser hint
 * (the account's locale takes over right after the session exists). */
export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(false);
    try {
      await api.post("/auth/login", { email, password });
      navigate("/app", { replace: true });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <svg width="44" height="44" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="8" className="fill-surface" />
            <path d="M16 6 L26 26 L21 26 L16 15 L11 26 L6 26 Z" className="fill-primary" />
          </svg>
          <div>
            <div className="text-[20px] font-semibold tracking-tight text-ink">
              {t("auth.login_title")}
            </div>
            <div className="eyebrow mt-1">{t("auth.login_sub")}</div>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="flex flex-col gap-3 rounded-card border border-hairline bg-surface p-5"
        >
          <Input
            label={t("auth.email")}
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            required
          />
          <Input
            label={t("auth.password")}
            type="password"
            value={password}
            onChange={setPassword}
            required
          />
          {error && (
            <div className="rounded-sm bg-alertSoft px-2.5 py-1.5 text-[12px] text-alertText">
              {t("auth.error")}
            </div>
          )}
          <Button type="submit" disabled={busy} className="mt-1 w-full">
            {t("auth.login")}
          </Button>
          <button
            type="button"
            onClick={() => navigate("/join")}
            className="mt-1 text-center text-[12px] text-muted hover:text-ink2"
          >
            {t("auth.have_invite")} {t("auth.redeem")}
          </button>
        </form>
      </div>
    </div>
  );
}
