"use client";

import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { ApexButton, PageHeader, Card, BackLink } from "@/components/apex/kit";

export function JoinScreen() {
  const t = useT();
  const ui = useApexUi();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-5">
      <div className="w-full max-w-md">
        <div className="text-[14px] font-medium text-ink2">{t("auth.redeem")}</div>
        <h1 className="page-title mt-2">{t("auth.invite_code")}</h1>
        <Card className="mt-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ui.signIn();
            }}
            className="space-y-3"
          >
            <input
              required
              placeholder={t("auth.invite_code")}
              defaultValue="APEX-7K2M9"
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <input
              required
              placeholder={t("auth.your_name")}
              defaultValue="Apex Athlete"
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <input
              type="email"
              required
              placeholder={t("auth.email")}
              defaultValue="demo@apexhealth.app"
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <div className="grid grid-cols-2 gap-2">
              <select
                className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink"
                defaultValue="en"
              >
                <option value="en">{t("locale.en")}</option>
                <option value="it">{t("locale.it")}</option>
              </select>
              <select
                className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5 text-[13px] text-ink"
                defaultValue="dark"
              >
                <option value="dark">{t("theme.dark")}</option>
                <option value="light">{t("theme.light")}</option>
              </select>
            </div>
            <ApexButton type="submit" className="w-full">
              {t("auth.continue")}
            </ApexButton>
          </form>
        </Card>
        <div className="mt-4">
          <BackLink onClick={() => ui.setView("welcome")}>{t("auth.back_to_welcome")}</BackLink>
        </div>
      </div>
    </div>
  );
}
