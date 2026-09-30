"use client";

/**
 * Apex Health — CoachPage.
 *
 * Route purpose: "What can the system help me understand?"
 * An AI feature grounded in the user's measured data — not a generic chatbot.
 *
 * UX law (mandatory):
 *  - Assistant responses visually distinguish data / recommendation / disclaimer.
 *  - The AI is never louder than the data: no giant "AI INSIGHT" cards.
 *  - Referenced data is rendered as a small grid of metric → value pairs.
 *  - Disclaimers are subdued, italic, alert/40 — the AI defers to clinicians.
 *
 * Layout: desktop = 280px past-conversations sidebar + chat thread.
 * Mobile = horizontal-scroll strip of past conversations above the thread.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Send, Plus, Trash2, Mic, Square, Loader2, Sparkles, Volume2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { chatSessions, getChatSession } from "@/lib/apex/data";
import { timeAgo } from "@/lib/apex/format";
import type { ChatMessage, ChatSession } from "@/lib/apex/types";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useTTS } from "@/hooks/use-tts";
import {
  Card,
  PageHeader,
  Badge,
  ApexButton,
  Eyebrow,
  Empty,
  Loading,
  Hairline,
} from "@/components/apex/kit";
import { useToast } from "@/hooks/use-toast";

/* ----------------------------------------------------------------- id helpers */
let _msgId = 10_000;
function nextMsgId(): number {
  return ++_msgId;
}
let _sessionId = 2_000;
function nextSessionId(): number {
  return ++_sessionId;
}

/* ----------------------------------------------------------------- canned replies */
/**
 * Deterministic canned assistant replies, grounded in the user's mock data.
 * Returns three messages — a `data` interpretation, a `recommendation`,
 * and a `disclaimer` — matching the pattern of the pre-populated sessions.
 */
