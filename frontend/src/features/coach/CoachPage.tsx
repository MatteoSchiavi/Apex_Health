import { AiConsentPanel, useAiState } from "../athlete/AiConsentPanel";
import { referencedProposalLinks } from "./proposalLinks";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import type { AthleteDay } from "../athlete/types";
import { validatedCoachContext } from "./coachContext";
import ChangesPanel from "../lab/ChangesPanel";
import { Segmented } from "../../components/kit";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, MoreHorizontal, Plus, Send, Trash2 } from "lucide-react";
import {
  api,
  ApiError,
  type ChatSessionDetail,
  type ChatSessionOut,
} from "../../app/api";
import { useUi } from "../../app/stores/ui";
import {
  Button,
  Card,
  ErrorNote,
  Loading,
  PageHeader,
  friendlyDiscipline,
} from "../../components/kit";
function stored(key: string) {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function PendingReply({ startedAt }: { startedAt: number }) {
  const { t } = useTranslation();
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return <div className="mt-6 space-y-2 text-[13px] text-muted">
    <p role="status">{t(elapsed >= 30 ? "v01Coach.waiting_long" : "v01Coach.waiting")}</p>
    <p className="tabular-nums" aria-live="off">{t("v01Coach.elapsed", {
      time: `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`,
    })}</p>
    <p className="text-[12px]">{t("v01Coach.waiting_note")}</p>
  </div>;
}

function CheckedEvidence({ grounding }: { grounding: unknown }) {
  const { t } = useTranslation();
  const receipt = grounding as { status?: string; verified_claims?: { metric: string; measurement_metric?: string; value: unknown; unit?: string }[] } | null;
  const claims = receipt?.status === "structured" && Array.isArray(receipt.verified_claims)
    ? receipt.verified_claims.filter(c => typeof c?.metric === "string" &&
      (typeof c.value === "string" || typeof c.value === "boolean" || (typeof c.value === "number" && Number.isFinite(c.value)))) : [];
  if (!claims.length) return null;
  return <details className="mt-3 border-t border-hairline pt-3 text-[12px]">
    <summary className="cursor-pointer text-muted">{t("coach.checked_evidence")}</summary>
    <dl className="mt-3 space-y-2">{claims.map((claim, index) => {
      const measurement = typeof claim.measurement_metric === "string" ? claim.measurement_metric : null;
      const metric = measurement || claim.metric;
      return <div key={index} className="flex flex-wrap justify-between gap-x-4 gap-y-1">
      <dt>{t("lab.metrics." + metric, { defaultValue: metric.replace(/[._]/g, " ") })}
        {measurement && <> · {t("coach.statistic." + claim.metric, { defaultValue: claim.metric })}</>}</dt>
      <dd className="tabular-nums">{String(claim.value)}{typeof claim.unit === "string" ? " " + claim.unit : ""}</dd>
    </div>; })}</dl>
    <p className="mt-3 text-muted">{t("coach.checked_evidence_note")}</p>
  </details>;
}

export default function CoachPage() {
  const uid = useUi((s) => s.me?.user_id);
  // A changed account must never inherit a mounted account's composer or chat.
  return uid == null ? null : <CoachWorkspace key={uid} uid={uid} />;
}

function CoachWorkspace({ uid }: { uid: number }) {
  const { t } = useTranslation();
  const aiState = useAiState();
  const aiAllowed = aiState.data?.effective_access !== "disabled" && !!aiState.data && !aiState.data.budget.exhausted;
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const context = validatedCoachContext(location.state, uid);
  const contextKey = context ? `${uid}:${context.date}:${context.plannedSessionId ?? "day"}` : null;
  const contextState = context ? { coachContext: context } : null;
  const day = useQuery({
    queryKey: ["athlete-day", uid, context?.date],
    queryFn: () => api.get<AthleteDay>("/athlete/day?date=" + context!.date),
    enabled: context != null,
    retry: false,
  });
  const contextReady = context != null && !day.isError && !day.isFetching && day.data?.date === context.date &&
    (context.plannedSessionId === undefined || (Array.isArray(day.data.sessions) && day.data.sessions.some(session => session.id === context.plannedSessionId)));
  const [replaceContextKey, setReplaceContextKey] = useState<string | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const tab = params.get("tab") === "changes" ? "changes" : "analysis";
  const qc = useQueryClient();
  const activeKey = "apex.chat." + uid + ".active";
  const draftKey = "apex.chat." + uid + ".draft";
  const [activeId, setActiveId] = useState<number | null>(() =>
    Number(stored(activeKey)) > 0 ? Number(stored(activeKey)) : null,
  );
  const [draft, setDraft] = useState(() => stored(draftKey));
  const [historyOpen, setHistoryOpen] = useState(false);
  const [openActionsId, setOpenActionsId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChatSessionOut | null>(null);
  const [deletedTitle, setDeletedTitle] = useState<string | null>(null);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const newChatButton = useRef<HTMLDivElement>(null);
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
    // Retrying an earlier question must not clear a follow-up being composed.
    onMutate: ({ text }) => setDraft(current => current.trim() === text ? "" : current),
    onSuccess: (data) => {
      setActiveId(data.id);
      qc.setQueryData(["chat", uid, data.id], data);
      qc.invalidateQueries({ queryKey: ["chats", uid] });
      qc.invalidateQueries({ queryKey: ["lab"] });
    },
    onError: (_err, variables) => {
      // The composer remains editable while waiting. Never overwrite newer text.
      setDraft(current => current || variables.text);
      qc.invalidateQueries({ queryKey: ["chat", uid, variables.sessionId] });
      qc.invalidateQueries({ queryKey: ["chats", uid] });
    },
    onSettled: () => { void qc.invalidateQueries({ queryKey: ["athlete-ai", uid] }); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete("/coach/chats/" + id),
    onSuccess: async (_data, id) => {
      // A detail request already in flight must not restore a deleted transcript.
      await qc.cancelQueries({ queryKey: ["chat", uid, id], exact: true });
      if (id === activeId) {
        setActiveId(null);
        send.reset();
      }
      qc.removeQueries({ queryKey: ["chat", uid, id], exact: true });
      qc.setQueryData<ChatSessionOut[]>(["chats", uid], (rows) =>
        rows?.filter((row) => row.id !== id),
      );
      setDeletedTitle(deleteTarget?.title ?? t("coach.new_chat"));
      setDeleteTarget(null);
      void qc.invalidateQueries({ queryKey: ["chats", uid], exact: true });
      requestAnimationFrame(() => newChatButton.current?.querySelector("button")?.focus());
    },
  });
  useEffect(() => {
    const dialog = deleteDialog.current;
    if (deleteTarget && dialog && !dialog.open) dialog.showModal();
    else if (!deleteTarget && dialog?.open) dialog.close();
  }, [deleteTarget]);
  const conversationUnavailable = active.error instanceof ApiError && active.error.status === 404;
  useEffect(() => {
    if (conversationUnavailable && activeId != null) {
      qc.invalidateQueries({ queryKey: ["chats", uid], exact: true });
    }
  }, [conversationUnavailable, activeId, qc, uid]);
  useEffect(() => {
    if ((active.data?.messages.length ?? 0) > 0 || send.isPending || send.isError) {
      bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [active.data?.messages.length, send.isPending, send.isError]);
  function submit() {
    if (aiAllowed && draft.trim() && !send.isPending && !remove.isPending && !active.isLoading && !active.isError)
      send.mutate({ text: draft.trim(), sessionId: activeId });
  }
  function prepareQuestion() {
    if (!context || !contextReady || send.isPending || remove.isPending) return;
    setDraft(t(context.plannedSessionId === undefined ? "dailyFlow.coach_day_prompt" : "dailyFlow.coach_workout_prompt", {
      date: context.date, id: context.plannedSessionId,
    }));
    setActiveId(null);
    send.reset();
    setReplaceContextKey(null);
    setParams({ tab: "analysis" }, { state: contextState });
    requestAnimationFrame(() => composer.current?.focus());
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("coach.title")}
        subtitle={t("coach.subtitle")}
        actions={
          <div ref={newChatButton}><Button
            variant="ghost"
            icon={<Plus size={16} />}
            disabled={send.isPending || remove.isPending}
            onClick={() => {
              setActiveId(null);
              setParams({ tab: "analysis" }, { state: contextState });
              send.reset();
            }}
          >
            {t("coach.new_chat")}
          </Button></div>
        }
      />
      {context && <Card className="space-y-3 border-l-2 border-l-ink">
        <h2 className="text-[15px] font-medium">{t(context.plannedSessionId === undefined ? "dailyFlow.coach_day_title" : "dailyFlow.coach_workout_title", { date: context.date, id: context.plannedSessionId })}</h2>
        {contextReady && context.plannedSessionId !== undefined && (() => {
          const workout = day.data!.sessions.find(session => session.id === context.plannedSessionId)!;
          return <p className="break-words text-[14px]">{workout.session_type || friendlyDiscipline(workout.discipline, t)}</p>;
        })()}
        <p className="max-w-2xl text-[13px] leading-relaxed text-muted">{t("dailyFlow.coach_context_note")}</p>
        {day.isFetching ? <p role="status" className="text-[13px] text-muted">{t("dailyFlow.coach_context_loading")}</p> : !contextReady && <div className="space-y-2">
          <p role="status" className="text-[13px] text-muted">{t("dailyFlow.coach_context_unavailable")}</p>
          <Button variant="ghost" onClick={() => void day.refetch()}>{t("dailyFlow.coach_context_retry")}</Button>
        </div>}
        {replaceContextKey === contextKey ? <div className="space-y-3">
          <p className="text-[13px]">{t("dailyFlow.replace_question_note")}</p>
          <div className="flex flex-wrap gap-3">
            <Button variant="ghost" onClick={() => setReplaceContextKey(null)}>{t("dailyFlow.keep_question")}</Button>
            <Button disabled={!contextReady || send.isPending || remove.isPending} onClick={prepareQuestion}>{t("dailyFlow.replace_question")}</Button>
          </div>
        </div> : <Button disabled={!contextReady || send.isPending || remove.isPending} onClick={() => {
          if (draft.trim()) setReplaceContextKey(contextKey);
          else prepareQuestion();
        }}>{t("dailyFlow.review_question")}</Button>}
        <div className="flex flex-wrap gap-4 text-[13px]">
          <Link className="text-link inline-flex min-h-11 items-center" to={`/app?date=${context.date}`}>{t("dailyFlow.return_day")}</Link>
          {context.plannedSessionId !== undefined && <Link className="text-link inline-flex min-h-11 items-center" to={`/app/workouts/${context.plannedSessionId}`}>{t("dailyFlow.return_workout")}</Link>}
        </div>
      </Card>}
      {deletedTitle && <p role="status" className="text-[13px] text-muted">
        {t("betaCoach.deleted", { title: deletedTitle })}
      </p>}
      {!aiAllowed && <details className="border border-hairline p-4">
        <summary className="min-h-6 cursor-pointer text-[13px]">{t("athlete.ai_disabled")} · {t("betaCoach.consent_details")}</summary>
        <div className="mt-4"><AiConsentPanel /></div>
      </details>}
      <dialog
        ref={deleteDialog}
        aria-labelledby="delete-conversation-title"
        aria-describedby="delete-conversation-description"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
          const first = buttons[0];
          const last = buttons.at(-1);
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault(); last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault(); first?.focus();
          }
        }}
        onCancel={(event) => {
          event.preventDefault();
          if (!remove.isPending) { setDeleteTarget(null); remove.reset(); }
        }}
        className="m-auto w-[calc(100%_-_2rem)] max-w-md border border-hairline bg-surface p-6 text-ink shadow-xl backdrop:bg-black/50"
      >
        <h2 id="delete-conversation-title" className="text-lg font-medium">{t("betaCoach.confirm_title")}</h2>
        <p id="delete-conversation-description" className="mt-3 break-words text-[14px] leading-relaxed text-muted">
          {t("betaCoach.confirm_body", { title: deleteTarget?.title ?? t("coach.new_chat") })}
        </p>
        {remove.isError && <p role="alert" className="mt-4 text-[13px] text-alertText">{t("betaCoach.delete_failed")}</p>}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button autoFocus disabled={remove.isPending}
            onClick={() => { setDeleteTarget(null); remove.reset(); }}
            className="min-h-11 rounded-control border border-hairline px-4 text-[13px] disabled:opacity-50">
            {t("betaCoach.cancel")}
          </button>
          <Button variant="danger" disabled={remove.isPending || !deleteTarget}
            onClick={() => { if (deleteTarget) remove.mutate(deleteTarget.id); }}>
            {t(remove.isPending ? "betaCoach.deleting" : "betaCoach.delete")}
          </Button>
        </div>
      </dialog>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented
          value={tab}
          onChange={(v) => setParams({ tab: v }, { state: contextState })}
          options={[
            { value: "analysis", label: t("v01Coach.conversation") },
            { value: "changes", label: t("v01Coach.proposals") },
          ]}
        />
        <Link to="/app/training?tab=planning" className="text-link inline-flex min-h-11 items-center gap-2 text-[12px]">
          {t("v01Coach.training")} <ArrowUpRight size={15} aria-hidden="true" />
        </Link>
      </div>
      {tab === "changes" && <p className="-mt-3 max-w-2xl text-[12px] leading-relaxed text-muted">{t("v01Coach.proposal_note")}</p>}
      {tab === "changes" && send.isPending && <PendingReply startedAt={send.submittedAt} />}
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
                        disabled={send.isPending || remove.isPending}
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
                      <details name="coach-conversation-actions" className="relative shrink-0"
                        onToggle={(event) => {
                          const isOpen = event.currentTarget.open;
                          setOpenActionsId((current) => isOpen ? s.id : current === s.id ? null : current);
                        }}>
                        <summary
                          role="button"
                          aria-expanded={openActionsId === s.id}
                          aria-label={t("betaCoach.actions", { title: s.title ?? t("coach.new_chat") })}
                          className="flex min-h-11 min-w-11 cursor-pointer list-none items-center justify-center rounded-control text-muted hover:bg-surface3 focus-visible:outline focus-visible:outline-2 [&::-webkit-details-marker]:hidden"
                        >
                          <MoreHorizontal size={18} aria-hidden="true" />
                        </summary>
                        <button
                          disabled={send.isPending || remove.isPending}
                          onClick={(event) => {
                            const disclosure = event.currentTarget.closest("details");
                            if (disclosure) {
                              disclosure.open = false;
                              disclosure.querySelector("summary")?.focus();
                            }
                            setDeletedTitle(null);
                            remove.reset();
                            setDeleteTarget(s);
                          }}
                          className="absolute right-0 z-10 flex min-h-11 w-52 items-center gap-2 border border-hairline bg-surface px-3 text-left text-[13px] text-alertText shadow-lg disabled:opacity-50"
                        >
                          <Trash2 size={16} aria-hidden="true" />
                          {t("betaCoach.delete")}
                        </button>
                      </details>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-6 border-t border-hairline pt-4 text-[12px] text-muted">
                {t("betaCoach.saved_account")}
              </p>
            </div>
          </aside>
          <Card className="flex h-[min(75dvh,850px)] min-h-[480px] flex-col !p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-6 py-4">
              <span className="min-w-0 break-words text-[13px] font-medium">
                {active.data?.title ?? t("coach.conversation")}
              </span>
              {typeof active.data?.messages.at(-1)?.referenced_data?.model === "string" && (
                <details className="min-w-0 text-[12px] text-muted">
                  <summary className="cursor-pointer">{t("v01Coach.reply_details")}</summary>
                  <p className="mt-2 break-all">{t("v01Coach.model", { name: String(active.data.messages.at(-1)!.referenced_data!.model) })}</p>
                </details>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 md:px-8">
              {active.isLoading ? (
                <Loading />
              ) : active.isError ? (
                <div role="alert">
                  <ErrorNote message={t(conversationUnavailable ? "betaCoach.unavailable" : "betaCoach.load_failed")} />
                  {!conversationUnavailable && <Button variant="ghost" onClick={() => { void active.refetch(); }}>
                    {t("betaCoach.retry")}
                  </Button>}
                </div>
              ) : !active.data?.messages.length && !send.isPending && !send.isError ? (
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
                      {m.role === "assistant" && Array.isArray(m.referenced_data?.drafts) && m.referenced_data.drafts.length > 0 && (() => {
                        const proposals = referencedProposalLinks(m.referenced_data.drafts);
                        return proposals.length ? <div className="mt-3 flex flex-wrap gap-x-4">{proposals.map((proposal, index) => <Link key={proposal.id} to={proposal.href} state={contextState} className="text-link inline-flex min-h-11 items-center gap-2 text-[13px]">{t("dailyFlow.review_proposal", {number:index+1})}<ArrowUpRight size={15} aria-hidden="true" /></Link>)}</div> : <Link to="/app/coach?tab=changes" state={contextState} className="text-link mt-3 inline-flex min-h-11 items-center gap-2 text-[13px]">{t("v01Coach.proposals")} <ArrowUpRight size={15} aria-hidden="true" /></Link>;
                      })()}
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
              {send.isPending && <PendingReply startedAt={send.submittedAt} />}
              {send.isError && send.variables && (
                <div className="mt-6 space-y-3">
                  <ErrorNote message={send.error.message} />
                  <p className="text-[13px] leading-relaxed text-muted">{t("v01Coach.failed_note")}</p>
                  <details className="text-[13px]">
                    <summary className="cursor-pointer text-muted">{t("v01Coach.failed_question")}</summary>
                    <p className="mt-3 whitespace-pre-wrap break-words leading-relaxed">{send.variables.text}</p>
                  </details>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="ghost" disabled={!aiAllowed || remove.isPending || active.isLoading || active.isError}
                      onClick={() => { if (send.variables) send.mutate(send.variables); }}>
                      {t("v01Coach.retry_question")}
                    </Button>
                    <Button variant="ghost" disabled={sessions.isFetching || active.isFetching}
                      onClick={() => {
                        setHistoryOpen(true);
                        void sessions.refetch();
                        if (activeId != null) void active.refetch();
                      }}>
                      {t("v01Coach.refresh_history")}
                    </Button>
                  </div>
                </div>
              )}
              <div ref={bottom} />
            </div>
            <div className="border-t border-hairline p-5">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
                className="flex items-end gap-3"
              >
                <textarea
                  ref={composer}
                  value={draft}
                  disabled={remove.isPending}
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
                    !aiAllowed || !draft.trim() ||
                    send.isPending || remove.isPending ||
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
