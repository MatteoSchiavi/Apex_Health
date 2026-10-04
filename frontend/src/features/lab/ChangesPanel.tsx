import { useTranslation } from "react-i18next";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
} from "../../components/kit";
import type { Draft } from "./types";
import { human, QueryState, useAction, useLab, Value } from "./shared";
export default function ChangesPanel() {
  const { t } = useTranslation();
  const q = useLab<Draft[]>("/lab/changes");
  const action = useAction();
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
                {t("lab.states." + d.status, { defaultValue: human(d.status) })}
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
          <div className="flex gap-3">
            {d.status === "draft" && (
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
