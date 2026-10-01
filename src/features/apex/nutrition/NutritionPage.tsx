"use client";

import { PageHeader } from "@/components/apex/kit";
import { useT } from "@/lib/apex/i18nContext";

/**
 * Nutrition page placeholder (plan §12, phase 2). Backend read routes do not
 * exist yet; this page is a stub so the nav is wired for the future.
 */
export function NutritionPage() {
  const t = useT();
  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.nutrition")} subtitle={t("nutrition.subtitle")} />
      <div className="rounded-[var(--radius-card)] border border-dashed border-hairline2 px-6 py-16 text-center">
        <div className="text-[14px] font-semibold text-ink2">{t("nutrition.coming_soon")}</div>
        <div className="mt-1 text-[12px] text-muted">{t("nutrition.coming_soon_body")}</div>
      </div>
    </div>
  );
}
