"use client";

import { PageHeader } from "@/components/apex/kit";
import { useT } from "@/lib/apex/i18nContext";

/**
 * Labs page placeholder. Full implementation is delegated to the Labs subagent
 * (plan §7). This renders a clean empty state so the nav + router are wired.
 */
export function LabsPage() {
  const t = useT();
  return (
    <div className="space-y-4">
      <PageHeader title={t("nav.labs")} subtitle={t("labs.subtitle")} />
      <div className="rounded-[var(--radius-card)] border border-dashed border-hairline2 px-6 py-16 text-center">
        <div className="text-[14px] font-semibold text-ink2">{t("labs.empty_title")}</div>
        <div className="mt-1 text-[12px] text-muted">{t("labs.empty_body")}</div>
      </div>
    </div>
  );
}
