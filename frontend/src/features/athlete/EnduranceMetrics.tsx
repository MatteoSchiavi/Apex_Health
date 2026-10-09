import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Card, CardHeader, ErrorNote, Loading, fmtDuration, fmtNum } from "../../components/kit";
import { paceText } from "../activities/SportActivityView";

interface CalculatedMetric {
  key: string; value: number | { name: string; duration_s: number }[] | null; unit: string;
  kind: string; formula: string; formula_version: string; source_dependencies: string[];
  availability: string; unavailable_reason: string | null; limitations: string[]; prerequisites: string[];
}

export function EnduranceMetrics({ id }: { id: number }) {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const query = useQuery({ queryKey: ["endurance", uid, id], queryFn: () => api.get<{ sport: string; metrics: CalculatedMetric[] }>(`/activities/${id}/endurance`) });
  if (query.isLoading) return <Loading />;
  if (!query.data || query.isError) return <ErrorNote />;
  return <Card>
    <CardHeader title={t("athlete.metrics_"+query.data.sport)} />
    <p className="mb-5 text-[13px] text-muted">{t("athlete.metrics_limits")}</p>
    <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">{query.data.metrics.map(m => <section key={m.key} className="min-w-0 border-t border-hairline pt-4">
      <div className="flex items-center justify-between gap-2"><h3 className="text-[13px] font-medium">{t("athlete.metric_"+m.key)}</h3><Badge>{t("athlete."+m.kind)}</Badge></div>
      {Array.isArray(m.value) ? <ul className="mt-3 text-[13px]">{m.value.map((zone, i) => <li className="flex justify-between gap-3" key={i}><span>{zone.name}</span><span className="num">{fmtDuration(zone.duration_s)}</span></li>)}</ul> : <p className="num my-3 text-[24px]">{m.key.includes("pace") && typeof m.value === "number" ? paceText(m.value/60) : fmtNum(m.value as number | null, 2)} <span className="text-[12px] text-muted">{m.key.includes("pace") ? "min/km" : m.unit}</span></p>}
      {m.unavailable_reason && <p className="text-[12px] text-muted">{t("athlete.reason_"+m.unavailable_reason)}</p>}
      <details className="mt-3 text-[12px] text-muted"><summary className="cursor-pointer">{t("athlete.calculation_details")}</summary><p className="mt-3 break-words text-ink2">{t("athlete.formula_"+m.key)}</p><p className="mt-2 break-all">{m.formula_version}</p>
        {!!m.source_dependencies.length && <p className="mt-2 break-all">{t("athlete.source_dependencies")}: {m.source_dependencies.join(" · ")}</p>}
        <ul className="mt-2 space-y-1">{[...m.prerequisites, ...m.limitations].map((key, i) => <li key={i}>{t("athlete.limit_"+key)}</li>)}</ul>
      </details>
    </section>)}</div>
  </Card>;
}
