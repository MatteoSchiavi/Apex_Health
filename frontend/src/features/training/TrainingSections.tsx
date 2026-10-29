import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function TrainingSections() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  return <nav aria-label={t("betaNavigation.training_sections")} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
    {[["/app/training", "today"], ["/app/sports/running", "running"], ["/app/sports/cycling", "cycling"], ["/app/sports/strength", "strength"]].map(([to, label]) => {
      const selected = pathname === to;
      return <Link key={to} to={to} aria-current={selected ? "page" : undefined} className={`flex min-h-11 items-center justify-center rounded-control border px-3 py-2 text-center text-[13px] ${selected ? "border-ink bg-ink font-medium text-canvas" : "border-hairline text-muted hover:bg-surface2 hover:text-ink"}`}>{t("betaNavigation." + label)}</Link>;
    })}
  </nav>;
}
