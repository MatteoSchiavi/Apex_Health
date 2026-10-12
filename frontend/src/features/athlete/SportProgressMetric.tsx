import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Badge, fmtDuration, fmtNum } from "../../components/kit";
import { paceText } from "../activities/SportActivityView";
export interface SportProgressMetric { key: string; value: unknown; unit: string; kind: string; availability: string; unavailable_reason: string | null; formula: string; formula_version: string; source_dependencies: string[]; prerequisites: string[]; limitations: string[]; quality?: Record<string, unknown> }
const humanize = (key: string) => key.replaceAll("_", " ");

function MetricValue({ value, field = "", unit = "" }: { value: unknown; field?: string; unit?: string }) {
  const { t } = useTranslation();
  if (value == null) return <span>—</span>;
  if (typeof value === "number") return <span className="num">{field.endsWith("duration_s") || field === "valid_seconds" ? fmtDuration(value) : field.endsWith("pace_s_km") ? `${paceText(value / 60)} min/km` : field.endsWith("distance_m") ? `${fmtNum(value / 1000, 2)} km` : fmtNum(value, 2)} {unit}</span>;
  if (typeof value === "boolean") return <span>{t(value ? "athlete.yes" : "athlete.no")}</span>;
  if (typeof value === "string") return <span className="break-words">{t("sportProgress.values." + value, { defaultValue: value })}</span>;
  if (Array.isArray(value)) return <ul className="space-y-2">{value.map((item, index) => <li key={index}><MetricValue value={item} /></li>)}</ul>;
  if (typeof value === "object") return <dl className="space-y-2">{Object.entries(value).map(([key, entry]) => <div key={key} className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-1"><dt className="text-muted">{t("sportProgress.fields." + key, { defaultValue: humanize(key) })}</dt><dd className="min-w-0 max-w-full">{key.endsWith("activity_id") && typeof entry === "number" ? <Link className="text-link" to={`/app/activities/${entry}`}>{t("sportProgress.view_activity")}</Link> : <MetricValue value={entry} field={key} />}</dd></div>)}</dl>;
  return null;
}
export function MetricProvenance({ metric }: { metric: SportProgressMetric }) {
  const { t } = useTranslation();
  return <details className="mt-3 text-[12px] text-muted"><summary className="cursor-pointer">{t("sportProgress.method")}</summary><div className="mt-3 space-y-3">
    <p className="break-words">{metric.formula}</p><p>{metric.formula_version}</p>
    {metric.unavailable_reason && <p className="break-words">{t("sportProgress.availability_code")}: {metric.unavailable_reason}</p>}
    {!!metric.prerequisites.length && <div><h4 className="font-medium">{t("sportProgress.requirements")}</h4><ul className="mt-2 space-y-1">{metric.prerequisites.map(key => <li key={key}>{t("sportProgress.rules." + key, { defaultValue: t("athlete.limit_" + key, { defaultValue: humanize(key) }) })}</li>)}</ul></div>}
    {!!metric.limitations.length && <div><h4 className="font-medium">{t("sportProgress.limitations")}</h4><ul className="mt-2 space-y-1">{metric.limitations.map(key => <li key={key}>{t("sportProgress.rules." + key, { defaultValue: t("athlete.limit_" + key, { defaultValue: humanize(key) }) })}</li>)}</ul></div>}
    {metric.quality && <div><h4 className="mb-2 font-medium">{t("sportProgress.quality")}</h4><MetricValue value={metric.quality} /></div>}
    {!!metric.source_dependencies.length && <div><h4 className="font-medium">{t("athlete.source_dependencies")}</h4><ul className="mt-2 space-y-1">{metric.source_dependencies.map(source => <li key={source} className="break-all">{source}</li>)}</ul></div>}
  </div></details>;
}
export function ProgressMetric({ metric }: { metric: SportProgressMetric }) {
  const { t, i18n } = useTranslation();
  const bestPower = metric.key.match(/^best_power_(\d+)s$/);
  const title = bestPower ? t("sportProgress.best_power", { duration: fmtDuration(Number(bestPower[1])) }) : t("sportProgress.metrics." + metric.key, { defaultValue: t("athlete.metric_" + metric.key, { defaultValue: humanize(metric.key) }) });
  const reasonKey = "sportProgress.reasons." + metric.unavailable_reason;
  const reason = metric.unavailable_reason && i18n.exists(reasonKey) ? t(reasonKey) : metric.unavailable_reason ? t("sportProgress.unavailable") : null;
  return <section className="min-w-0 border-t border-hairline pt-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="text-[14px] font-medium">{title}</h3><Badge>{t(metric.value == null ? "sportProgress.not_available" : metric.kind === "recorded" ? "athlete.recorded" : "athlete.calculated")}</Badge></div>
    <div className={typeof metric.value === "number" ? "text-[22px]" : "text-[13px]"}><MetricValue value={metric.value} unit={typeof metric.value === "number" ? metric.unit : ""} /></div>
    {reason && <p className="mt-2 text-[13px] text-muted">{reason}</p>}
    <MetricProvenance metric={metric} />
  </section>;
}
