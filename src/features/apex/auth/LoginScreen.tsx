"use client";

import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { ApexButton, Eyebrow, PageHeader, Card } from "@/components/apex/kit";
import { BackLink } from "@/components/apex/kit";

export function LoginScreen() {
  const t = useT();
  const ui = useApexUi();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-5">
      <div className="w-full max-w-md">
        <Eyebrow>{t("auth.login_title")}</Eyebrow>
        <h1 className="page-title mt-2">{t("auth.login_sub")}</h1>
        <Card className="mt-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ui.signIn();
            }}
            className="space-y-3"
          >
            <input
              type="email"
              required
              defaultValue="matteo.schiavi@apexhealth.app"
              placeholder={t("auth.email")}
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <input
              type="password"
              required
              defaultValue="demo"
              placeholder={t("auth.password")}
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <ApexButton type="submit" className="w-full">
              {t("auth.login")}
            </ApexButton>
          </form>
        </Card>
        <div className="mt-4 flex items-center justify-between">
          <BackLink onClick={() => ui.setView("welcome")}>{t("auth.back_to_welcome")}</BackLink>
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
