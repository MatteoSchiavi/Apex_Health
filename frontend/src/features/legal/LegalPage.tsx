import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Logo } from "../../components/layout/AppShell";

type LegalConfig = {
  controller_name: string;
  controller_address: string;
  contact_email: string;
  hosting_region: string;
  effective_date: string;
  account_basis: string;
  health_basis: string;
  ai_processor: string;
  backup_location: string;
  transfer_details: string;
  details_complete: boolean;
};

const pages = ["privacy", "terms", "cookies"] as const;
type Page = (typeof pages)[number];

function Section({ name, children }: { name: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <section className="border-t border-hairline py-7">
      <h2 className="text-xl font-medium tracking-tight">{t(`legal.${name}.title`)}</h2>
      <div className="mt-3 space-y-3 text-sm leading-7 text-muted">{children}</div>
    </section>
  );
}

function Value({ value }: { value?: string }) {
  const { t } = useTranslation();
  return value ? <span className="text-ink">{value}</span> : <span className="text-amber-700">{t("legal.not_configured")}</span>;
}

function Privacy({ config }: { config?: LegalConfig }) {
  const { t } = useTranslation();
  return (
    <>
      <Section name="controller">
        <p>{t("legal.controller.body")}</p>
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[10rem_1fr]">
          <dt>{t("legal.controller.name")}</dt><dd><Value value={config?.controller_name} /></dd>
          <dt>{t("legal.controller.address")}</dt><dd><Value value={config?.controller_address} /></dd>
          <dt>{t("legal.controller.contact")}</dt><dd><Value value={config?.contact_email} /></dd>
          <dt>{t("legal.controller.effective")}</dt><dd><Value value={config?.effective_date} /></dd>
        </dl>
      </Section>
      <Section name="data"><p>{t("legal.data.body")}</p></Section>
      <Section name="purposes">
        <p>{t("legal.purposes.body")}</p>
        <p>{t("legal.purposes.account_basis")} <Value value={config?.account_basis} /></p>
        <p>{t("legal.purposes.health_basis")} <Value value={config?.health_basis} /></p>
      </Section>
      <Section name="recipients">
        <p>{t("legal.recipients.body")}</p>
        <p>{t("legal.recipients.telegram")}</p>
        <p>{t("legal.recipients.ai")} <Value value={config?.ai_processor} /></p>
        <p>{t("legal.recipients.hosting")} <Value value={config?.hosting_region} /></p>
        <p>{t("legal.recipients.backup")} <Value value={config?.backup_location} /></p>
        <p>{t("legal.recipients.transfers")} <Value value={config?.transfer_details} /></p>
      </Section>
      <Section name="retention">
        <p>{t("legal.retention.body")}</p>
        <p>{t("legal.retention.preferences")}</p>
        <p>{t("legal.retention.backups")}</p>
      </Section>
      <Section name="rights">
        <p>{t("legal.rights.body")}</p>
        <p>{t("legal.rights.controls")} <Link className="text-link text-ink" to="/app/settings?tab=data-health">{t("legal.rights.data_health")}</Link>.</p>
        <p>{t("legal.rights.authority")}</p>
      </Section>
      <Section name="automated"><p>{t("legal.automated.body")}</p></Section>
    </>
  );
}

function Terms() {
  const { t } = useTranslation();
  return <>
    <Section name="service"><p>{t("legal.service.body")}</p></Section>
    <Section name="access"><p>{t("legal.access.body")}</p></Section>
    <Section name="health"><p>{t("legal.health.body")}</p></Section>
    <Section name="providers"><p>{t("legal.providers.body")}</p></Section>
    <Section name="responsibilities"><p>{t("legal.responsibilities.body")}</p></Section>
    <Section name="changes"><p>{t("legal.changes.body")}</p></Section>
  </>;
}

function Cookies() {
  const { t } = useTranslation();
  return <>
    <Section name="cookies_used"><p>{t("legal.cookies_used.body")}</p></Section>
    <Section name="local_storage"><p>{t("legal.local_storage.body")}</p></Section>
    <Section name="cookies_choices"><p>{t("legal.cookies_choices.body")}</p></Section>
  </>;
}

export default function LegalPage() {
  const { t, i18n } = useTranslation();
  const { pathname } = useLocation();
  const page = (pages.find((item) => pathname.endsWith(`/${item}`)) ?? "privacy") as Page;
  const { data, isError } = useQuery({
    queryKey: ["legal-config"],
    queryFn: () => api.get<LegalConfig>("/legal/config"),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const isItalian = i18n.resolvedLanguage === "it";

  function switchLanguage() {
    const next = isItalian ? "en" : "it";
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
  }

  return (
    <main className="min-h-dvh bg-canvas px-5 py-5 text-ink sm:px-8 sm:py-8">
      <div className="mx-auto max-w-4xl border border-hairline bg-bg">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline px-5 py-4 sm:px-8">
          <Link to="/" aria-label={t("legal.home")}><Logo /></Link>
          <div className="flex items-center gap-5 text-sm">
            <button type="button" onClick={switchLanguage} className="text-link" aria-label={t("landing.language")}>{isItalian ? "EN" : "IT"}</button>
            <Link to="/login" className="text-link">{t("landing.sign_in")}</Link>
          </div>
        </header>
        <div className="px-5 py-8 sm:px-8 sm:py-12">
          <p className="eyebrow text-primaryText">{t("legal.eyebrow")}</p>
          <h1 className="mt-3 text-4xl font-medium tracking-tight">{t(`legal.${page}`)}</h1>
          <nav aria-label={t("legal.nav_label")} className="mt-7 flex flex-wrap gap-x-5 gap-y-2 border-b border-hairline pb-5 text-sm">
            {pages.map((item) => <Link key={item} to={`/legal/${item}`} aria-current={page === item ? "page" : undefined} className={page === item ? "font-semibold text-ink" : "text-link text-muted"}>{t(`legal.${item}`)}</Link>)}
          </nav>
          {(isError || (data && !data.details_complete)) && <p role="status" className="mt-6 border-l-2 border-amber-500 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("legal.incomplete")}</p>}
          <div className="mt-3">
            {page === "privacy" ? <Privacy config={data} /> : page === "terms" ? <Terms /> : <Cookies />}
          </div>
          <p className="mt-4 text-xs leading-5 text-muted">{t("legal.revision_note")}</p>
        </div>
      </div>
    </main>
  );
}
