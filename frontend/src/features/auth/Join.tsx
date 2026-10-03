import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { useUi, type Locale, type Theme } from "../../app/stores/ui";
import { Button, ErrorNote, Input, Segmented } from "../../components/kit";
import { AuthLayout } from "./AuthLayout";
export default function Join() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [locale, setLocale] = useState<Locale>(useUi.getState().locale);
  const [theme, setTheme] = useState<Theme>(useUi.getState().theme);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/invite/redeem", {
        code: code.trim(),
        name,
        email,
        password,
        locale,
        theme,
      });
      qc.clear();
      useUi.getState().setMe(null);
      useUi.getState().setLocale(locale, false);
      useUi.getState().setTheme(theme, false);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? t("auth.invite_error")
          : err instanceof ApiError && err.status === 422
            ? t("design.join_validation")
            : t("design.login_unavailable"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthLayout>
      <h2 className="page-title">{t("auth.welcome")}</h2>
      <p className="mb-8 mt-3 text-[14px] text-muted">{t("design.join_sub")}</p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Input
          label={t("auth.invite_code")}
          value={code}
          onChange={setCode}
          required
        />
        <Input
          label={t("auth.your_name")}
          value={name}
          onChange={setName}
          autoComplete="name"
          required
        />
        <Input
          label={t("auth.email")}
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="username"
          required
        />
        <Input
          label={t("auth.password")}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          minLength={8}
          required
        />
        <p className="text-[12px] text-muted">{t("settings.new_password")}</p>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <span className="text-[13px] text-muted">
            {t("auth.choose_language")}
          </span>
          <Segmented
            value={locale}
            onChange={(v) => {
              setLocale(v);
              useUi.getState().setLocale(v, false);
            }}
            options={[
              { value: "en", label: "English" },
              { value: "it", label: "Italiano" },
            ]}
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <span className="text-[13px] text-muted">
            {t("auth.choose_theme")}
          </span>
          <Segmented
            value={theme}
            onChange={(v) => {
              setTheme(v);
              useUi.getState().setTheme(v, false);
            }}
            options={[
              { value: "light", label: t("theme.light") },
              { value: "dark", label: t("theme.dark") },
            ]}
          />
        </div>
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={busy} className="mt-3 !h-12">
          {t(busy ? "common.loading" : "auth.redeem")}
        </Button>
      </form>
      <Link
        to="/login"
        className="mt-6 block text-[13px] text-muted underline underline-offset-4"
      >
        {t("auth.login")}
      </Link>
    </AuthLayout>
  );
}
