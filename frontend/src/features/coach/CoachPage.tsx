import { useSearchParams } from "react-router-dom";
import ChangesPanel from "../lab/ChangesPanel";
import { Segmented } from "../../components/kit";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Plus, Send, Trash2 } from "lucide-react";
import {
  api,
  type ChatSessionDetail,
  type ChatSessionOut,
} from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Loading,
  PageHeader,
} from "../../components/kit";
function stored(key: string) {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function CheckedEvidence({ grounding }: { grounding: unknown }) {
  const { t } = useTranslation();
  const receipt = grounding as { status?: string; verified_claims?: { metric: string; value: unknown; unit?: string }[] } | null;
  const claims = receipt?.status === "structured" && Array.isArray(receipt.verified_claims)
    ? receipt.verified_claims.filter(c => typeof c?.metric === "string" &&
      (typeof c.value === "string" || typeof c.value === "boolean" || (typeof c.value === "number" && Number.isFinite(c.value)))) : [];
  if (!claims.length) return null;
  return <details className="mt-3 border-t border-hairline pt-3 text-[12px]">
    <summary className="cursor-pointer text-muted">{t("coach.checked_evidence")}</summary>
    <dl className="mt-3 space-y-2">{claims.map((claim, index) => <div key={index} className="flex flex-wrap justify-between gap-x-4 gap-y-1">
      <dt>{t("lab.metrics." + claim.metric, { defaultValue: claim.metric.replace(/[._]/g, " ") })}</dt>
      <dd className="tabular-nums">{String(claim.value)}{typeof claim.unit === "string" ? " " + claim.unit : ""}</dd>
    </div>)}</dl>
    <p className="mt-3 text-muted">{t("coach.checked_evidence_note")}</p>
  </details>;
}

export default function CoachPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "analysis";
  const qc = useQueryClient();
  const uid = useUi((s) => s.me!.user_id);
  const activeKey = "apex.chat." + uid + ".active";
  const draftKey = "apex.chat." + uid + ".draft";
  const [activeId, setActiveId] = useState<number | null>(() =>
    Number(stored(activeKey)) > 0 ? Number(stored(activeKey)) : null,
  );
  const [draft, setDraft] = useState(() => stored(draftKey));
  const [historyOpen, setHistoryOpen] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const sessions = useQuery({
    queryKey: ["chats", uid],
    queryFn: () => api.get<ChatSessionOut[]>("/coach/chats"),
  });
  const active = useQuery({
    queryKey: ["chat", uid, activeId],
    queryFn: () => api.get<ChatSessionDetail>("/coach/chats/" + activeId),
    enabled: activeId != null,
  });
  useEffect(() => {
    try {
      if (activeId == null) localStorage.removeItem(activeKey);
      else localStorage.setItem(activeKey, String(activeId));
    } catch {
      /* unavailable */
    }
  }, [activeId, activeKey]);
  useEffect(() => {
    try {
      if (draft) localStorage.setItem(draftKey, draft);
      else localStorage.removeItem(draftKey);
    } catch {
      /* unavailable */
    }
  }, [draft, draftKey]);
  const send = useMutation({
    mutationFn: ({
      text,
      sessionId,
    }: {
      text: string;
      sessionId: number | null;
    }) =>
      api.post<ChatSessionDetail>("/coach/chats", {
        text,
        ...(sessionId != null ? { session_id: sessionId } : {}),
      }),
    onMutate: () => setDraft(""),
    onSuccess: (data) => {
      setActiveId(data.id);
      qc.setQueryData(["chat", uid, data.id], data);
      qc.invalidateQueries({ queryKey: ["chats", uid] });
      qc.invalidateQueries({ queryKey: ["lab"] });
    },
    onError: (_err, variables) => {
      setDraft(variables.text);
      qc.invalidateQueries({ queryKey: ["chat", uid, variables.sessionId] });
      qc.invalidateQueries({ queryKey: ["chats", uid] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete("/coach/chats/" + id),
    onSuccess: (_data, id) => {
      if (id === activeId) setActiveId(null);
      qc.removeQueries({ queryKey: ["chat", uid, id] });
      qc.invalidateQueries({ queryKey: ["chats", uid] });
    },
  });
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active.data?.messages.length, send.isPending]);
  function submit() {
    if (draft.trim() && !send.isPending && !active.isLoading)
      send.mutate({ text: draft.trim(), sessionId: activeId });
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("coach.title")}
        subtitle={t("coach.subtitle")}
        actions={
          <Button
            variant="ghost"
            icon={<Plus size={16} />}
            disabled={send.isPending}
            onClick={() => {
              setActiveId(null);
              send.reset();
            }}
          >
            {t("coach.new_chat")}
          </Button>
        }
      />
      <div>
        <Segmented
          value={tab}
          onChange={(v) => setParams({ tab: v })}
          options={[
            { value: "analysis", label: t("lab.analysis") },
            { value: "changes", label: t("lab.changes") },
          ]}
        />
      </div>
      {tab === "changes" ? (
        <ChangesPanel />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[240px_1fr]">
          <aside className="min-w-0">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              aria-expanded={historyOpen}
              className="mb-4 text-[14px] font-medium xl:hidden"
            >
              {t("coach.past_chats")} ↓
            </button>
            <div className={(historyOpen ? "" : "hidden ") + "xl:block"}>
              <h2 className="section-label mb-5 hidden xl:block">
                {t("coach.past_chats")}
              </h2>
              {sessions.isLoading ? (
                <Loading />
              ) : sessions.isError ? (
                <ErrorNote />
              ) : !sessions.data?.length ? (
                <p className="text-[13px] text-muted">{t("coach.no_chats")}</p>
              ) : (
                <div className="max-h-[55vh] overflow-y-auto">
                  {sessions.data.map((s) => (
                    <div
                      key={s.id}
                      className={
                        "group mb-1 flex items-center gap-2 px-3 py-4 " +
                        (activeId === s.id ? "bg-surface2" : "hover:bg-surface")
                      }
                    >
                      <button
                        disabled={send.isPending}
                        className="min-w-0 flex-1 text-left"
                        onClick={() => {
                          setActiveId(s.id);
                          setHistoryOpen(false);
                          send.reset();
                        }}
                      >
                        <span className="block truncate text-[13px] font-medium">
                          {s.title ?? t("coach.new_chat")}
                        </span>
                        <span className="mt-1 block text-[12px] text-muted">
                          {new Date(s.last_activity_at).toLocaleDateString()} ·{" "}
                          {s.message_count}
                        </span>
                      </button>
                      <button
                        disabled={send.isPending || remove.isPending}
                        onClick={() => {
                          if (confirm(t("coach.delete_confirm")))
                            remove.mutate(s.id);
                        }}
                        aria-label={t("training.delete")}
                        className="p-2 text-muted hover:text-alertText"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {remove.isError && <ErrorNote />}
              <p className="mt-6 border-t border-hairline pt-4 text-[12px] text-muted">
                {t("coach.saved_locally")}
              </p>
            </div>
          </aside>
          <Card className="flex h-[min(75dvh,850px)] min-h-[480px] flex-col !p-0">
            <div className="flex items-center justify-between border-b border-hairline px-6 py-4">
              <span className="text-[13px] font-medium">
                {active.data?.title ?? t("coach.conversation")}
              </span>
              {typeof active.data?.messages.at(-1)?.referenced_data?.model === "string" && (
                <Badge>{String(active.data.messages.at(-1)!.referenced_data!.model)}</Badge>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 md:px-8">
              {active.isLoading ? (
                <Loading />
              ) : active.isError ? (
                <ErrorNote />
              ) : !active.data?.messages.length && !send.isPending ? (
                <div className="flex h-full flex-col items-start justify-center">
                  <span className="mb-6 text-[12px] text-muted">
                    APEX / {t("nav.coach")}
                  </span>
                  <h2 className="max-w-lg text-[28px] font-medium leading-tight tracking-[-.04em]">
                    {t("coach.empty_title")}
                  </h2>
                  <p className="mt-4 max-w-md text-[14px] leading-relaxed text-muted">
                    {t("coach.empty_body")}
                  </p>
                  <div className="mt-8 flex w-full flex-col border-t border-hairline">
                    {[
                      "prompt_recovery",
                      "prompt_training",
                      "prompt_trends",
                    ].map((k) => (
                      <button
                        key={k}
                        onClick={() => setDraft(t("design." + k))}
                        className="flex items-center justify-between border-b border-hairline py-4 text-left text-[13px]"
                      >
                        {t("design." + k)}
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-6">
                  {active.data?.messages.map((m) => (
                    <div
                      key={m.id}
                      className={
                        m.role === "user" ? "ml-8 bg-surface2 p-5" : "pr-6"
                      }
                    >
                      <span className="mb-2 block text-[12px] font-medium text-muted">
                        {m.role === "user" ? t("social.you") : t("nav.coach")}
                      </span>
                      <p className="whitespace-pre-wrap break-words text-[14px] leading-7">
                        {m.content.startsWith("I couldn't finish this request within the tool budget")
                          ? t("coach.incomplete_reply") : m.content}
                      </p>
                      {m.role === "assistant" &&
                        !!m.referenced_data?.grounding && (
                          <p className="mt-3 text-[12px] text-muted">
                            {t(
                              "lab.grounding." +
                                String(
                                  (
                                    m.referenced_data.grounding as {
                                      status: string;
                                    }
                                  ).status,
                                ),
                            )}
                          </p>
                        )}
                      {m.role === "assistant" && <CheckedEvidence grounding={m.referenced_data?.grounding} />}
                      {m.model_tier === "medical" && m.role === "assistant" && (
                        <p className="mt-4 text-[12px] text-warningText">
                          {t("coach.medical_disclaimer")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {send.isPending && send.variables && (
                <div className="ml-8 mt-6 bg-surface2 p-5">
                  <span className="mb-2 block text-[12px] font-medium text-muted">
                    {t("social.you")}
                  </span>
                  <p className="whitespace-pre-wrap break-words text-[14px] leading-7">
                    {send.variables.text}
                  </p>
                </div>
              )}
              {send.isPending && (
                <div role="status" className="mt-6 text-[13px] text-muted">
                  {t("coach.thinking")}
                </div>
              )}
              <div ref={bottom} />
            </div>
            <div className="border-t border-hairline p-5">
              {send.isError && (
                <div className="mb-4">
                  <ErrorNote message={send.error.message} />
                </div>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
                className="flex items-end gap-3"
              >
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  maxLength={8000}
                  aria-label={t("coach.placeholder")}
                  placeholder={t("coach.placeholder")}
                  rows={2}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                  className="min-w-0 flex-1 resize-none border border-hairline bg-transparent px-4 py-3 text-[14px] outline-none"
                />
                <Button
                  type="submit"
                  disabled={
                    !draft.trim() ||
                    send.isPending ||
                    active.isLoading ||
                    active.isError
                  }
                  icon={<Send size={16} />}
                >
                  <span className="sr-only sm:not-sr-only">
                    {t("coach.send")}
                  </span>
                </Button>
              </form>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
