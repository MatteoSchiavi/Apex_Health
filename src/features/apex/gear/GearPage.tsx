"use client";

import { PageHeader } from "@/components/apex/kit";
import { useT } from "@/lib/apex/i18nContext";

/**
 * Gear page placeholder. Full implementation is delegated to the Gear subagent
 * (plan §6). This renders a clean empty state so the nav + router are wired.
 */
export function GearPage() {
  const t = useT();
  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.gear")} subtitle={t("gear.subtitle")} />
      <div className="rounded-[var(--radius-card)] border border-dashed border-hairline2 px-6 py-16 text-center">
        <div className="text-[14px] font-semibold text-ink2">{t("gear.empty_title")}</div>
        <div className="mt-1 text-[12px] text-muted">{t("gear.empty_body")}</div>
      </div>
    </div>
  );
}
