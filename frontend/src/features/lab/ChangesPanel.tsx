import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader title={t("lab.changes")} />
        <p className="max-w-2xl text-[13px] leading-relaxed text-muted">
          {t("lab.approval_note")}
        </p>
      </Card>
      <QueryState
        loading={q.isLoading}
        error={q.isError}
        empty={q.data?.length === 0}
      />
      {q.data?.some((d) => d.id === replacementId && d.status === "draft") && (
        <p role="status" className="text-[13px] text-muted">
          {t("decisionLearning.newApprovalRequired")}
        </p>
      )}
      {q.data?.map((d) => (
        <Card key={d.id}>
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
                    setReplacementId((result as Draft).id);
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
      ))}
      {action.isError && <ErrorNote message={action.error.message} />}
    </div>
  );
}
