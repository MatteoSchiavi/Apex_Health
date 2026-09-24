/**
 * AI Coach chat — resumable conversations (owner ask).
 *
 * Server side: every turn persists to ai_chat_sessions/ai_chat_messages;
 * the sidebar lists past sessions from GET /coach/chats and a click resumes
 * it (GET /coach/chats/{id}). Local side: the ACTIVE transcript + draft are
 * mirrored into localStorage (apex.chat.*) so a reload mid-conversation
 * never loses context, and the draft survives.
 */

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Send, Trash2 } from "lucide-react";
import {
  api,
  type ChatMessageOut,
  type ChatSessionDetail,
  type ChatSessionOut,
} from "../../app/api";
import { Badge, Button, Card, ErrorNote, Loading, PageHeader } from "../../components/kit";

const LS_ACTIVE = "apex.chat.activeId";
const LS_DRAFT = "apex.chat.draft";

function loadDraft(): string {
  try {
    return localStorage.getItem(LS_DRAFT) ?? "";
  } catch {
    return "";
  }
}

export default function CoachPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(() => {
    const v = Number(localStorage.getItem(LS_ACTIVE));
    return Number.isFinite(v) && v > 0 ? v : null;
  });
  const [draft, setDraft] = useState(loadDraft);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const sessions = useQuery({
    queryKey: ["chats"],
    queryFn: () => api.get<ChatSessionOut[]>("/coach/chats"),
  });
  const active = useQuery({
    queryKey: ["chat", activeId],
    queryFn: () => api.get<ChatSessionDetail>(`/coach/chats/${activeId}`),
    enabled: activeId !== null,
  });

  useEffect(() => {
    try {
      if (activeId === null) localStorage.removeItem(LS_ACTIVE);
      else localStorage.setItem(LS_ACTIVE, String(activeId));
    } catch { /* ignore */ }
  }, [activeId]);
  useEffect(() => {
    try {
      localStorage.setItem(LS_DRAFT, draft);
    } catch { /* ignore */ }
  }, [draft]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active.data?.messages.length, sending]);

  const send = useMutation({
    mutationFn: (text: string) =>
      api.post<ChatSessionDetail>("/coach/chats", {
        text,
        session_id: activeId,
      }),
    onMutate: () => {
      setSending(true);
      setDraft("");
    },
    onSettled: () => setSending(false),
    onSuccess: (data) => {
      setActiveId(data.id);
      qc.invalidateQueries({ queryKey: ["chats"] });
      qc.setQueryData(["chat", data.id], data);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/coach/chats/${id}`),
    onSuccess: (_d, id) => {
      if (id === activeId) setActiveId(null);
      qc.invalidateQueries({ queryKey: ["chats"] });
    },
  });

  const messages: ChatMessageOut[] = active.data?.messages ?? [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("coach.title")} subtitle={t("coach.subtitle")} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[260px_1fr]">
      {/* session list */}
      <Card className="h-fit">
        <div className="mb-3 flex items-center justify-between">
          <div className="eyebrow">{t("coach.past_chats")}</div>
          <button
            type="button"
            onClick={() => setActiveId(null)}
            className="flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-control border border-hairline px-2 text-[12px] font-medium text-ink2 hover:bg-surface3"
          >
            <Plus size={12} /> {t("coach.new_chat")}
          </button>
        </div>
        {sessions.isLoading ? (
          <Loading />
        ) : !sessions.data || sessions.data.length === 0 ? (
          <p className="text-[12px] text-faint">{t("coach.no_chats")}</p>
        ) : (
          <div className="flex max-h-[60vh] flex-col gap-1 overflow-y-auto">
            {sessions.data.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-control px-2 py-1.5 transition-colors ${
                  s.id === activeId ? "bg-surface3" : "hover:bg-surface2"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveId(s.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="truncate text-[12px] font-medium text-ink2">
                    {s.title ?? t("coach.new_chat")}
                  </div>
                  <div className="num text-[10px] text-faint">
                    {new Date(s.last_activity_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                    })}{" "}
                    · {s.message_count} msg
                  </div>
                </button>
                <button
                  type="button"
                  aria-label={t("training.delete")}
                  onClick={() => {
                    if (confirm(t("coach.delete_confirm"))) remove.mutate(s.id);
                  }}
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <Trash2 size={13} className="text-faint hover:text-alertText" />
                </button>
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 border-t border-hairline pt-2 text-[10px] leading-snug text-faint">
          {t("coach.saved_locally")}
        </p>
      </Card>

      {/* conversation */}
      <Card className="flex min-h-[70vh] flex-col !p-0">
        <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
          <div className="eyebrow">{t("coach.conversation")}</div>
          {messages.at(-1)?.model_tier && (
            <Badge tone="primary">{messages.at(-1)!.model_tier}</Badge>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !sending ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <div className="text-[15px] font-semibold text-ink">{t("coach.empty_title")}</div>
              <div className="max-w-sm text-[12px] text-muted">{t("coach.empty_body")}</div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] whitespace-pre-wrap rounded-card px-3.5 py-2.5 text-[13px] leading-relaxed ${
                      m.role === "user"
                        ? "bg-primarySoft text-ink"
                        : "border border-hairline bg-surface2 text-ink2"
                    }`}
                  >
                    {m.content}
                    {m.model_tier === "medical" && m.role === "assistant" && (
                      <div className="mt-2 border-t border-hairline pt-2 text-[11px] text-warningText">
                        {t("coach.medical_disclaimer")}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {sending && (
            <div className="mt-3 flex items-center gap-2 text-[12px] text-muted">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-hairline2 border-t-primary" />
              {t("coach.thinking")}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-hairline p-3">
          {active.isError && <ErrorNote />}
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("coach.placeholder")}
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (draft.trim() && !send.isPending) send.mutate(draft.trim());
                }
              }}
              className="max-h-40 flex-1 resize-none rounded-control border border-hairline bg-surface2 px-3 py-2 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
            />
            <Button
              onClick={() => draft.trim() && send.mutate(draft.trim())}
              disabled={!draft.trim() || sending}
              icon={<Send size={14} />}
            >
              <span className="hidden sm:inline">{t("coach.send")}</span>
            </Button>
          </div>
        </div>
      </Card>
      </div>
    </div>
  );
}
