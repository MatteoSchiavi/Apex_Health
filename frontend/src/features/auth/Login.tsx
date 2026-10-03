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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/auth/login", { email, password });
      qc.clear();
      useUi.getState().setMe(null);
      const from = location.state?.from;
      navigate(
        typeof from === "string" &&
          (from === "/app" || from.startsWith("/app/"))
          ? from
          : "/app",
        { replace: true },
      );
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