function generateReply(userMsg: string): ChatMessage[] {
  const text = userMsg.toLowerCase();
  const now = new Date().toISOString();

  let dataContent: string;
  let dataRef: Record<string, unknown>;
  let recContent: string;
  let recRef: Record<string, unknown> | null;

  if (text.includes("recovery")) {
    dataContent =
      "Your HRV is 64 ms, +8% above your 28-day baseline of 59 ms. Resting HR is 48 bpm (−2 bpm vs 7-day mean). Sleep efficiency is 94% over the last 3 nights. Readiness is 84/100.";
    dataRef = { hrv_ms: 64, hrv_baseline_ms: 59, resting_hr: 48, readiness: 84 };
    recContent =
      "Parasympathetic recovery is strong — a quality session is appropriate today. Aim for threshold-style work (e.g. 4×8 min at FTP) and avoid back-to-back high-load days to keep ACWR inside the optimal band.";
    recRef = { acwr: 1.09 };
  } else if (text.includes("training") || text.includes("train") || text.includes("load")) {
    dataContent =
      "Your ACWR is 1.09 — inside the optimal training window but at the upper edge. Acute load is 312, chronic load 286, training load over 7 days is 418. The last high-intensity session was 2 days ago.";
    dataRef = { acwr: 1.09, acute_load: 312, chronic_load: 286, training_load_7d: 418 };
    recContent =
      "Sustain the current pattern but cap today's session at threshold intensity. Include a full recovery day tomorrow to pull ACWR back toward 1.0 before adding new load.";
    recRef = null;
  } else if (text.includes("sleep")) {
    dataContent =
      "Bedtime variance dropped from 47 to 18 minutes over the last 14 days. Sleep score averages 85, up from 78 in the prior fortnight. Deep sleep averages 1.5h, REM 1.8h — both within healthy ranges.";
    dataRef = { sleep_score_avg: 85, bedtime_variance_min: 18, deep_s_h: 1.5, rem_s_h: 1.8 };
    recContent =
      "Maintain the current sleep window — the consistency, more than the absolute hours, is what is driving the score improvement. Avoid shifting wake time on weekends by more than 30 minutes.";
    recRef = null;
  } else if (text.includes("hrv")) {
    dataContent =
      "HRV dropped to 56 ms yesterday, −8 ms vs your 28-day baseline of 64 ms. The drop follows a high-load training day (load 418) and 23 minutes less deep sleep than your 14-day average.";
    dataRef = { hrv_ms: 56, hrv_baseline_ms: 64, training_load: 418, deep_sleep_delta_min: -23 };
    recContent =
      "Plan a low-intensity recovery day. HRV typically returns to baseline within 24–48h after a single perturbation, provided sleep and hydration are normal. Re-check tomorrow morning before resuming hard work.";
    recRef = null;
  } else {
    // Default — generic, references the user's headline metrics.
    dataContent =
      "I see your readiness is 84/100, HRV is 64 ms (+8% vs baseline 59 ms), and resting HR is 48 bpm. ACWR is 1.09, sleep efficiency 94%. These signals support a quality training day, with recovery still in a strong band.";
    dataRef = {
      readiness: 84,
      hrv_ms: 64,
      hrv_baseline_ms: 59,
      resting_hr: 48,
      acwr: 1.09,
      sleep_efficiency_pct: 94,
    };
    recContent =
      "Consider a threshold session today and a recovery day tomorrow to keep ACWR near 1.0. If subjective fatigue is elevated despite the objective markers, prioritise sleep over the session.";
    recRef = null;
  }

  const disclaimerContent =
    "This is an interpretation of measured data, not medical advice. Stop and consult a clinician if you experience chest pain, unusual shortness of breath, or persistent fatigue.";

  return [
    {
      id: nextMsgId(),
      role: "assistant",
      content: dataContent,
      referenced_data: dataRef,
      created_at: now,
      kind: "data",
    },
    {
      id: nextMsgId(),
      role: "assistant",
      content: recContent,
      referenced_data: recRef,
      created_at: now,
      kind: "recommendation",
    },
    {
      id: nextMsgId(),
      role: "assistant",
      content: disclaimerContent,
      referenced_data: null,
      created_at: now,
      kind: "disclaimer",
    },
  ];
}

/* ----------------------------------------------------------------- pure presentational bits */
function ApexMonogram({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="6" className="fill-primarySoft" />
      <path d="M16 7 L25 25 L20 25 L16 16 L12 25 L7 25 Z" className="fill-primaryText" />
    </svg>
  );
}

function KindBadge({
  kind,
  t,
}: {
  kind: ChatMessage["kind"];
  t: (p: string) => string;
}) {
  if (kind === "data") return <Badge tone="neutral">{t("coach.reply_data")}</Badge>;
  if (kind === "recommendation")
    return <Badge tone="primary">{t("coach.reply_recommendation")}</Badge>;
  return (
    <Badge tone="alert" className="opacity-70">
      {t("coach.reply_disclaimer")}
    </Badge>
  );
}

