import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Logo } from "../../components/layout/AppShell";
import { Link } from "react-router-dom";
export function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="auth-layout">
      <aside className="auth-brand">
        <Logo />
        <div className="my-12 max-w-lg">
          <p className="mb-5 text-[13px] opacity-65">
            {t("design.auth_eyebrow")}
          </p>
          <h1 className="whitespace-pre-line text-[clamp(44px,5vw,76px)] font-medium leading-[1.02] tracking-[-.07em]">
            {t("design.auth_headline")}
          </h1>
          <p className="mt-6 max-w-sm text-[15px] leading-7 opacity-70">
            {t("design.auth_body")}
          </p>
        </div>
        <div className="auth-foot flex items-center justify-between border-t border-current/20 pt-5 text-[12px] opacity-60">
          <span>Apex Health</span>
          <span>{t("design.footer")}</span>
        </div>
        <nav aria-label={t("legal.nav_label")} className="mt-3 flex flex-wrap gap-4 text-xs">
          <Link to="/legal/privacy" className="text-link">{t("legal.privacy")}</Link>
          <Link to="/legal/terms" className="text-link">{t("legal.terms")}</Link>
          <Link to="/legal/cookies" className="text-link">{t("legal.cookies")}</Link>
        </nav>
      </aside>
      <div className="auth-form">
        <div className="auth-form-inner">{children}</div>
      </div>
    </div>
  );
}
