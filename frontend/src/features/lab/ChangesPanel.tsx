import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
} from "../../components/kit";
import type { Draft } from "./types";
import { Form, human, inputClass, num, QueryState, str, useAction, useLab, Value } from "./shared";
export default function ChangesPanel() {
  const { t } = useTranslation();
  const q = useLab<Draft[]>("/lab/changes");
  const action = useAction();
  const [editing, setEditing] = useState<number | null>(null);
  const [replacementId, setReplacementId] = useState<number | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const match = /^#change-([1-9]\d*)$/.exec(location.hash);
  const parsedId = match ? Number(match[1]) : null;
  const targetId = parsedId !== null && Number.isSafeInteger(parsedId) ? parsedId : null;
  const uid = useUi((state) => state.me?.user_id);
  const targetInList = targetId !== null && !!q.data?.some((d) => d.id === targetId);
  // The list contains only the newest 50 proposals. Resolve older links through
  // an account-scoped read without replacing the rest of the review list.
  const needsTarget = targetId !== null && q.isSuccess && !targetInList;
  const selected = useQuery({
    queryKey: ["lab", uid, `/lab/changes/${targetId}`],
    queryFn: () => api.get<Draft>(`/lab/changes/${targetId}`),
    enabled: needsTarget,
    retry: false,
  });
  const selectedDraft = needsTarget && !selected.isError && selected.data?.id === targetId ? selected.data : null;
  const drafts = selectedDraft ? [selectedDraft, ...(q.data ?? [])] : (q.data ?? []);
  const targetExists = targetInList || selectedDraft !== null;
  const targetMissing = needsTarget && (selected.error instanceof ApiError && selected.error.status === 404 || selected.isSuccess && !selectedDraft);
  const targetFailed = q.isError || needsTarget && selected.isError && !targetMissing;
  const loading = q.isLoading || needsTarget && selected.isLoading;
  useEffect(() => {
    if (!targetExists || loading || targetFailed) return;
    const card = document.getElementById(`change-${targetId}`);
    card?.focus({ preventScroll: true });
    card?.scrollIntoView({ block: "start" });
  }, [targetId, targetExists, loading, targetFailed]);
  const showAll = () => navigate({ pathname: location.pathname, search: location.search, hash: "" }, { replace: true, state: location.state });
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader title={t("lab.changes")} />
        <p className="max-w-2xl text-[13px] leading-relaxed text-muted">
          {t("lab.approval_note")}
        </p>
      </Card>
      {location.hash && (
        <div role={targetId === null || targetFailed || targetMissing ? "alert" : "status"} className="flex flex-wrap items-center gap-3 text-[13px]">
          {targetId === null ? <p>{t("dailyFlow.proposalInvalid")}</p>
            : targetFailed ? <p>{t("dailyFlow.proposalLoadFailed")}</p>
            : targetMissing ? <p>{t("dailyFlow.proposalUnavailable")}</p>
            : targetExists ? <p>{t("dailyFlow.proposalSelected")}</p> : null}
          {targetFailed && <Button variant="ghost" onClick={() => { void (q.isError ? q.refetch() : selected.refetch()); }}>{t("betaCoach.retry")}</Button>}
          <Button variant="ghost" onClick={showAll}>{t("dailyFlow.showAllProposals")}</Button>
        </div>
      )}
      <QueryState
        loading={loading}
        error={q.isError}
        empty={q.isSuccess && !loading && drafts.length === 0}
      />
      {drafts.some((d) => d.id === replacementId && d.status === "draft") && (
        <p role="status" className="text-[13px] text-muted">
          {t("decisionLearning.newApprovalRequired")}
        </p>
      )}
      {drafts.map((d) => (
        <section key={d.id} id={`change-${d.id}`} tabIndex={-1} data-selected={targetId === d.id && !q.isError ? "true" : undefined} className={`scroll-mt-24 outline-none ${targetId === d.id && !q.isError ? "ring-2 ring-ink ring-offset-2" : ""}`}>
        <Card>
          <CardHeader
            title={t("lab.change_kinds." + d.kind, {
              defaultValue: human(d.kind),
            })}
            right={
              <Badge
                tone={
                  d.status === "applied_locally"
                    ? "positive"
                    : d.status === "draft"
                      ? "warning"
                      : "neutral"
                }
              >
                {d.status === "superseded"
                  ? t("decisionLearning.superseded")
                  : t("lab.states." + d.status, { defaultValue: human(d.status) })}
              </Badge>
            }
          />
          <p className="mb-5 text-[14px]">{d.reason}</p>
          {d.adaptation && <div className="mb-4 text-[13px] text-muted"><p>{t("athlete.objective_"+d.adaptation.objective_status)}</p><p className="mt-2">{d.adaptation.data_gaps.length ? t("athlete.adaptation_gaps") : t("athlete.adaptation_evidence")}</p><p>{d.adaptation.evidence_ids.join(" · ") || t("lab.no_evidence")}</p></div>}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="border border-hairline p-4 text-[13px]">
              <h3 className="eyebrow mb-3">{t("lab.before")}</h3>
              <Value
                value={
                  d.kind === "context_patch"
                    ? (d.before.content ?? "")
                    : d.before
                }
              />
            </div>
            <div className="border-l-2 border-ink bg-surface2 p-4 text-[13px]">
              <h3 className="eyebrow mb-3">{t("lab.after")}</h3>
              <Value
                value={
                  d.kind === "context_patch" ? (d.after.content ?? "") : d.after
                }
              />
            </div>
          </div>
          <details className="my-4 text-[12px] text-muted">
            <summary>{t("lab.approval_details")}</summary>
            <p className="mt-3 break-all">SHA-256 · {d.payload_hash}</p>
            <p>
              {t("lab.expires")} {new Date(d.expires_at).toLocaleString()}
            </p>
            <p>{d.evidence_ids.join(", ") || t("lab.no_evidence")}</p>
          </details>
          {d.receipt && (
            <p className="mb-4 text-[13px] text-muted">
              {t("lab.receipt")} · {t("lab.states." + d.receipt.state)} ·{" "}
              {t("lab.delivery." + d.receipt.external_delivery)}
            </p>
          )}
          {d.kind === "session_patch" && d.status === "applied_locally" && d.receipt?.state === "applied_locally" && typeof d.after.target_id === "number" && Number.isSafeInteger(d.after.target_id) && d.after.target_id > 0 && (
            <Link className="text-link mb-4 inline-block text-[13px]" to={`/app/workouts/${d.after.target_id}`}>{t("dailyFlow.viewUpdatedWorkout")}</Link>
          )}
          {editing === d.id && d.kind === "session_patch" && d.status === "draft" && (
            <div className="mb-5 border border-hairline p-4">
              <p className="mb-4 text-[13px] text-muted">{t("decisionLearning.editCaption")}</p>
              <Form label={t("decisionLearning.saveEdit")} pending={action.isPending} onSave={(f) => {
                const body: Record<string, unknown> = {
                  reason: str(f, "reason"),
                };
                if (str(f, "description") !== (d.after.description ?? "")) {
                  body.description = str(f, "description");
                }
                const duration = num(f, "target_duration_min");
                if (duration != null) body.target_duration_min = duration;
                action.mutate({ path: `/lab/changes/${d.id}/edit`, body }, {
                  onSuccess: (result) => {
                    setEditing(null);
                    const replacement = (result as Draft).id;
                    setReplacementId(replacement);
                    if (Number.isSafeInteger(replacement) && replacement > 0) navigate({pathname:location.pathname,search:location.search,hash:`#change-${replacement}`},{replace:true,state:location.state});
                  },
                });
              }}>
                <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted">
                  <span>{t("lab.duration")}</span>
                  <input name="target_duration_min" className={inputClass} type="number" min={0} max={1440} step={1} defaultValue={typeof d.after.target_duration_min === "number" ? d.after.target_duration_min : ""} />
                </label>
                <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted">
                  <span>{t("decisionLearning.sessionDescription")}</span>
                  <textarea name="description" className={inputClass} maxLength={2000} rows={3} defaultValue={typeof d.after.description === "string" ? d.after.description : ""} />
                </label>
                <label className="flex min-w-0 flex-col gap-2 text-[12px] text-muted">
                  <span>{t("decisionLearning.editReason")}</span>
                  <textarea name="reason" className={inputClass} maxLength={2000} rows={2} required defaultValue={d.reason} />
                </label>
                <Button variant="ghost" type="button" disabled={action.isPending} onClick={() => setEditing(null)}>{t("lab.cancel")}</Button>
              </Form>
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            {d.status === "draft" && editing !== d.id && (
              <>
                <Button
                  disabled={
                    action.isPending || Date.parse(d.expires_at) < Date.now()
                  }
                  onClick={() =>
                    action.mutate({
                      path: `/lab/changes/${d.id}/approve`,
                      body: { payload_hash: d.payload_hash },
                    })
                  }
                >
                  {t("lab.approve")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({ path: `/lab/changes/${d.id}/reject` })
                  }
                >
                  {t("lab.reject")}
                </Button>
                {d.kind === "session_patch" && (
                  <Button variant="ghost" disabled={action.isPending || Date.parse(d.expires_at) < Date.now()} onClick={() => setEditing(d.id)}>
                    {t("decisionLearning.editProposal")}
                  </Button>
                )}
              </>
            )}
            {d.status === "applied_locally" && d.receipt?.undo_available && (
              <Button
                variant="ghost"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({ path: `/lab/changes/${d.id}/undo` })
                }
              >
                {t("lab.undo")}
              </Button>
            )}
          </div>
        </Card>
        </section>
      ))}
      {action.isError && <ErrorNote message={action.error.message} />}
    </div>
  );
}
