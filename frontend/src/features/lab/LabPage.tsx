import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
  Segmented,
  StatPod,
  fmtNum,
} from "../../components/kit";
import { NutritionIntegrations } from "../biometrics/NutritionIntegrations";
import { shiftDay } from "../../components/data";
import { TrendChart } from "../../components/charts/TrendChart";
import type { Analysis, Decision, Doc, Entry, Observation } from "./types";
import { coreMetrics } from "./types";
import {
  Field,
  Form,
  inputClass,
  num,
  QueryState,
  str,
  useAction,
  useLab,
  useToday,
  Value,
} from "./shared";
function AnalysisResult({ r }: { r: Analysis }) {
  const { t } = useTranslation();
  const d = r.data;
  return (
    <Card>
      <CardHeader
        title={t("lab.recipes." + r.recipe)}
        right={<Badge>{String(d.state ?? t("lab.descriptive"))}</Badge>}
      />
      {r.recipe === "personal_baseline" ? (
        <>
          <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
            <StatPod
              label={t("lab.median")}
              value={fmtNum(d.median as number | null, 1)}
              unit={String(d.unit ?? "")}
            />
            <StatPod label="MAD" value={fmtNum(d.mad as number | null, 1)} />
            <StatPod
              label={t("lab.samples")}
              value={String(d.sample_count ?? 0)}
            />
            <StatPod
              label={t("lab.missing_days")}
              value={String(d.missing_days ?? "—")}
            />
          </div>
          <p className="text-[13px] text-muted">{t("lab.baseline_note")}</p>
          {Array.isArray(d.empirical_range) && (
            <p className="mt-3 text-[13px]">
              P10–P90 · {d.empirical_range.join(" — ")} {String(d.unit ?? "")}
            </p>
          )}
        </>
      ) : (
        <div className="text-[13px]">
          <Value
            value={Object.fromEntries(
              Object.entries(d).filter(
                ([k]) =>
                  ![
                    "evidence_ids",
                    "pairs",
                    "sessions",
                    "limitations",
                    "formula",
                    "interpretation",
                  ].includes(k),
              ),
            )}
          />
          {Array.isArray(d.sessions) && (
            <details className="mt-4">
              <summary>
                {t("lab.sessions")} · {d.sessions.length}
              </summary>
              <div className="mt-4 flex flex-col gap-4">
                {d.sessions.slice(0, 60).map((v, i) => (
                  <div key={i} className="border-t border-hairline pt-3">
                    <Value value={v} />
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
      <details className="mt-5 border-t border-hairline pt-4 text-[12px] text-muted">
        <summary>{t("lab.method_evidence")}</summary>
        <p className="my-3">
          {r.formula_version} · {r.handle}
        </p>
        <Value value={d.limitations ?? d.interpretation} />
        <p className="mt-3 break-words">
          {Array.isArray(d.evidence_ids) ? d.evidence_ids.join(", ") : ""}
        </p>
      </details>
    </Card>
  );
}
function Baselines() {
  const { t } = useTranslation();
  const today = useToday();
  const [metric, setMetric] = useState("hrv_overnight_rmssd");
  const [origin, setOrigin] = useState("garmin");
  const [start, setStart] = useState(shiftDay(today, -27));
  const [end, setEnd] = useState(today);
  const observations = useLab<Observation[]>(
    `/lab/observations?metric=${metric}&origin=${origin}&start=${start}&end=${end}`,
  );
  const result = useMutation({
    mutationFn: (recipe: string) =>
      api.post<Analysis>("/lab/analytics", {
        recipe,
        metric,
        origin,
        start_date: start,
        end_date: end,
      }),
  });
  const prefs = useAction();
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader title={t("lab.baselines")} />
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-[12px] text-muted">
            {t("lab.metric")}
            <select
              className={inputClass + " mt-2 bg-surface text-ink"}
              value={metric}
              onChange={(e) => {
                setMetric(e.target.value);
                result.reset();
              }}
            >
              {coreMetrics.map((k) => (
                <option key={k} value={k}>
                  {t("lab.metrics." + k)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[12px] text-muted">
            {t("lab.source")}
            <select
              className={inputClass + " mt-2 bg-surface text-ink"}
              value={origin}
              onChange={(e) => {
                setOrigin(e.target.value);
                result.reset();
              }}
            >
              {["garmin", "manual", "whoop", "oura", "coros"].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label className="text-[12px] text-muted">
            {t("lab.start")}
            <input
              className={inputClass + " mt-2"}
              type="date"
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                result.reset();
              }}
            />
          </label>
          <label className="text-[12px] text-muted">
            {t("lab.end")}
            <input
              className={inputClass + " mt-2"}
              type="date"
              value={end}
              max={today}
              onChange={(e) => {
                setEnd(e.target.value);
                result.reset();
              }}
            />
          </label>
        </div>
        <div className="my-5 flex flex-wrap gap-2">
          {[
            "personal_baseline",
            "multisport_load",
            "sleep_timing",
            "gym_progression",
          ].map((k) => (
            <Button
              key={k}
              disabled={result.isPending}
              variant="ghost"
              onClick={() => result.mutate(k)}
            >
              {t("lab.recipes." + k)}
            </Button>
          ))}
        </div>
        <QueryState
          loading={observations.isLoading}
          error={observations.isError}
          empty={observations.data?.length === 0}
        />
        {!!observations.data?.length && (
          <TrendChart
            label={t("lab.metrics." + metric)}
            points={observations.data.map((o) => ({
              date: o.local_date,
              value: o.value,
            }))}
            unit={observations.data[0].unit ?? ""}
            start={start}
            end={end}
          />
        )}
        <p className="mt-4 text-[12px] text-muted">{t("lab.baseline_note")}</p>
        {result.isError && <ErrorNote message={result.error.message} />}
      </Card>
      {result.data && <AnalysisResult r={result.data} />}
      <Card>
        <CardHeader title={t("lab.personal_targets")} />
        <Form
          pending={prefs.isPending}
          error={prefs.error}
          onSave={(f) =>
            prefs.mutate({
              path: "/lab/entries",
              body: {
                entry: {
                  kind: "metric_settings",
                  date: str(f, "date"),
                  sleep_target_h: num(f, "sleep"),
                  ftp_w: num(f, "ftp"),
                  sport: "road_cycling",
                },
              },
            })
          }
        >
          <div className="grid gap-4 md:grid-cols-3">
            <Field
              name="date"
              type="date"
              label={t("lab.effective_date")}
              value={today}
              required
            />
            <Field
              name="sleep"
              type="number"
              label={t("lab.sleep_target")}
              min={4}
              max={12}
            />
            <Field
              name="ftp"
              type="number"
              label="FTP · W"
              min={50}
              max={600}
            />
          </div>
          <p className="text-[12px] text-muted">{t("lab.targets_note")}</p>
        </Form>
      </Card>
    </div>
  );
}
function Experiments() {
  const { t } = useTranslation();
  const today = useToday();
  const definitions = useLab<Entry[]>("/lab/entries?kind=experiment&days=366");
  const action = useAction();
  const [selected, setSelected] = useState<number | null>(null);
  const result = useMutation({
    mutationFn: (id: number) =>
      api.post<Analysis>("/lab/analytics", {
        recipe: "intervention_association",
        experiment_id: id,
      }),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader title={t("lab.experiments")} />
          <p className="mb-5 text-[13px] text-muted">
            {t("lab.experiment_note")}
          </p>
          <QueryState
            loading={definitions.isLoading}
            error={definitions.isError}
            empty={definitions.data?.length === 0}
          />
          {definitions.data?.map((e) => (
            <div key={e.id} className="border-t border-hairline py-4">
              <h3 className="text-[15px] font-medium">
                {String(e.payload.title)}
              </h3>
              <p className="my-2 text-[13px] text-muted">
                {String(e.payload.intervention)} · {e.date} →{" "}
                {String(e.payload.end_date)}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => setSelected(e.id)}>
                  {t("lab.checkin")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={result.isPending}
                  onClick={() => result.mutate(e.id)}
                >
                  {t("lab.analyze")}
                </Button>
              </div>
            </div>
          ))}
        </Card>
        {selected && (
          <Card>
            <CardHeader title={t("lab.checkin")} />
            <Form
              pending={action.isPending}
              error={action.error}
              onSave={(f) =>
                action.mutate({
                  path: "/lab/entries",
                  body: {
                    entry: {
                      kind: "experiment_checkin",
                      date: str(f, "date"),
                      experiment_id: selected,
                      exposed: f.get("exposed") === "on",
                      confounders: f.getAll("confounder"),
                      notes: str(f, "notes"),
                    },
                  },
                })
              }
            >
              <Field
                name="date"
                type="date"
                label={t("lab.start")}
                value={today}
                required
              />
              <label className="flex gap-2 text-[13px]">
                <input name="exposed" type="checkbox" />
                {t("lab.exposed")}
              </label>
              <p className="text-[12px] text-muted">{t("lab.confounders")}</p>
              <div className="flex flex-wrap gap-3">
                {[
                  "travel",
                  "alcohol",
                  "illness",
                  "device_change",
                  "heavy_training",
                ].map((k) => (
                  <label className="flex gap-2 text-[12px]" key={k}>
                    <input type="checkbox" name="confounder" value={k} />
                    {t("lab.confounder." + k)}
                  </label>
                ))}
              </div>
              <Field name="notes" type="textarea" label={t("lab.notes")} />
            </Form>
          </Card>
        )}
        {result.isError && <ErrorNote message={result.error.message} />}{" "}
        {result.data && <AnalysisResult r={result.data} />}
      </div>
      <Card>
        <CardHeader title={t("lab.new_experiment")} />
        <Form
          pending={action.isPending}
          error={action.error}
          onSave={(f) =>
            action.mutate({
              path: "/lab/entries",
              body: {
                entry: {
                  kind: "experiment",
                  date: str(f, "date"),
                  end_date: str(f, "end"),
                  title: str(f, "title"),
                  intervention: str(f, "intervention"),
                  outcome_metric: str(f, "metric"),
                  origin: str(f, "origin"),
                  outcome_lag_days: num(f, "lag"),
                },
              },
            })
          }
        >
          <Field name="title" label={t("lab.title")} required />
          <Field name="intervention" label={t("lab.intervention")} required />
          <div className="grid grid-cols-2 gap-3">
            <Field
              name="date"
              label={t("lab.start")}
              type="date"
              value={today}
              required
            />
            <Field
              name="end"
              label={t("lab.end")}
              type="date"
              value={shiftDay(today, 56)}
              required
            />
          </div>
          <Field name="metric" label={t("lab.outcome_metric")}>
            {coreMetrics.map((k) => (
              <option key={k} value={k}>
                {t("lab.metrics." + k)}
              </option>
            ))}
          </Field>
          <Field name="origin" label={t("lab.source")}>
            {["garmin", "manual", "whoop", "oura"].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </Field>
          <Field
            name="lag"
            label={t("lab.lag")}
            type="number"
            value={1}
            min={0}
            max={7}
            required
          />
        </Form>
      </Card>
    </div>
  );
}
function Nutrition() {
  return <NutritionIntegrations />;
}

function Documents() {
  const { t } = useTranslation();
  const docs = useLab<Doc[]>("/lab/documents");
  const action = useAction();
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader title={t("lab.documents")} />
        <p className="mb-5 max-w-xl text-[13px] text-muted">
          {t("lab.documents_note")}
        </p>
        <Form
          pending={action.isPending}
          error={action.error}
          label={t("lab.upload")}
          onSave={(f) => action.mutate({ path: "/lab/documents", body: f })}
        >
          <input
            className={inputClass}
            name="file"
            type="file"
            accept=".txt,.md,.pdf"
            aria-label={t("lab.file")}
            required
          />
        </Form>
      </Card>
      <QueryState
        loading={docs.isLoading}
        error={docs.isError}
        empty={docs.data?.length === 0}
      />
      {docs.data?.map((d) => (
        <Card key={d.id}>
          <CardHeader
            title={d.filename}
            right={
              <Badge tone={d.status === "confirmed" ? "positive" : "warning"}>
                {t("lab.states." + d.status)}
              </Badge>
            }
          />
          <Form
            pending={action.isPending}
            error={action.error}
            label={t("lab.confirm_document")}
            onSave={(f) =>
              action.mutate({
                path: `/lab/documents/${d.id}/confirm`,
                body: {
                  content_hash: d.content_hash,
                  reviewed_text: str(f, "excerpt"),
                },
              })
            }
          >
            <Field
              name="excerpt"
              type="textarea"
              label={t("lab.reviewed_text")}
              value={d.excerpt ?? ""}
              required
            />
            <p className="break-all text-[11px] text-muted">
              SHA-256 · {d.content_hash}
            </p>
          </Form>
          <div className="mt-5 flex flex-wrap gap-4">
            <a href={`/lab/documents/${d.id}/original`} className="text-link">
              {t("lab.original")} ↗
            </a>
            <Button
              variant="ghost"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  path: `/lab/documents/${d.id}`,
                  method: "delete",
                })
              }
            >
              {t("training.delete")}
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
function Labs() {
  const { t } = useTranslation();
  const today = useToday();
  const panels = useLab<
    {
      id: number;
      panel_date: string;
      panel_type: string;
      ferritin: number | null;
      hemoglobin: number | null;
      notes: string | null;
      markers: {
        marker: string;
        value: number;
        unit: string | null;
        ref_low: number | null;
        ref_high: number | null;
      }[];
    }[]
  >("/labs");
  const action = useAction();
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("lab.add_lab")} />
        <Form
          pending={action.isPending}
          error={action.error}
          onSave={(f) =>
            action.mutate({
              path: "/labs",
              body: {
                panel_date: str(f, "date"),
                panel_type: str(f, "type"),
                ferritin: num(f, "ferritin"),
                hemoglobin: num(f, "hemoglobin"),
                notes: str(f, "notes"),
              },
            })
          }
        >
          <Field
            name="date"
            type="date"
            label={t("lab.start")}
            value={today}
            required
          />
          <Field
            name="type"
            label={t("lab.panel_type")}
            value="blood"
            required
          />
          <Field
            name="ferritin"
            label="Ferritin · ng/ml"
            type="number"
            min={0}
          />
          <Field
            name="hemoglobin"
            label="Hemoglobin · g/dl"
            type="number"
            min={0}
          />
          <Field name="notes" type="textarea" label={t("lab.notes")} />
        </Form>
      </Card>
      <Card>
        <CardHeader title={t("lab.labs")} />
        <QueryState
          loading={panels.isLoading}
          error={panels.isError}
          empty={panels.data?.length === 0}
        />
        {panels.data?.map((p) => (
          <div key={p.id} className="border-t border-hairline py-5">
            <h3 className="mb-4 font-medium">
              {p.panel_date} · {p.panel_type}
            </h3>
            <div className="grid grid-cols-2 gap-5">
              <StatPod
                label="Ferritin"
                value={fmtNum(p.ferritin, 1)}
                unit="ng/ml"
              />
              <StatPod
                label="Hemoglobin"
                value={fmtNum(p.hemoglobin, 1)}
                unit="g/dl"
              />
            </div>
            {p.markers?.length > 0 && (
              <dl className="mt-5 divide-y divide-hairline">
                {p.markers.map((m, i) => (
                  <div
                    key={`${m.marker}-${i}`}
                    className="flex justify-between gap-4 py-3 text-[13px]"
                  >
                    <dt>
                      {m.marker}
                      <span className="block text-[12px] text-muted">
                        {m.ref_low ?? "—"}–{m.ref_high ?? "—"} {m.unit}
                      </span>
                    </dt>
                    <dd
                      className={
                        (m.ref_low != null && m.value < m.ref_low) ||
                        (m.ref_high != null && m.value > m.ref_high)
                          ? "text-warning"
                          : ""
                      }
                    >
                      {fmtNum(m.value, 2)} {m.unit}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="mt-4 text-[13px] text-muted">{p.notes}</p>
          </div>
        ))}
      </Card>
    </div>
  );
}
function Outcomes() {
  const { t } = useTranslation();
  const q = useLab<
    {
      id: number;
      date: string;
      output: Decision;
      outcome: { state: string; notes: string } | null;
    }[]
  >("/lab/decisions");
  return (
    <Card>
      <CardHeader title={t("lab.outcomes")} />
      <p className="mb-5 text-[13px] text-muted">{t("lab.outcomes_note")}</p>
      <QueryState
        loading={q.isLoading}
        error={q.isError}
        empty={q.data?.length === 0}
      />
      {q.data?.map((r) => (
        <div
          key={r.id}
          className="grid gap-3 border-t border-hairline py-4 text-[13px] md:grid-cols-3"
        >
          <span className="num">{r.date}</span>
          <span>{t("lab.actions." + r.output.action)}</span>
          <div>
            <Badge>
              {r.outcome
                ? t("lab.outcome." + r.outcome.state)
                : t("lab.unrecorded")}
            </Badge>
            {r.outcome?.notes && (
              <p className="mt-2 text-muted">{r.outcome.notes}</p>
            )}
          </div>
        </div>
      ))}
    </Card>
  );
}
function Reports() {
  const { t } = useTranslation();
  const q = useLab<
    {
      id: number;
      type: string;
      start: string;
      end: string;
      content: string;
      source_policy: string;
    }[]
  >("/lab/reports");
  return (
    <div className="flex flex-col gap-5">
      <QueryState
        loading={q.isLoading}
        error={q.isError}
        empty={q.data?.length === 0}
      />
      {q.data?.map((r) => (
        <Card key={r.id}>
          <CardHeader
            title={`${t("lab.report_types." + r.type)} · ${r.start} — ${r.end}`}
            right={<Badge>{r.source_policy}</Badge>}
          />
          <p className="whitespace-pre-wrap text-[14px] leading-7">
            {r.content}
          </p>
        </Card>
      ))}
    </div>
  );
}
export default function LabPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "baselines";
  const tabs = [
    "baselines",
    "experiments",
    "nutrition",
    "labs",
    "documents",
    "outcomes",
    "reports",
  ];
  const content: Record<string, () => JSX.Element> = {
    baselines: Baselines,
    experiments: Experiments,
    nutrition: Nutrition,
    labs: Labs,
    documents: Documents,
    outcomes: Outcomes,
    reports: Reports,
  };
  const Panel = content[tab] ?? Baselines;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("lab.heading")} subtitle={t("lab.subtitle")} />
      <div>
        <Segmented
          value={tab}
          onChange={(v) => setParams({ tab: v })}
          options={tabs.map((k) => ({ value: k, label: t("lab." + k) }))}
        />
      </div>
      <Panel key={tab} />
    </div>
  );
}
