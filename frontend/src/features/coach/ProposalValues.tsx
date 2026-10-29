import { useTranslation } from "react-i18next";

// Only known bookkeeping fields move into details. Unknown fields, including
// underscored ones, stay visible so a future payload cannot hide a change.
const technicalFields = new Set(["id", "target_id", "plan_id", "training_plan_id", "revision", "snapshot_revision", "payload_hash"]);
const fieldNames = new Set([
  "date", "target_duration_min", "duration_min", "target_distance_m", "distance_m",
  "description", "session_type", "discipline", "content", "doc_kind", "exists",
  "notes", "tags", "week_start", "sessions", "start_time", "protected", "title",
]);
const units: Record<string, string> = { target_duration_min: "min", duration_min: "min", target_distance_m: "m", distance_m: "m" };
export function proposalFields(value: Record<string, unknown>, technical = false) {
  return Object.fromEntries(Object.entries(value).filter(([key]) => technicalFields.has(key) === technical));
}

/** Preserve strings, precision, null, booleans and every unknown payload field. */
export function ProposalValues({ value, field }: { value: unknown; field?: string }) {
  const { t } = useTranslation();
  if (value === undefined) return <span className="text-muted">{t("redesign.proposals.not_provided")}</span>;
  if (value === null) return <span className="text-muted">{t("redesign.proposals.not_set")}</span>;
  if (value === "") return <span className="text-muted">{t("redesign.proposals.empty_text")}</span>;
  if (typeof value === "boolean") return <span>{t(value ? "redesign.proposals.yes" : "redesign.proposals.no")}</span>;
  if (Array.isArray(value)) return value.length ? <ol className="space-y-3">{value.map((item, index) => <li key={index} className="rounded-control border border-hairline p-3"><ProposalValues value={item} /></li>)}</ol> : <span className="text-muted">{t("redesign.proposals.empty_list")}</span>;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length ? <dl className="space-y-3">{entries.map(([key, item]) => <div key={key} className="min-w-0">
      <dt className="mb-1 break-words text-[12px] text-muted">{fieldNames.has(key) ? t("redesign.proposals.fields." + key) : key}</dt>
      <dd className="min-w-0 whitespace-pre-wrap break-words"><ProposalValues value={item} field={key} /></dd>
    </div>)}</dl> : <span className="text-muted">{t("redesign.proposals.no_fields")}</span>;
  }
  return <span className="whitespace-pre-wrap break-words">{String(value)}{typeof value === "number" && field && units[field] ? ` ${units[field]}` : ""}</span>;
}
