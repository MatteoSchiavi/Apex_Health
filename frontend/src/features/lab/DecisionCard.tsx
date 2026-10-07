import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  Loading,
  StatPod,
  fmtNum,
  fmtHours,
} from "../../components/kit";
import type { Decision } from "./types";
import { useAction, useLab, useToday, Form, Field, num, str } from "./shared";
export function DecisionCard({ date }: { date?: string } = {}) {
  const { t } = useTranslation();
  const q = useLab<Decision | null>("/lab/decision" + (date ? `?day=${encodeURIComponent(date)}` : ""));
  const save = useAction();
  const today = useToday();
  if (q.isLoading)
    return (
      <Card>
        <Loading />
      </Card>
    );
  if (q.isError || !q.data)
    return (
      <Card>
        <CardHeader title={t("lab.daily_decision")} />
        {q.isError ? <ErrorNote /> : <p className="text-[13px] text-muted">{t("lab.no_historical_decision", { date })}</p>}
      </Card>
    );
  const d = q.data;
  const tone =
    d.action === "train_normally"
      ? "positive"
      : d.action === "recover"
        ? "alert"
        : "warning";
  return (
    <Card className="!p-6 md:!p-8">
      <CardHeader
        eyebrow={date ? `${t("lab.historical_decision")} / ${date}` : "APEX / TODAY"}
        title={t("lab.daily_decision")}
        right={<Badge tone={tone}>{t("lab.actions." + d.action)}</Badge>}
      />
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div>
          <h2 className="text-[28px] font-medium tracking-[-.035em]">
            {t("lab.actions." + d.action)}
          </h2>
          <p className="mt-3 text-[12px] text-muted">
            {t("lab.coverage_label", {
              value: d.data_completeness.coverage_pct,
            })}{" "}
            · {t("lab.confidence." + d.confidence)}
          </p>
          <ul className="mt-5 flex flex-col gap-2 text-[14px] leading-relaxed">
            {d.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <div className="mt-5 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {["accepted", "modified", "rejected", "snoozed"].map((state) => (
              <Button
                key={state}
                variant="ghost"
                disabled={save.isPending || d.outcome?.state === state}
                className="min-h-11 w-full sm:w-auto"
                onClick={() =>
                  save.mutate({
                    path: `/lab/decision/${d.id}/outcome`,
                    body: { state },
                  })
                }
              >
                {t("lab.outcome." + state)}
              </Button>
            ))}
          </div>
          {save.isError && <ErrorNote message={save.error.message} />}
        </div>
        <div className="grid grid-cols-2 gap-4">
          {d.evidence.map((e) => (
            <StatPod
              key={e.id}
              label={t("lab.metrics." + e.metric, {
                defaultValue: e.metric.replaceAll("_", " "),
              })}
              value={e.unit === "h" ? fmtHours(e.value == null ? null : e.value * 3600) : fmtNum(e.value, 1)}
              unit={e.unit === "h" ? undefined : e.unit}
              sub={
                <>
                  <span className="block">
                    {e.origin} · {t("lab.measured")} {e.local_date}
                  </span>
                </>
              }
            />
          ))}
        </div>
      </div>
      <details className="mt-6 border-t border-hairline pt-4 text-[13px]">
        <summary className="cursor-pointer">{t("lab.alternatives")}</summary>
        <div className="mt-4 grid gap-6 md:grid-cols-2">
          <div>
            {d.alternatives.map((a, i) => (
              <p key={i} className="mb-3">
                <strong>{t("lab.actions." + a.action)}</strong> — {a.reason}
              </p>
            ))}
            <p className="text-muted">{d.counterfactual}</p>
            <p className="mt-3 text-muted">{d.limitations.join(" ")}</p>
            <Link to="/app/calendar" className="text-link mt-3">
              {t("lab.review_plan")}
            </Link>
          </div>
          <Form
            pending={save.isPending}
            onSave={(f) =>
              save.mutate({
                path: "/lab/entries",
                body: {
                  entry: {
                    kind: "daily_checkin",
                    date: today,
                    energy: num(f, "energy"),
                    fatigue: num(f, "fatigue"),
                    pain: f.get("pain") === "on",
                    felt_unwell: f.get("felt_unwell") === "on",
                    notes: str(f, "notes"),
                  },
                },
              })
            }
          >
            <div className="grid grid-cols-2 gap-3">
              <Field
                name="energy"
                label={t("lab.energy")}
                type="number"
                min={1}
                max={10}
              />
              <Field
                name="fatigue"
                label={t("lab.fatigue")}
                type="number"
                min={1}
                max={10}
              />
            </div>
            <div className="flex flex-wrap gap-4">
              {["pain", "felt_unwell"].map((k) => (
                <label key={k} className="flex gap-2">
                  <input name={k} type="checkbox" />
                  {t("lab." + k)}
                </label>
              ))}
            </div>
            <Field name="notes" type="textarea" label={t("lab.notes")} />
          </Form>
        </div>
      </details>
      <div className="mt-4 text-[11px] text-muted">
        {d.formula_version} · {d.date} · {t("lab.descriptive")}
      </div>
    </Card>
  );
}
