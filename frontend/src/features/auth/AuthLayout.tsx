import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Logo } from "../../components/layout/AppShell";
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
      </aside>
      <div className="auth-form">
        <div className="auth-form-inner">{children}</div>
      </div>
    </div>
  );
}
