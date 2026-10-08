import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Badge, Button, Card, CardHeader, ErrorNote, Loading } from "../../components/kit";
import type { Constraints, Decision, Draft } from "./types";
import { useAction, useLab, useToday, Form, Field, inputClass, num, str } from "./shared";

function DecisionFeedback({ decision: d }: { decision: Decision }) {
  const { t } = useTranslation();
  const save = useAction();
  const plans = useLab<Constraints>(`/lab/constraints?day=${encodeURIComponent(d.date)}`);
  const proposals = useLab<Draft[]>("/lab/changes");
  const [plannedId, setPlannedId] = useState(String(d.outcome?.planned_session_id ?? d.recommended_action?.planned_session_id ?? ""));
  const [draftId, setDraftId] = useState(String(d.outcome?.draft_id ?? ""));
  const sessions = plans.data?.sessions.filter((s) => s.date === d.date) ?? [];
  const drafts = proposals.data?.filter((p) => p.kind === "session_patch" && p.after.date === d.date) ?? [];
  return <Form label={t("decisionLearning.saveFeedback")} pending={save.isPending || !d.outcome?.state} error={save.error} onSave={(f) => {
    if (!d.outcome?.state) return;
    const body: Record<string, unknown> = { state: d.outcome.state };
    for (const key of ["influenced_plan", "completion"] as const) {
      const value = str(f, key);
      if (value) body[key] = value;
      else if (d.outcome[key] != null) body[key] = null;
    }
    for (const key of ["useful", "pain", "felt_unwell"] as const) {
      const value = str(f, key);
      if (value) body[key] = value === "yes";
      else if (d.outcome[key] != null) body[key] = null;
    }
    for (const key of ["rpe", "soreness"] as const) {
      const value = num(f, key);
      if (value != null || d.outcome[key] != null) body[key] = value;
    }
    if (str(f, "notes") !== (d.outcome.notes ?? "")) body.notes = str(f, "notes");
    if (plannedId || d.outcome.planned_session_id != null) body.planned_session_id = plannedId ? Number(plannedId) : null;
    if (draftId || d.outcome.draft_id != null) body.draft_id = draftId ? Number(draftId) : null;
    save.mutate({ path: `/lab/decision/${d.id}/outcome`, body });
  }}>
    {!d.outcome?.state && <p className="text-[12px] text-muted">{t("decisionLearning.chooseState")}</p>}
    <div className="grid gap-3 sm:grid-cols-2">
      <Field name="influenced_plan" label={t("decisionLearning.influence")} value={d.outcome?.influenced_plan ?? ""}>
        <option value="">{t("decisionLearning.optional")}</option>
        {["yes", "partly", "no"].map((value) => <option key={value} value={value}>{t("decisionLearning." + value)}</option>)}
      </Field>
      <Field name="useful" label={t("decisionLearning.useful")} value={d.outcome?.useful == null ? "" : d.outcome.useful ? "yes" : "no"}>
        <option value="">{t("decisionLearning.optional")}</option>
        <option value="yes">{t("decisionLearning.yes")}</option><option value="no">{t("decisionLearning.no")}</option>
      </Field>
    </div>
    <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted"><span>{t("decisionLearning.notes")}</span><textarea name="notes" className={inputClass} rows={3} maxLength={2000} defaultValue={d.outcome?.notes ?? ""} /></label>
    <details className="border-t border-hairline pt-3 text-[13px]">
      <summary className="cursor-pointer">{t("decisionLearning.postSession")}</summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field name="completion" label={t("decisionLearning.completion")} value={d.outcome?.completion ?? ""}>
          <option value="">{t("decisionLearning.optional")}</option>
          {["completed", "partial", "skipped"].map((value) => <option key={value} value={value}>{t("decisionLearning." + value)}</option>)}
        </Field>
        <Field name="rpe" label={t("decisionLearning.rpe")} type="number" min={0} max={10} value={d.outcome?.rpe ?? ""} />
        <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted"><span>{t("decisionLearning.soreness")}</span><input name="soreness" className={inputClass} type="number" step={1} min={0} max={10} defaultValue={d.outcome?.soreness ?? ""} /></label>
        {(["pain", "felt_unwell"] as const).map((key) => <Field key={key} name={key} label={t("lab." + key)} value={d.outcome?.[key] == null ? "" : d.outcome[key] ? "yes" : "no"}>
          <option value="">{t("decisionLearning.optional")}</option>
          <option value="yes">{t("decisionLearning.yes")}</option><option value="no">{t("decisionLearning.no")}</option>
        </Field>)}
        <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted"><span>{t("decisionLearning.plannedSession")}</span>
          <select className={inputClass + " bg-surface text-ink"} value={plannedId} onChange={(e) => { setPlannedId(e.target.value); if (draftId && drafts.find((p) => String(p.id) === draftId)?.after.target_id !== Number(e.target.value)) setDraftId(""); }}>
            <option value="">{t("decisionLearning.noLink")}</option>
            {plannedId && !sessions.some((s) => String(s.id) === plannedId) && <option value={plannedId}>#{plannedId}</option>}
            {sessions.map((s) => <option key={s.id} value={s.id}>#{s.id} · {s.description || s.session_type || d.date}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted"><span>{t("decisionLearning.proposal")}</span>
          <select className={inputClass + " bg-surface text-ink"} value={draftId} onChange={(e) => { setDraftId(e.target.value); const target = drafts.find((p) => String(p.id) === e.target.value)?.after.target_id; if (typeof target === "number") setPlannedId(String(target)); }}>
            <option value="">{t("decisionLearning.noLink")}</option>
            {draftId && !drafts.some((p) => String(p.id) === draftId) && <option value={draftId}>#{draftId}</option>}
            {drafts.map((p) => <option key={p.id} value={p.id}>#{p.id} · {p.reason}</option>)}
          </select>
        </label>
      </div>
      {(plans.isError || proposals.isError) && <ErrorNote />}
    </details>
    {save.isSuccess && <p role="status" className="text-[12px] text-positiveText">{t("decisionLearning.feedbackSaved")}</p>}
  </Form>;
}

export function DecisionCard({ date }: { date?: string } = {}) {
  const { t } = useTranslation();
  const q = useLab<Decision | null>("/lab/decision" + (date ? `?day=${encodeURIComponent(date)}` : ""));
  const save = useAction();
  const today = useToday();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackDecision, setFeedbackDecision] = useState<number | null>(null);
  if (q.isLoading) return <Card><Loading /></Card>;
  if (q.isError || !q.data) return <Card><CardHeader title={t("lab.daily_decision")} />{q.isError ? <ErrorNote /> : <p className="text-[13px] text-muted">{t("lab.no_historical_decision", { date })}</p>}</Card>;
  const d = q.data;
  const tone = d.action === "train_normally" ? "positive" : d.action === "recover" ? "alert" : "warning";
  const cover = d.data_coverage ?? d.data_completeness;
  return <Card className="!p-6 md:!p-8">
    <CardHeader eyebrow={date ? `${t("lab.historical_decision")} / ${date}` : t("decisionLearning.today")} title={t("lab.daily_decision")} right={<Badge tone={tone}>{t("lab.actions." + d.action)}</Badge>} />
    <h2 className="text-[25px] font-medium tracking-[-.035em] sm:text-[28px]">{d.headline ?? t("lab.actions." + d.action)}</h2>
    <p className="mt-3 text-[12px] text-muted">{t("lab.coverage_label", { value: cover.coverage_pct })} · {t("lab.confidence." + d.confidence)}</p>
    <ul className="mt-4 flex flex-col gap-2 text-[14px] leading-relaxed">{(d.contributors ?? d.reasons).map((r) => <li key={r}>{r}</li>)}</ul>
    <p className="mt-4 text-[13px] text-muted">{d.recommended_action?.reason ?? d.next_step}</p>
    <div className="mt-5 flex flex-wrap gap-x-6 gap-y-3 text-[13px]">
      <Link to="/app/calendar" className="text-link">{t("lab.review_plan")}</Link>
      <Link to="/app/coach" className="text-link">{t("decisionLearning.askApex")}</Link>
    </div>
    <div className="mt-5 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
      {["accepted", "modified", "rejected", "snoozed"].map((state) => <Button key={state} variant="ghost" disabled={save.isPending || d.outcome?.state === state} className="min-h-11 w-full sm:w-auto" onClick={() => { setFeedbackDecision(d.id); save.mutate({ path: `/lab/decision/${d.id}/outcome`, body: { state } }); }}>{t("lab.outcome." + state)}</Button>)}
    </div>
    {save.isError && <ErrorNote message={save.error.message} />}
    {(d.outcome || feedbackDecision === d.id) && <details className="mt-4 border-t border-hairline pt-4 text-[13px]" onToggle={(e) => setFeedbackOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer">{t("decisionLearning.feedback")}</summary>
      {feedbackOpen && <div className="mt-4"><DecisionFeedback key={d.id} decision={d} /></div>}
    </details>}
    <details className="mt-4 border-t border-hairline pt-4 text-[13px]">
      <summary className="cursor-pointer">{t("decisionLearning.details")}</summary>
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        {d.key_changes?.some(change => change.baseline == null) && <p className="text-[12px] text-muted">{t("decisionLearning.noBaseline")}</p>}
        <ul className="flex flex-col gap-3">
          {d.evidence.map(e => <li key={e.id}><span className="block font-medium">{t("lab.metrics." + e.metric, { defaultValue: e.metric.replaceAll("_", " ") })}</span><span className="block text-muted">{e.origin} · {t("lab.measured")} {e.local_date}</span></li>)}
        </ul>
        <div>
          <h3 className="mb-3 font-medium">{t("lab.alternatives")}</h3>
          {d.alternatives.map((a, i) => <p key={i} className="mb-3"><strong>{t("lab.actions." + a.action)}</strong> — {a.reason}</p>)}
          <p className="text-muted">{d.counterfactual}</p>
          <p className="mt-3 text-muted">{d.limitations.join(" ")}</p>
        </div>
      </div>
      {!date && <details className="mt-4 border-t border-hairline pt-4"><summary className="cursor-pointer">{t("decisionLearning.checkin")}</summary><div className="mt-4">
        <Form pending={save.isPending} onSave={(f) => save.mutate({ path: "/lab/entries", body: { entry: { kind: "daily_checkin", date: today, energy: num(f, "energy"), fatigue: num(f, "fatigue"), pain: f.get("pain") === "on", felt_unwell: f.get("felt_unwell") === "on", notes: str(f, "notes") } } })}>
          <div className="grid grid-cols-2 gap-3"><Field name="energy" label={t("lab.energy")} type="number" min={1} max={10} /><Field name="fatigue" label={t("lab.fatigue")} type="number" min={1} max={10} /></div>
          <div className="flex flex-wrap gap-4">{["pain", "felt_unwell"].map((k) => <label key={k} className="flex gap-2"><input name={k} type="checkbox" />{t("lab." + k)}</label>)}</div>
          <Field name="notes" type="textarea" label={t("lab.notes")} />
        </Form>
      </div></details>}
    </details>
    <div className="mt-4 text-[11px] text-muted">{d.formula_version} · {d.date} · {t("lab.descriptive")}</div>
  </Card>;
}