function ReferencedDataGrid({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (!entries.length) return null;
  return (
    <div className="mt-2 rounded-[var(--radius-control)] border border-hairline bg-surface2/60 p-2">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-2">
            <span className="num text-[10px] uppercase tracking-[0.06em] text-faint">{k}</span>
            <span className="num text-[11px] font-semibold text-ink2">{String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssistantMessage({
  msg,
  t,
  locale,
  tts,
}: {
  msg: ChatMessage;
  t: (p: string) => string;
  locale: "en" | "it";
  tts: ReturnType<typeof useTTS>;
}) {
  const isDisclaimer = msg.kind === "disclaimer";
  // Streaming indicator: empty content means the message is currently being streamed.
  const isStreaming = !msg.content;
  const canSpeak = !isStreaming && !!msg.content && !isDisclaimer;
  const isThisPlaying = tts.isPlaying && tts.activeText === msg.content;
  const isThisLoading = tts.isLoading && tts.activeText === msg.content;
  return (
    <div className="flex items-start gap-2.5">
      <div className="mt-0.5 shrink-0">
        <ApexMonogram size={22} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <KindBadge kind={msg.kind} t={t} />
          {isStreaming && (
            <span className="num flex items-center gap-1 text-[10px] text-primaryText">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
              </span>
              typing…
            </span>
          )}
          {!isStreaming && (
            <span className="mono text-[10px] text-faint">{timeAgo(msg.created_at, locale)}</span>
          )}
          {/* Speaker button — read this message aloud via TTS */}
          {canSpeak && (
            <button
              type="button"
              onClick={() => {
                if (isThisPlaying) {
                  tts.stop();
                } else {
                  tts.speak(msg.content);
                }
              }}
              className={`flex h-5 w-5 items-center justify-center rounded-[var(--radius-control)] text-muted transition-colors hover:bg-surface2 hover:text-ink ${
                isThisPlaying || isThisLoading ? "text-primaryText" : ""
              }`}
              aria-label={isThisPlaying ? "Stop audio" : "Read aloud"}
              title={isThisPlaying ? "Stop audio" : isThisLoading ? "Loading audio…" : "Read aloud"}
            >
              {isThisLoading ? (
                <Loader2 size={11} className="animate-spin" />
              ) : isThisPlaying ? (
                <Square size={9} fill="currentColor" />
              ) : (
                <Volume2 size={11} />
              )}
            </button>
          )}
        </div>
        <div className="rounded-[var(--radius-card)] border border-hairline bg-surface px-3 py-2">
          <div
            className={`whitespace-pre-wrap text-[13px] leading-[20px] ${
              isDisclaimer ? "italic text-alertText/40" : "text-ink2"
            } ${isThisPlaying ? "border-l-2 border-primary pl-2 -ml-2" : ""}`}
          >
            {msg.content}
            {isStreaming && (
              <span
                className="ml-0.5 inline-block h-[14px] w-[7px] translate-y-[2px] animate-pulse bg-primary"
                aria-hidden
              />
            )}
          </div>
          {msg.referenced_data && <ReferencedDataGrid data={msg.referenced_data} />}
        </div>
      </div>
    </div>
  );
}

function UserMessage({ msg, locale }: { msg: ChatMessage; locale: "en" | "it" }) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-[80%] flex-col items-end gap-1">
        <div className="rounded-[var(--radius-card)] border border-hairline bg-primarySoft/30 px-3 py-2 text-ink">
          <div className="whitespace-pre-wrap text-[13px] leading-[20px]">{msg.content}</div>
        </div>
        <span className="mono pr-1 text-[10px] text-faint">{timeAgo(msg.created_at, locale)}</span>
      </div>
    </div>
  );
}

function SuggestionChips({
  t,
  onPick,
}: {
  t: (p: string) => string;
  onPick: (s: string) => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <Eyebrow>{t("coach.new_session_label")}</Eyebrow>
      <div className="max-w-md text-[12px] text-muted">{t("coach.placeholder")}</div>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {[1, 2, 3, 4].map((i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPick(t(`coach.suggestion_${i}`))}
            className="num rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-1.5 text-[12px] text-ink2 transition-colors hover:border-hairline2 hover:bg-surface3"
          >
            {t(`coach.suggestion_${i}`)}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- main component */
export function CoachPage() {
  const t = useT();
  const ui = useApexUi();
  const { toast } = useToast();
  const locale = ui.locale;

  // Pre-load all mock sessions' messages into a single map keyed by id.
  const [messagesMap, setMessagesMap] = useState<Record<number, ChatMessage[]>>(() => {
    const m: Record<number, ChatMessage[]> = {};
    for (const s of chatSessions) m[s.id] = getChatSession(s.id).messages;
    return m;
  });

  // Local copy of the session list — new conversations prepend to it.
  const [localSessions, setLocalSessions] = useState<ChatSession[]>(() => [...chatSessions]);

  // Currently selected chat id. null = brand-new conversation (no messages yet).
  const initialId = ui.selectedChatId ?? chatSessions[0].id;
  const [currentId, setCurrentId] = useState<number | null>(initialId);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const voice = useVoiceInput();
  const tts = useTTS({
    voice: ui.ttsVoice,
    autoPlayText: ui.ttsAutoPlay ? () => true : undefined,
  });
  const [useAiBackend, setUseAiBackend] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const loadingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentSession = useMemo(
    () => (currentId === null ? null : localSessions.find((s) => s.id === currentId) ?? null),
    [currentId, localSessions]
  );
  const messages = currentId === null ? [] : messagesMap[currentId] ?? [];

  /* ----- auto-scroll to bottom when messages change or loading toggles */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, loading, currentId]);

  /* ----- voice transcript listener: append transcript to input + focus */
  useEffect(() => {
    const onTranscript = (e: Event) => {
      const text = (e as CustomEvent<string>).detail ?? "";
      setInput((cur) => {
        const next = cur.trim();
        return next ? `${next} ${text}` : text;
      });
      setTimeout(() => taRef.current?.focus(), 50);
    };
    window.addEventListener("apex-voice-transcript", onTranscript);
    return () => window.removeEventListener("apex-voice-transcript", onTranscript);
  }, []);

  /* ----- auto-grow textarea up to 4 rows */
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const maxH = 96; // ~4 rows
    ta.style.height = `${Math.min(ta.scrollHeight, maxH)}px`;
  }, [input]);

  /* ----- cleanup pending timer on unmount */
  useEffect(() => {
    return () => {
      if (loadingTimer.current) clearTimeout(loadingTimer.current);
    };
  }, []);

  /* ----- handlers */
  function startNew() {
    if (loadingTimer.current) clearTimeout(loadingTimer.current);
    setLoading(false);
    setCurrentId(null);
    setInput("");
    ui.selectChat(null);
    // Focus the textarea on the next paint.
    requestAnimationFrame(() => taRef.current?.focus());
  }

  function selectSession(id: number) {
    if (id === currentId) return;
    if (loadingTimer.current) clearTimeout(loadingTimer.current);
    setLoading(false);
    setCurrentId(id);
    setInput("");
    ui.selectChat(id);
  }

  function updateSession(id: number, updater: (s: ChatSession) => ChatSession) {
    setLocalSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }

  function appendMessages(id: number, msgs: ChatMessage[]) {
    setMessagesMap((prev) => ({
      ...prev,
      [id]: [...(prev[id] ?? []), ...msgs],
    }));
  }

  /** Replace a specific message (by id) — used for streaming. */
  function replaceMessage(id: number, msgId: number, updater: (m: ChatMessage) => ChatMessage) {
    setMessagesMap((prev) => ({
      ...prev,
      [id]: (prev[id] ?? []).map((m) => (m.id === msgId ? updater(m) : m)),
    }));
  }

  /**
   * Stream the assistant reply word-by-word into the chat thread.
   * Each reply is 3 messages (data / recommendation / disclaimer). We stream
   * the data message word-by-word; the recommendation + disclaimer appear all
   * at once after the data stream completes (they're typically shorter and
   * benefit less from streaming).
   *
   * Cancellable: returns a cleanup function that clears the timer.
   */
  function streamReply(id: number, userMsg: string): () => void {
    const reply = generateReply(userMsg);
    const nowIso = new Date().toISOString();
    const dataMsg = reply[0];
    const rest = reply.slice(1);

    // Words to stream in the data message
    const words = dataMsg.content.split(/(\s+)/); // keep whitespace tokens
    let wordIdx = 0;

    // Initial empty data message — will be progressively filled.
    const streamingMsg: ChatMessage = {
      ...dataMsg,
      content: "",
    };
    appendMessages(id, [streamingMsg]);

    const tick = () => {
      wordIdx += 1;
      const partial = words.slice(0, wordIdx).join("");
      const streamingId = streamingMsg.id;
      replaceMessage(id, streamingId, (m) => ({ ...m, content: partial }));

      if (wordIdx < words.length) {
        // Variable delay: faster for whitespace tokens, slower for word boundaries
        const lastToken = words[wordIdx - 1] ?? "";
        const delay = /^\s+$/.test(lastToken) ? 20 : 45 + Math.random() * 35;
        loadingTimer.current = setTimeout(tick, delay);
      } else {
        // Stream complete — append the recommendation + disclaimer.
        appendMessages(id, rest);
        updateSession(id, (s) => ({
          ...s,
          message_count: s.message_count + reply.length,
          last_activity_at: nowIso,
          preview: dataMsg.content,
        }));
        setLoading(false);
        loadingTimer.current = null;
        // Auto-play TTS if user enabled it in Settings.
        if (dataMsg.content) {
          tts.maybeAutoPlay(dataMsg.content);
        }
      }
    };

    // Brief "thinking" pause before streaming starts
    loadingTimer.current = setTimeout(tick, 450);
    return () => {
      if (loadingTimer.current) {
        clearTimeout(loadingTimer.current);
        loadingTimer.current = null;
      }
    };
  }

  /**
   * Real-LLM streaming: calls /api/coach with the full conversation history,
   * parses the SSE stream, and progressively fills the assistant message.
   * Falls back to canned streamReply() if the backend fails or is unreachable.
   */
  async function streamReplyLLM(id: number, userMsg: string, currentMessages: ChatMessage[]): Promise<void> {
    const nowIso = new Date().toISOString();

    // Build the message history for the LLM (only user/assistant, skip kind badges)
    const history = currentMessages
      .filter((m) => m.role === "user" || (m.role === "assistant" && m.content))
      .map((m) => ({ role: m.role, content: m.content }));

    // Placeholder assistant message — streamed into place
    const streamingMsg: ChatMessage = {
      id: nextMsgId(),
      role: "assistant",
      content: "",
      referenced_data: null,
      created_at: nowIso,
      kind: "data",
    };
    appendMessages(id, [streamingMsg]);

    try {
      const resp = await fetch("/api/coach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history, locale: ui.locale }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let acc = "";

      // Read chunks until done
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse complete SSE events (separated by \n\n)
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? ""; // keep the last (possibly partial) chunk

        for (const evt of events) {
          const line = evt.trim();
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6);
          try {
            const parsed = JSON.parse(json);
            if (parsed.type === "token") {
              acc += parsed.text;
              replaceMessage(id, streamingMsg.id, (m) => ({ ...m, content: acc }));
            } else if (parsed.type === "done") {
              // Append a recommendation + disclaimer wrap-up so the kind-badged
              // structure matches the canned path.
              const rest: ChatMessage[] = [
                {
                  id: nextMsgId(),
                  role: "assistant",
                  content: "",
                  referenced_data: null,
                  created_at: nowIso,
                  kind: "recommendation",
                },
                {
                  id: nextMsgId(),
                  role: "assistant",
                  content: "This is an interpretation of measured data, not medical advice.",
                  referenced_data: null,
                  created_at: nowIso,
                  kind: "disclaimer",
                },
              ];
              appendMessages(id, rest);
              updateSession(id, (s) => ({
                ...s,
                message_count: s.message_count + 3,
                last_activity_at: nowIso,
                preview: acc.slice(0, 80),
              }));
              setLoading(false);
              // Auto-play TTS if user enabled it in Settings.
              if (acc) {
                tts.maybeAutoPlay(acc);
              }
              return;
            } else if (parsed.type === "error") {
              throw new Error(parsed.error || "LLM error");
            }
          } catch {
            /* ignore malformed JSON chunks */
          }
        }
      }
      // Stream ended without explicit "done"
      throw new Error("Stream ended prematurely");
    } catch (err) {
      // Fallback: append the error message + canned reply
      const errMsg = err instanceof Error ? err.message : "Unknown LLM error";
      replaceMessage(id, streamingMsg.id, (m) => ({
        ...m,
        content: `[LLM backend unavailable — falling back to local canned reply]\n\nError: ${errMsg}`,
      }));
      // Then proceed with canned reply
      streamReply(id, userMsg);
    }
  }

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMsg: ChatMessage = {
      id: nextMsgId(),
      role: "user",
      content: trimmed,
      referenced_data: null,
      created_at: new Date().toISOString(),
      kind: "data", // user msgs carry a kind for type compliance; not displayed.
    };

    setInput("");

    if (currentId === null) {
      /* ----- new conversation: mint a local session and prepend */
      const id = nextSessionId();
      const title = trimmed.length > 40 ? trimmed.slice(0, 40) + "…" : trimmed;
      const newSession: ChatSession = {
        id,
        title,
        started_at: userMsg.created_at,
        last_activity_at: userMsg.created_at,
        message_count: 1,
        preview: trimmed,
      };
      setLocalSessions((prev) => [newSession, ...prev]);
      setMessagesMap((prev) => ({ ...prev, [id]: [userMsg] }));
      setCurrentId(id);
      ui.selectChat(id);

      // Stream the assistant reply word-by-word (typewriter effect).
      setLoading(true);
      if (useAiBackend) {
        // Fire-and-forget the async LLM call
        streamReplyLLM(id, trimmed, [userMsg]);
      } else {
        streamReply(id, trimmed);
      }
    } else {
      /* ----- continuing existing conversation */
      const id = currentId;
      appendMessages(id, [userMsg]);
      updateSession(id, (s) => ({
        ...s,
        message_count: s.message_count + 1,
        last_activity_at: userMsg.created_at,
        preview: trimmed,
      }));

      // Stream the assistant reply word-by-word (typewriter effect).
      setLoading(true);
      const currentMessages = (messagesMap[id] ?? []).concat(userMsg);
      if (useAiBackend) {
        streamReplyLLM(id, trimmed, currentMessages);
      } else {
        streamReply(id, trimmed);
      }
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleDelete() {
    if (loadingTimer.current) clearTimeout(loadingTimer.current);
    setLoading(false);
    toast({
      title: t("coach.delete"),
      description: currentSession?.title ?? t("coach.new_session_label"),
    });
    // Cosmetic only — does not actually remove the conversation.
  }

  function pickSuggestion(s: string) {
    setInput(s);
    requestAnimationFrame(() => {
      taRef.current?.focus();
      // Move caret to end.
      const len = s.length;
      taRef.current?.setSelectionRange(len, len);
    });
  }

  const canSend = input.trim().length > 0 && !loading;

  /* ----- session list item (desktop) */
  const SessionListItem = ({ s }: { s: ChatSession }) => {
    const selected = s.id === currentId;
    return (
      <button
        type="button"
        onClick={() => selectSession(s.id)}
        className={`flex w-full flex-col gap-1 rounded-[var(--radius-card)] border p-2 text-left transition-colors ${
          selected
            ? "border-primary/40 bg-surface2"
            : "border-transparent hover:bg-surface2/60"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="truncate text-[13px] font-semibold text-ink">
            {s.title ?? t("coach.new_session_label")}
          </div>
          <Badge tone="neutral" className="shrink-0">
            {s.message_count}
          </Badge>
        </div>
        <div className="line-clamp-2 text-[11px] leading-[15px] text-muted">{s.preview}</div>
        <div className="mono text-[10px] text-faint">{timeAgo(s.last_activity_at, locale)}</div>
      </button>
    );
  };

  /* ----- session chip (mobile horizontal strip) */
  const SessionChip = ({ s }: { s: ChatSession }) => {
    const selected = s.id === currentId;
    return (
      <button
        type="button"
        onClick={() => selectSession(s.id)}
        className={`flex w-[200px] shrink-0 flex-col gap-1 rounded-[var(--radius-card)] border p-2 text-left transition-colors ${
          selected ? "border-primary/40 bg-surface2" : "border-hairline bg-surface"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="truncate text-[12px] font-semibold text-ink">
            {s.title ?? t("coach.new_session_label")}
          </div>
          <Badge tone="neutral" className="shrink-0">
            {s.message_count}
          </Badge>
        </div>
        <div className="line-clamp-2 text-[10px] leading-[14px] text-muted">{s.preview}</div>
        <div className="mono text-[10px] text-faint">{timeAgo(s.last_activity_at, locale)}</div>
      </button>
    );
  };

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader title={t("coach.title")} />

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        {/* ----------------------------------------------------------- left column */}
        <aside className="hidden lg:flex flex-col gap-3">
          <Card pad={false} className="flex flex-col p-3">
            <Eyebrow>{t("coach.past_chats")}</Eyebrow>
            <ApexButton
              variant="primary"
              size="md"
              className="mt-2 w-full"
              icon={<Plus size={14} strokeWidth={2.5} />}
              onClick={startNew}
            >
              {t("coach.new_chat")}
            </ApexButton>
            <Hairline className="my-2" />
            {/* AI backend toggle */}
            <label className="flex items-center justify-between gap-2 rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2.5 py-1.5 cursor-pointer transition-colors hover:bg-surface3">
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-ink2">
                <Sparkles size={11} className="text-primaryText" />
                Live LLM
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={useAiBackend}
                onClick={() => setUseAiBackend((v) => !v)}
                className={`relative h-4 w-7 rounded-full transition-colors ${useAiBackend ? "bg-primary" : "bg-surface3"}`}
                aria-label="Toggle live LLM backend"
              >
                <span
                  className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform ${
                    useAiBackend ? "translate-x-3.5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </label>
            <p className="num mt-1 px-1 text-[10px] text-faint">
              {useAiBackend
                ? "Real LLM (z-ai-web-dev-sdk) with SSE streaming."
                : "Canned deterministic replies."}
            </p>
            <Hairline className="my-2" />
            {localSessions.length === 0 ? (
              <Empty title={t("coach.empty_chats")} />
            ) : (
              <div className="flex flex-col gap-1.5">
                {localSessions.map((s) => (
                  <SessionListItem key={s.id} s={s} />
                ))}
              </div>
            )}
          </Card>
        </aside>

        {/* ----------------------------------------------------------- right column */}
        <section className="flex flex-col gap-3">
          {/* Mobile: horizontal strip of past conversations */}
          <Card pad={false} className="flex flex-col p-3 lg:hidden">
            <div className="mb-2 flex items-center justify-between gap-2">
              <Eyebrow>{t("coach.past_chats")}</Eyebrow>
              <ApexButton
                variant="primary"
                size="sm"
                icon={<Plus size={12} strokeWidth={2.5} />}
                onClick={startNew}
              >
                {t("coach.new_chat")}
              </ApexButton>
            </div>
            {localSessions.length === 0 ? (
              <Empty title={t("coach.empty_chats")} />
            ) : (
              <div className="scroll-area -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
                {localSessions.map((s) => (
                  <SessionChip key={s.id} s={s} />
                ))}
              </div>
            )}
          </Card>

          {/* Chat thread */}
          <Card pad={false} className="flex flex-col">
            <div className="flex items-start justify-between gap-3 p-3">
              <div className="min-w-0">
                <Eyebrow>
                  {currentId === null ? t("coach.new_session_label") : t("coach.past_chats")}
                </Eyebrow>
                <div className="mt-0.5 truncate text-[15px] font-semibold text-ink">
                  {currentSession?.title ?? t("coach.new_session_label")}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ApexButton
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 size={12} strokeWidth={2.25} />}
                  onClick={handleDelete}
                >
                  {t("coach.delete")}
                </ApexButton>
              </div>
            </div>
            <Hairline />

            {/* Messages scroll area */}
            <div
              ref={scrollRef}
              className="scroll-area flex max-h-[calc(100vh-260px)] min-h-[280px] flex-col gap-3 overflow-y-auto p-4"
            >
              {messages.length === 0 && currentId === null ? (
                <SuggestionChips t={t} onPick={pickSuggestion} />
              ) : messages.length === 0 ? (
                <Empty title={t("coach.empty_chats")} />
              ) : (
                <>
                  {messages.map((m) =>
                    m.role === "user" ? (
                      <UserMessage key={m.id} msg={m} locale={locale} />
                    ) : (
                      <AssistantMessage key={m.id} msg={m} t={t} locale={locale} tts={tts} />
                    )
                  )}
                  {loading && (
                    <div className="flex items-start gap-2.5">
                      <div className="mt-0.5 shrink-0">
                        <ApexMonogram size={22} />
                      </div>
                      <div className="flex-1">
                        <Loading label={t("coach.loading")} />
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <Hairline />

            {/* Input row */}
            <div className="p-3">
              <div className="flex items-end gap-2">
                {/* Voice input button */}
                <button
                  type="button"
                  onClick={() => {
                    if (voice.isRecording) {
                      voice.stopRecording();
                    } else if (voice.isTranscribing) {
                      /* noop — wait */
                    } else {
                      voice.startRecording();
                    }
                  }}
                  disabled={loading}
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] border transition-colors ${
                    voice.isRecording
                      ? "border-alert/40 bg-alertSoft text-alertText animate-pulse"
                      : voice.isTranscribing
                      ? "border-primary/40 bg-primarySoft text-primaryText"
                      : "border-hairline bg-surface2 text-muted hover:bg-surface3 hover:text-ink"
                  }`}
                  aria-label={voice.isRecording ? "Stop recording" : voice.isTranscribing ? "Transcribing…" : "Voice input"}
                  title={voice.isRecording ? "Stop recording" : voice.isTranscribing ? "Transcribing…" : "Voice input"}
                >
                  {voice.isRecording ? (
                    <Square size={13} fill="currentColor" />
                  ) : voice.isTranscribing ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Mic size={14} />
                  )}
                </button>
                <textarea
                  ref={taRef}
                  value={input}
                  rows={1}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    voice.isRecording
                      ? "Listening…"
                      : voice.isTranscribing
                      ? "Transcribing…"
                      : t("coach.placeholder")
                  }
                  className={`num w-full resize-none rounded-[var(--radius-control)] border bg-surface px-3 py-2 text-[13px] leading-[20px] text-ink transition-colors placeholder:text-faint focus:outline-none ${
                    voice.isRecording
                      ? "border-alert/60"
                      : "border-hairline focus:border-primary/60"
                  }`}
                />
                <ApexButton
                  variant="primary"
                  size="md"
                  icon={<Send size={14} strokeWidth={2.25} />}
                  onClick={handleSend}
                  disabled={!canSend || voice.isRecording || voice.isTranscribing}
                >
                  {t("coach.send")}
                </ApexButton>
              </div>
              {/* Voice state hint */}
              {voice.state === "error" && voice.error && (
                <div className="mt-2 text-[11px] text-alertText">{voice.error}</div>
              )}
              {voice.isRecording && (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-alert opacity-60" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-alert" />
                  </span>
                  Recording — click stop when done
                </div>
              )}
            </div>
          </Card>

          {/* AI warning footer */}
          <p className="px-1 text-[11px] italic leading-[16px] text-alertText/40">
            {t("coach.ai_warning")}
          </p>
        </section>
      </div>
    </div>
  );
}
