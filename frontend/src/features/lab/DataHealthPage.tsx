import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
  fmtNum,
} from "../../components/kit";
import type { Coverage, Entry, Job, Observation } from "./types";
import { coreMetrics } from "./types";
import {
  Field,
  Form,
  human,
  inputClass,
  num,
  QueryState,
  str,
  useAction,
  useLab,
  useToday,
  Value,
} from "./shared";
export default function DataHealthPage({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation();
  const today = useToday();
  const q = useLab<Coverage>("/lab/coverage");
  const jobs = useLab<Job[]>("/lab/jobs");
  const privacy = useLab<Entry[]>("/lab/entries?kind=privacy_preferences");
  const privacyEntry = privacy.data?.[0];
  const action = useAction();
  const [all, setAll] = useState(false);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(
    null,
  );
  const [source, setSource] = useState("garmin");
  const [deletion, setDeletion] = useState<{
    payload_hash: string;
    counts: Record<string, number>;
    scope: string;
  } | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importFormat, setImportFormat] = useState("csv");
  const [importName, setImportName] = useState("");
  const importInput = useRef<HTMLInputElement>(null);
  const importLimit = importFormat === "apple-health" ? 100 : 20;
  const importAccept = importFormat === "fit" ? ".fit" : importFormat === "csv" ? ".csv,text/csv" : ".zip,application/zip";
  async function inspect(obs: Observation) {
    try {
      setLookupError(null);
      const { api } = await import("../../app/api");
      setEvidence(await api.get(`/lab/evidence/${obs.id.split(":")[1]}`));
    } catch (e) {
      setLookupError((e as Error).message);
    }
  }
  return (
    <div className="flex flex-col gap-6">
      {!embedded && <PageHeader
        title={t("lab.data_health")}
        subtitle={t("lab.data_health_sub")}
      />}
      <QueryState loading={q.isLoading} error={q.isError} />
      <Card>
        <CardHeader
          title={t("lab.coverage")}
          right={
            <Button variant="ghost" onClick={() => setAll((v) => !v)}>
              {t(all ? "lab.core_metrics" : "lab.all_metrics")}
            </Button>
          }
        />
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label={t("lab.coverage")}
        >
          <table className="w-full min-w-[660px] text-left text-[13px]">
            <thead className="text-[11px] text-muted">
              <tr>
                {[
                  "metric",
                  "state",
                  "coverage",
                  "measured",
                  "fetched",
                  "source",
                ].map((k) => (
                  <th key={k} className="pb-3 font-normal">
                    {t("lab." + k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.data?.metrics
                .filter((m) => all || coreMetrics.includes(m.metric))
                .map((m) => (
                  <tr key={m.metric} className="border-t border-hairline">
                    <th className="py-4 pr-5 font-medium">
                      {t("lab.metrics." + m.metric, {
                        defaultValue: human(m.metric),
                      })}
                      <span className="num ml-3 text-muted">
                        {fmtNum(m.latest?.value, 1)} {m.unit}
                      </span>
                    </th>
                    <td>
                      <Badge
                        tone={
                          m.availability === "available"
                            ? "positive"
                            : m.availability === "fetch_failed"
                              ? "alert"
                              : "warning"
                        }
                      >
                        {t("lab.states." + m.availability, {
                          defaultValue: human(m.availability),
                        })}
                      </Badge>
                    </td>
                    <td className="num">{m.sample_days_7d}/7</td>
                    <td>{m.latest ? m.latest.local_date : "—"}</td>
                    <td>
                      {m.latest
                        ? new Date(m.latest.fetched_at).toLocaleDateString()
                        : "—"}
                    </td>
                    <td>
                      {m.latest && (
                        <button
                          className="text-link"
                          onClick={() => inspect(m.latest!)}
                        >
                          {m.latest.origin} ↗
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[12px] text-muted">{t("lab.freshness_note")}</p>
        {evidence && (
          <details
            open
            className="mt-5 border-t border-hairline pt-4 text-[12px]"
          >
            <summary>{t("lab.provenance")}</summary>
            <div className="mt-4">
              <Value value={evidence} />
            </div>
            <Form
              pending={action.isPending}
              error={action.error}
              label={t("lab.annotate")}
              onSave={(f) =>
                action.mutate({
                  path: "/lab/entries",
                  body: {
                    entry: {
                      kind: "observation_annotation",
                      date: today,
                      observation_id: Number(String(evidence.id).split(":")[1]),
                      exclude_from_analysis: f.get("exclude") === "on",
                      notes: str(f, "reason"),
                    },
                  },
                })
              }
            >
              <label className="mt-4 flex gap-2">
                <input type="checkbox" name="exclude" defaultChecked />
                {t("lab.exclude_analysis")}
              </label>
              <Field name="reason" label={t("lab.reason")} required />
            </Form>
          </details>
        )}
        {lookupError && <ErrorNote message={lookupError} />}
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={t("lab.repair")} />
          <Form
            pending={action.isPending}
            error={action.error}
            label={t("lab.request_job")}
            onSave={(f) =>
              action.mutate({
                path: "/lab/jobs",
                body: {
                  kind: str(f, "kind"),
                  start_date: str(f, "start"),
                  end_date: str(f, "end"),
                },
              })
            }
          >
            <Field name="kind" label={t("lab.job_kind")} value="reindex">
              <option value="reindex">{t("lab.reindex")}</option>
              <option value="repair">{t("lab.repair_provider")}</option>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field
                name="start"
                type="date"
                value={today}
                label={t("lab.start")}
                required
              />
              <Field
                name="end"
                type="date"
                value={today}
                max={today}
                label={t("lab.end")}
                required
              />
            </div>
            <p className="text-[12px] text-muted">{t("lab.repair_note")}</p>
          </Form>
          <div className="mt-5 flex flex-col gap-4">
            {jobs.data?.map((j) => (
              <div
                key={j.id}
                className="border-t border-hairline pt-4 text-[13px]"
              >
                <div className="flex flex-wrap justify-between gap-3">
                  <span>
                    #{j.id} ·{" "}
                    {t("lab." + j.kind, { defaultValue: human(j.kind) })} ·{" "}
                    {t("lab.states." + j.state, {
                      defaultValue: human(j.state),
                    })}
                  </span>
                  {["queued", "running"].includes(j.state) ? (
                    <Button
                      variant="ghost"
                      disabled={action.isPending || j.cancel_requested}
                      onClick={() =>
                        action.mutate({ path: `/lab/jobs/${j.id}/cancel` })
                      }
                    >
                      {t("lab.cancel")}
                    </Button>
                  ) : (
                    ["failed", "auth_required", "cancelled"].includes(
                      j.state,
                    ) && (
                      <Button
                        variant="ghost"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({ path: `/lab/jobs/${j.id}/retry` })
                        }
                      >
                        {t("common.retry")}
                      </Button>
                    )
                  )}
                </div>
                <p className="mt-2 text-muted">
                  {j.parameters.start} → {j.parameters.end}
                </p>
                <p className="num text-muted">
                  {String(j.progress.completed ?? 0)} /{" "}
                  {String(j.progress.total ?? "—")}
                </p>
                {!!j.progress.error && <p>{String(j.progress.error)}</p>}
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title={t("lab.manual_measurement")} />
          <Form
            pending={action.isPending}
            error={action.error}
            onSave={(f) =>
              action.mutate({
                path: "/lab/observations",
                body: {
                  metric: str(f, "metric"),
                  value: num(f, "value"),
                  measured_at: new Date(str(f, "measured_at")).toISOString(),
                  notes: str(f, "notes"),
                },
              })
            }
          >
            <Field name="metric" label={t("lab.metric")} value="resting_hr">
              {coreMetrics.map((k) => (
                <option key={k} value={k}>
                  {t("lab.metrics." + k)}
                </option>
              ))}
            </Field>
            <Field name="value" label={t("lab.value")} type="number" required />
            <Field
              name="measured_at"
              label={t("lab.measured")}
              type="datetime-local"
              required
            />
            <Field name="notes" type="textarea" label={t("lab.notes")} />
            <p className="text-[12px] text-muted">{t("lab.manual_note")}</p>
          </Form>
        </Card>
        <Card>
          <CardHeader title={t("lab.device_change")} />
          <Form
            pending={action.isPending}
            error={action.error}
            onSave={(f) =>
              action.mutate({
                path: "/lab/entries",
                body: {
                  entry: {
                    kind: "device_change",
                    date: str(f, "date"),
                    provider: str(f, "provider"),
                    device_id: str(f, "device"),
                    metrics: [str(f, "metric")],
                    notes: str(f, "notes"),
                  },
                },
              })
            }
          >
            <div className="grid grid-cols-2 gap-3">
              <Field
                name="date"
                type="date"
                label={t("lab.start")}
                value={today}
                required
              />
              <Field
                name="provider"
                label={t("lab.source")}
                value="garmin"
                required
              />
            </div>
            <Field name="device" label={t("lab.device_id")} required />
            <Field name="metric" label={t("lab.metric")}>
              {coreMetrics.map((k) => (
                <option key={k} value={k}>
                  {t("lab.metrics." + k)}
                </option>
              ))}
            </Field>
            <Field name="notes" type="textarea" label={t("lab.notes")} />
            <p className="text-[12px] text-muted">{t("lab.device_note")}</p>
          </Form>
        </Card>
        <Card>
          <CardHeader title={t("lab.import_export")} />
          <Form
            pending={action.isPending}
            error={action.error ?? (importError ? new Error(importError) : null)}
            label={t("lab.import")}
            onSave={(f) => {
              const format = str(f, "format");
              const file = f.get("file");
              if (!(file instanceof File) || !file.size) { setImportError(t("lab.import_choose_file")); return; }
              const ext = file.name.split(".").pop()?.toLowerCase();
              const valid = format === "fit" ? ext === "fit" : format === "csv" ? ext === "csv" : ext === "zip";
              if (!valid) { setImportError(t("lab.import_wrong_type")); return; }
              const limit = format === "apple-health" ? 100 : 20;
              if (file.size > limit * 1024 * 1024) { setImportError(t("lab.import_too_large", { size: limit })); return; }
              setImportError(null);
              const body = new FormData(); body.append("file", file);
              action.mutate({ path: format === "apple-health" ? "/imports/apple-health" : format === "fit" ? "/imports/fit" : "/imports/csv", body });
            }}
          >
            <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted">{t("lab.format")}<select name="format" value={importFormat} onChange={(e) => { setImportFormat(e.target.value); setImportName(""); setImportError(null); }} className={inputClass + " bg-surface text-ink"}>
              <option value="csv">CSV · {t("lab.import_csv_desc")}</option>
              <option value="fit">FIT</option>
              <option value="apple-health">Apple Health · export.zip</option>
            </select></label>
            <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 border border-dashed border-hairline2 bg-surface px-4 py-5 text-center hover:bg-surface2 focus-within:outline focus-within:outline-2 focus-within:outline-primary" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const files = e.dataTransfer.files; if (files.length && importInput.current) { importInput.current.files = files; setImportName(files[0].name); setImportError(null); } }}>
              <span className="text-[14px] font-medium text-ink">{importName || t("lab.drop_file")}</span>
              <span className="text-[12px] text-muted">{t("lab.import_file_rules", { type: importFormat === "fit" ? "FIT" : importFormat === "csv" ? "CSV" : "ZIP", size: importLimit })}</span>
              <input ref={importInput} className="sr-only" type="file" name="file" accept={importAccept} aria-label={t("lab.file")} onChange={(e) => { setImportError(null); setImportName(e.target.files?.[0]?.name ?? ""); }} required />
            </label>
          </Form>
          <p className="mt-3 text-[12px] text-muted">{t("refinement.apple_import_note")}</p>
          <div className="mt-6 flex flex-col gap-3">
            <a className="text-link" href="/lab/export/observations.csv">
              {t("lab.export_csv")} ↗
            </a>
            <a className="text-link" href="/lab/export/account.json">
              {t("lab.export_json")} ↗
            </a>
            <Link className="text-link" to="/app/settings?tab=devices">
              {t("lab.manage_devices")} ↗
            </Link>
          </div>
        </Card>
      </div>
      <Card>
        <CardHeader title={t("lab.privacy")} />
        <div className="grid gap-6 md:grid-cols-2">
          <Form
            key={privacyEntry?.id ?? "default-privacy"}
            pending={action.isPending}
            error={action.error}
            onSave={(f) =>
              action.mutate({
                path: "/lab/entries",
                body: {
                  entry: {
                    kind: "privacy_preferences",
                    date: today,
                    observation_retention_days: num(f, "retention"),
                    agent_log_retention_days: num(f, "audit_days"),
                    density: str(f, "density"),
                  },
                },
              })
            }
          >
            <Field
              name="retention"
              label={t("lab.retention")}
              type="number"
              min={30}
              max={36500}
              value={Number(
                privacyEntry?.payload.observation_retention_days ?? 3650,
              )}
              required
            />
            <Field
              name="audit_days"
              label={t("lab.audit_retention")}
              type="number"
              min={7}
              max={365}
              value={Number(
                privacyEntry?.payload.agent_log_retention_days ?? 90,
              )}
              required
            />
            <Field
              name="density"
              label={t("lab.density")}
              value={String(privacyEntry?.payload.density ?? "comfortable")}
            >
              <option value="comfortable">
                {t("lab.comfortable")}
              </option>
              <option value="compact">{t("lab.compact")}</option>
            </Field>
          </Form>
          <div className="flex flex-col gap-4">
            <label className="flex flex-col gap-2 text-[12px] text-muted">
              {t("lab.source")}
              <select
                className={inputClass + " bg-surface text-ink"}
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setDeletion(null);
                }}
              >
                {[
                  "garmin",
                  "fit",
                  "strava",
                  "whoop",
                  "oura",
                  "coros",
                  "technogym",
                  "csv_import",
                  "manual",
                ].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <Button
              variant="ghost"
              disabled={action.isPending}
              onClick={async () => {
                try {
                  const { api } = await import("../../app/api");
                  setDeletion(
                    await api.get(`/lab/sources/${source}/deletion-preview`),
                  );
                  setLookupError(null);
                } catch (e) {
                  setLookupError((e as Error).message);
                }
              }}
            >
              {t("lab.preview_deletion")}
            </Button>
            {deletion && (
              <div className="border-l-2 border-alert pl-4 text-[13px]">
                <p className="mb-4">{deletion.scope}</p>
                <Value value={deletion.counts} />
                <p className="my-4 text-alertText">{t("lab.irreversible")}</p>
                <Button
                  variant="danger"
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate(
                      {
                        path: `/lab/sources/${source}/delete`,
                        body: { payload_hash: deletion.payload_hash },
                      },
                      { onSuccess: () => setDeletion(null) },
                    )
                  }
                >
                  {t("lab.erase_source")}
                </Button>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
