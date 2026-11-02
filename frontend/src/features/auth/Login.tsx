import { useState, type FormEvent } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Button, ErrorNote, Input } from "../../components/kit";
import { AuthLayout } from "./AuthLayout";
export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/login", { email, password, remember_me: rememberMe });
      qc.clear();
      useUi.getState().setMe(null);
      const from = location.state?.from;
      let destination = "/app";
      if (typeof from === "string") {
        try {
          const target = new URL(from, window.location.origin);
          if (target.origin === window.location.origin && (target.pathname === "/app" || target.pathname.startsWith("/app/")))
            destination = target.pathname + target.search + target.hash;
        } catch { /* Fall back to Today for malformed return locations. */ }
      }
      navigate(destination, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? t("auth.error")
          : t("design.login_unavailable"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthLayout>
      <h2 className="page-title">{t("auth.login")}</h2>
      <p className="mb-8 mt-3 text-[14px] text-muted">
        {t("design.login_sub")}
      </p>
      <form onSubmit={submit} className="flex flex-col gap-5">
        <Input
          label={t("auth.email")}
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="username"
          required
        />
        <label className="flex items-center gap-3 text-[14px] text-muted">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(event) => setRememberMe(event.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          {t("auth.remember_me")}
        </label>
        <Input
          label={t("auth.password")}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          required
        />
        {error && <ErrorNote message={error} />}
        <Button type="submit" disabled={busy} className="mt-3 !h-12">
          {t(busy ? "common.loading" : "auth.login")}
        </Button>
      </form>
      <p className="mt-8 border-t border-hairline pt-6 text-[13px] text-muted">
        {t("auth.have_invite")}{" "}
        <Link
          to="/join"
          className="ml-1 font-medium text-ink underline underline-offset-4"
        >
          {t("auth.redeem")}
        </Link>
      </p>
    </AuthLayout>
  );
}
