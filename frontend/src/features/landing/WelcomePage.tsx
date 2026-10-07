import { ArrowRight, Database, FlaskConical, ShieldCheck, Moon, Activity, HeartPulse } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Logo } from "../../components/layout/AppShell";

const principles = [
  { icon: Database, key: "data" },
  { icon: FlaskConical, key: "evidence" },
  { icon: ShieldCheck, key: "control" },
] as const;

export default function WelcomePage() {
  const { t, i18n } = useTranslation();
  const isItalian = i18n.resolvedLanguage === "it";

  function switchLanguage() {
    const next = isItalian ? "en" : "it";
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
  }

  return (
    <main className="min-h-dvh bg-canvas px-5 py-5 text-ink sm:px-8 sm:py-8">
      <div className="mx-auto flex min-h-[calc(100dvh-2.5rem)] max-w-6xl flex-col border border-hairline bg-bg sm:min-h-[calc(100dvh-4rem)]">
        <header className="flex items-center justify-between border-b border-hairline px-5 py-4 sm:px-8">
          <Logo />
          <div className="flex items-center gap-4 text-[13px] font-medium">
            <button
              type="button"
              onClick={switchLanguage}
              className="text-muted transition-colors hover:text-ink"
              aria-label={t("landing.language")}
            >
              {isItalian ? "EN" : "IT"}
            </button>
            <Link to="/login" className="text-link text-ink">
              {t("landing.sign_in")}
            </Link>
          </div>
        </header>

        <section className="grid flex-1 lg:grid-cols-[1.15fr_.85fr]">
          <div className="flex flex-col justify-between px-5 py-12 sm:px-8 sm:py-16 lg:px-12 lg:py-20">
            <div>
              <p className="eyebrow text-primaryText">{t("landing.eyebrow")}</p>
              <h1 className="mt-5 max-w-3xl text-[clamp(42px,6.4vw,88px)] font-medium leading-[.94] tracking-[-.075em]">
                {t("landing.title")}
              </h1>
              <p className="mt-8 max-w-xl text-[16px] leading-7 text-muted sm:text-[17px]">
                {t("landing.body")}
              </p>
              <div className="mt-10 flex flex-wrap items-center gap-3">
                <Link
                  to="/login"
                  className="inline-flex h-11 items-center gap-2 bg-primary px-4 text-[13px] font-semibold text-white transition-opacity hover:opacity-90"
                >
                  {t("landing.open")}
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
                <Link to="/join" className="text-link px-2 text-muted hover:text-ink">
                  {t("landing.invite")}
                </Link>
              </div>
            </div>
            <div className="mt-16 max-w-lg border-t border-hairline pt-4 text-[12px] leading-5 text-faint">
              <p>{t("landing.note")}</p>
              <nav aria-label={t("legal.nav_label")} className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                <Link to="/legal/privacy" className="text-link">{t("legal.privacy")}</Link>
                <Link to="/legal/terms" className="text-link">{t("legal.terms")}</Link>
                <Link to="/legal/cookies" className="text-link">{t("legal.cookies")}</Link>
              </nav>
            </div>
          </div>

          <aside className="border-t border-hairline bg-surface lg:border-l lg:border-t-0">
            <div className="grid h-full content-center px-5 py-10 sm:px-8 lg:px-10">
              <section className="mb-8 border border-hairline bg-bg p-4 sm:p-5" aria-label={t("landing.preview_label")}>
                <div className="flex items-center justify-between border-b border-hairline pb-3"><span className="eyebrow">{t("landing.preview_title")}</span><span className="text-[11px] text-faint">{t("landing.preview_example")}</span></div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {[{ icon: HeartPulse, label: t("landing.preview_recovery"), value: "—" }, { icon: Moon, label: t("landing.preview_sleep"), value: "—" }, { icon: Activity, label: t("landing.preview_load"), value: "—" }].map(({ icon: Icon, label, value }) => <div key={label} className="min-w-0 border border-hairline p-2"><div className="flex items-center gap-1.5 text-faint"><Icon size={13} aria-hidden="true"/><span className="truncate text-[11px]">{label}</span></div><div className="num mt-3 text-[20px]">{value}</div></div>)}
                </div>
                <div className="mt-3 flex items-center gap-3 border-t border-hairline pt-3"><span className="h-2 w-2 rounded-full bg-warningText"/><span className="text-[12px] text-muted">{t("landing.preview_empty")}</span></div>
              </section>
              <div className="divide-y divide-hairline">
              {principles.map(({ icon: Icon, key }, index) => (
                <article key={key} className="py-7 first:pt-0 last:pb-0">
                  <div className="mb-4 flex items-center justify-between">
                    <Icon size={18} className="text-primaryText" aria-hidden="true" />
                    <span className="mono text-[11px] text-faint">
                      0{index + 1}
                    </span>
                  </div>
                  <h2 className="text-[20px] font-medium tracking-[-.035em]">
                    {t(`landing.${key}.title`)}
                  </h2>
                  <p className="mt-2 max-w-sm text-[14px] leading-6 text-muted">
                    {t(`landing.${key}.body`)}
                  </p>
                </article>
              ))}
              </div>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
