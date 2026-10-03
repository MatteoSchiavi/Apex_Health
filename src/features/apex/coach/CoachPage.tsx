"use client";

/**
 * Apex Health — CoachPage (plan §1 full redesign).
 *
 * Route purpose: "Ask a question, get an answer you can check, and act on what
 * the coach proposes."
 *
 * Layout:
 *   2xl: 3 columns — [sessions rail 260px | conversation | context panel]
 *   xl:  2 columns — [sessions rail 260px | conversation]  (context panel as drawer)
 *   below: 1 column — conversation first, sessions + context open as sheets
 *
 * Phase 0 fixes (plan §1 verified problems):
 *   1. Optimistic user message — appears instantly, marked "sending…", flips
 *      to "Not sent · retry" + restored composer text on failure.
 *   2. Draft cards rendered (Confirm / Discard, then resolved state).
 *   3. Assistant replies rendered as Markdown (kit's Markdown primitive).
 *   4. "Based on" chips from referenced_data.tool_calls, each linking into app.
 *   5. "The coach is working…" row while waiting (not a bare spinner).
 *   6. Mobile order: conversation is the first grid child.
 *   7. Suggested prompts built from real data: open alert → "Explain my {alert}";
 *      event in 14 d → "Plan this week around {event}"; gear > 80% → service chip;
 *      plus two evergreen. Generic empty state replaced.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clock,
  Copy,
  CornerUpLeft,
  History,
  Info,
  Plus,
  RotateCw,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi, me } from "@/lib/apex";
import { timeAgo, fmtClock, fmtDate } from "@/lib/apex/format";
import {
  ApexButton,
  Badge,
  Card,
  ConfirmPopover,
  Empty,
  Hairline,
  Loading,
  Markdown,
  PageHeader,
} from "@/components/apex/kit";
import { useToast } from "@/hooks/use-toast";
import type { CoachDraft, CoachEvidence, Overview } from "@/lib/apex/types";
import type { ChatMessageRow, ChatSessionRow, ContextDocRow } from "@/lib/apex/coachTypes";
import { getUserItem, setUserItem } from "@/lib/apex/storage";

/* ------------------------------------------------------------------ helpers */

const SORTED_DOC_KINDS = ["profile", "goals", "injuries", "equipment", "preferences", "season_plan"] as const;
type DocKind = (typeof SORTED_DOC_KINDS)[number];

function groupSessions(rows: ChatSessionRow[]): { label: string; rows: ChatSessionRow[] }[] {
  const now = Date.now();
  const DAY = 86_400_000;
  const today: ChatSessionRow[] = [];
  const seven: ChatSessionRow[] = [];
  const earlier: ChatSessionRow[] = [];
  for (const s of rows) {
    const t = new Date(s.last_activity_at).getTime();
    const age = now - t;
    if (age < DAY) today.push(s);
    else if (age < 7 * DAY) seven.push(s);
    else earlier.push(s);
  }
  const out: { label: string; rows: ChatSessionRow[] }[] = [];
  if (today.length) out.push({ label: "coach_today", rows: today });
  if (seven.length) out.push({ label: "coach_7d", rows: seven });
  if (earlier.length) out.push({ label: "coach_earlier", rows: earlier });
  return out;
}

function dayCountdown(iso: string): number {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return Infinity;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(iso);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/** Generate next stable temp id for optimistic user messages. */
let _tempId = -1;
function nextTempId(): number {
  return _tempId--;
}

/* --------------------------------------------------------------- evidence chips */

const TOOL_LABELS: Record<string, string> = {
  get_metric_trend: "HRV trend",
  get_sleep_night: "Sleep",
  get_acwr: "Load / ACWR",
  get_overview: "Overview",
  list_activities: "Activities",
};

const TOOL_VIEW: Record<string, { view: "biometrics" | "sleep" | "training" | "activities" | "overview"; metric?: string } | null> = {
  get_metric_trend: { view: "biometrics", metric: "hrv_ms" },
  get_sleep_night: { view: "sleep" },
  get_acwr: { view: "training" },
  get_overview: { view: "overview" },
  list_activities: { view: "activities" },
};

const CONTEXT_KEY_VIEW: Record<string, "biometrics" | "sleep" | "training" | "activities" | "overview"> = {
  overview: "overview",
  hrv_trend_30d: "biometrics",
  sleep_last_night: "sleep",
  training_load: "training",
  acwr: "training",
  recent_activities: "activities",
};

function EvidenceChips({
  evidence,
  onJump,
}: {
  evidence: CoachEvidence | null;
  onJump: (view: "biometrics" | "sleep" | "training" | "activities" | "overview", metric?: string) => void;
}) {
  if (!evidence) return null;
  const { tool_calls, context_keys } = evidence;
  const chips: { label: string; view: "biometrics" | "sleep" | "training" | "activities" | "overview"; metric?: string }[] = [];
  const seen = new Set<string>();

  for (const call of tool_calls ?? []) {
    const label = TOOL_LABELS[call.tool] ?? call.tool;
    const target = TOOL_VIEW[call.tool] ?? null;
    if (!target) continue;
    const key = `${label}-${target.view}`;
    if (seen.has(key)) continue;
    seen.add(key);
    chips.push({ label, view: target.view, metric: target.metric });
  }
  for (const ck of context_keys ?? []) {
    if (ck.startsWith("doc:")) continue;
    const view = CONTEXT_KEY_VIEW[ck];
    if (!view) continue;
    const label = ck.replace(/_/g, " ");
    const key = `ctx-${label}-${view}`;
    if (seen.has(key)) continue;
    seen.add(key);
    chips.push({ label, view });
  }

  if (!chips.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((c, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onJump(c.view, c.metric)}
          className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-surface2 px-2 py-0.5 text-[12px] font-medium text-muted transition-colors hover:bg-surface3 hover:text-ink2"
          title={`Open ${c.label}`}
        >
          <Info size={9} className="text-faint" />
          {c.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- draft card */

function DraftCard({
  draft,
  onConfirm,
  onDiscard,
}: {
  draft: CoachDraft;
  onConfirm: () => void;
  onDiscard: () => void;
}) {
  const resolved = draft.status !== "pending";
  const lines = (draft.details ?? "").split("\n").filter(Boolean).slice(0, 3);
  return (
    <div className="mt-2 rounded-[var(--radius-card)] border border-hairline2 bg-surface2/70 p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Badge tone={draft.kind === "training_plan" ? "primary" : "neutral"}>
            {draft.kind === "training_plan" ? "Training plan" : "Supplement protocol"}
          </Badge>
        </div>
        {resolved && (
          <Badge tone={draft.status === "confirmed" ? "positive" : "alert"} dot>
            {draft.status === "confirmed" ? "Confirmed" : "Discarded"}
          </Badge>
        )}
      </div>
      <div className="mt-1.5 text-[13px] font-semibold text-ink">{draft.title}</div>
      <div className="mono text-[12px] text-faint">
        {Array.isArray((draft as CoachDraft & { dates?: unknown }).dates)
          ? ((draft as CoachDraft & { dates: string[] }).dates.join(" → "))
          : "—"}
      </div>
      <div className="mt-1 text-[12px] text-muted">{draft.summary}</div>
      {lines.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[12px] text-muted">
          {lines.map((l, i) => (
            <li key={i} className="leading-[15px]">{l.replace(/^[-*]\s*/, "")}</li>
          ))}
        </ul>
      )}
      {!resolved && (
        <div className="mt-2 flex items-center gap-2">
          <ApexButton size="sm" variant="primary" onClick={onConfirm}>
            Confirm
          </ApexButton>
          <ApexButton size="sm" variant="ghost" onClick={onDiscard}>
            Discard
          </ApexButton>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- monogram */

function ApexMonogram({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="6" className="fill-primarySoft" />
      <path d="M16 7 L25 25 L20 25 L16 16 L12 25 L7 25 Z" className="fill-primaryText" />
    </svg>
  );
}

/* --------------------------------------------------------------- assistant message */

function AssistantMessage({
  msg,
  t,
  locale,
  onJump,
  onConfirmDraft,
  onDiscardDraft,
}: {
  msg: ChatMessageRow;
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
  onJump: (view: "biometrics" | "sleep" | "training" | "activities" | "overview", metric?: string) => void;
  onConfirmDraft: (draftId: string) => void;
  onDiscardDraft: (draftId: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const evidence = (msg.referenced_data as CoachEvidence | null) ?? null;
  const drafts = (msg.drafts as CoachDraft[] | null) ?? [];

  function copy() {
    if (!msg.content) return;
    try {
      navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="flex items-start gap-2.5">
      <div className="mt-0.5 shrink-0">
        <ApexMonogram size={22} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-[var(--radius-card)] bg-surface px-3 py-2.5">
          <Markdown content={msg.content} />
          {drafts.length > 0 && (
            <div className="mt-2">
              <div className="text-[14px] font-medium text-faint">{t("coach_proposed")}</div>
              {drafts.map((d) => (
                <DraftCard
                  key={d.id}
                  draft={d}
                  onConfirm={() => onConfirmDraft(d.id)}
                  onDiscard={() => onDiscardDraft(d.id)}
                />
              ))}
            </div>
          )}
          {evidence && <EvidenceChips evidence={evidence} onJump={onJump} />}
        </div>
        {/* footer */}
        <div className="mt-1 flex items-center gap-2 px-1">
          <span className="mono text-[12px] text-faint">{fmtClock(msg.created_at, locale)}</span>
          {msg.model_tier && (
            <Badge tone="neutral">
              {msg.model_tier}
            </Badge>
          )}
          <button
            type="button"
            onClick={copy}
            className="flex h-4 w-4 items-center justify-center rounded-[var(--radius-control)] text-faint transition-colors hover:bg-surface2 hover:text-ink2"
            aria-label="Copy message"
            title={copied ? "Copied" : "Copy"}
          >
            {copied ? <CornerUpLeft size={10} /> : <Copy size={10} />}
          </button>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- user message (optimistic) */

function UserMessage({
  msg,
  locale,
  onRetry,
}: {
  msg: ChatMessageRow;
  locale: "en" | "it";
  onRetry: () => void;
}) {
  const status = msg.status ?? "sent";
  const isSending = status === "sending";
  const isError = status === "error";
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex max-w-[80%] flex-col items-end">
        <div
          className={`rounded-[var(--radius-card)] px-3 py-2 text-ink ${
            isError ? "bg-alertSoft/40" : "bg-primarySoft/30"
          }`}
        >
          <div className="whitespace-pre-wrap text-[13px] leading-[20px]">{msg.content}</div>
        </div>
      </div>
      <div className="mono flex items-center gap-1.5 pr-1 text-[12px] text-faint">
        {isSending && <span className="text-primaryText">{/* spinner */}
          <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary align-middle" />
          {locale === "it" ? "invio…" : "sending…"}
        </span>}
        {isError && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1 text-alertText hover:underline"
          >
            <RotateCw size={10} /> {t_placeholder(locale)}
          </button>
        )}
        {!isSending && !isError && <span>{fmtClock(msg.created_at, locale)}</span>}
      </div>
    </div>
  );
}

function t_placeholder(locale: "en" | "it") {
  return locale === "it" ? "Non inviato · riprova" : "Not sent · retry";
}

/* --------------------------------------------------------------- working row */

function WorkingRow({ t }: { t: (p: string, vars?: Record<string, string | number>) => string }) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="mt-0.5 shrink-0">
        <ApexMonogram size={22} />
      </div>
      <div className="flex items-center gap-2 rounded-[var(--radius-card)] bg-surface2/60 px-3 py-2">
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-40" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-primary/40" />
        </span>
        <span className="text-[12px] text-muted">{t("coach_thinking")}</span>
        <span className="ml-1 flex gap-0.5">
          <span className="h-1 w-1 animate-bounce rounded-full bg-faint [animation-delay:-0.3s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-faint [animation-delay:-0.15s]" />
          <span className="h-1 w-1 animate-bounce rounded-full bg-faint" />
        </span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- sessions rail */

function SessionsRail({
  sessions,
  currentId,
  search,
  onSearch,
  onSelect,
  onNew,
  onDelete,
  t,
  locale,
}: {
  sessions: ChatSessionRow[];
  currentId: number | null;
  search: string;
  onSearch: (s: string) => void;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
}) {
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.title ?? "").toLowerCase().includes(q));
  }, [sessions, search]);
  const groups = useMemo(() => groupSessions(filtered), [filtered]);

  return (
    <div className="flex flex-col gap-3">
      <ApexButton
        variant="primary"
        size="md"
        className="w-full"
        icon={<Plus size={14} strokeWidth={2.5} />}
        onClick={onNew}
      >
        {t("coach_new_chat")}
      </ApexButton>
      <input
        type="text"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder={t("coach_search")}
        className="num h-8 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2.5 text-[12px] text-ink placeholder:text-faint focus:border-primary/60 focus:outline-none"
      />
      {groups.length === 0 ? (
        <div className="text-[12px] text-muted">{t("coach_no_chats")}</div>
      ) : (
        <div className="flex flex-col gap-3">
          {groups.map((g) => (
            <div key={g.label} className="flex flex-col gap-1">
              <div className="text-[14px] font-medium text-faint">{t(g.label)}</div>
              {g.rows.map((s) => (
                <SessionRow
                  key={s.id}
                  s={s}
                  selected={s.id === currentId}
                  locale={locale}
                  t={t}
                  onSelect={() => onSelect(s.id)}
                  onDelete={() => onDelete(s.id)}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SessionRow({
  s,
  selected,
  onSelect,
  onDelete,
  t,
  locale,
}: {
  s: ChatSessionRow;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
}) {
  return (
    <div
      className={`group flex items-start gap-1.5 rounded-[var(--radius-card)] border p-2 transition-colors ${
        selected ? "border-primary/40 bg-surface2" : "border-transparent hover:bg-surface2/60"
      }`}
    >
      <button type="button" onClick={onSelect} className="min-w-0 flex-1 text-left">
        <div className="truncate text-[12.5px] font-semibold text-ink">
          {s.title || t("coach_new_chat")}
        </div>
        <div className="mono mt-0.5 text-[12px] text-faint">
          {fmtDate(s.last_activity_at, locale)} · {timeAgo(s.last_activity_at, locale)}
        </div>
        <div className="mono text-[12px] text-faint">
          {t("coach_messages", { n: s.message_count })}
        </div>
      </button>
      <ConfirmPopover
        message={t("coach_delete_confirm")}
        onConfirm={onDelete}
        onCancel={() => {}}
        confirmLabel={t("coach_delete") === "coach_delete" ? "Delete" : t("coach_delete")}
        cancelLabel="Cancel"
      >
        <button
          type="button"
          aria-label="Delete chat"
          className="mt-0.5 hidden h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-faint transition-colors hover:bg-alertSoft hover:text-alertText group-hover:flex"
          onClick={(e) => e.stopPropagation()}
        >
          <Trash2 size={11} />
        </button>
      </ConfirmPopover>
    </div>
  );
}

/* --------------------------------------------------------------- context panel */

function ContextPanel({
  overview,
  events,
  docs,
  t,
  locale,
  onEditDocs,
}: {
  overview: Overview | null;
  events: { id: number; title: string; date: string; kind: string }[];
  docs: ContextDocRow[];
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
  onEditDocs: () => void;
}) {
  const readiness = overview?.readiness?.value ?? null;
  const recovery = overview?.recovery?.value ?? null;
  const strain = overview?.strain?.value ?? null;
  const acwr = overview?.acwr ?? null;
  const alerts = overview?.alerts ?? [];

  const now = new Date();
  const upcoming = events
    .filter((e) => new Date(e.date).getTime() >= now.getTime() - 86_400_000)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  const nextEvent = upcoming[0] ?? null;
  const todaySession = overview?.activities?.find((a) => a.local_date === (overview?.date ?? "")) ?? null;

  return (
    <Card pad={false} className="flex flex-col gap-3 p-3">
      <div className="text-[14px] font-medium text-ink2">{t("coach_context_panel")}</div>

      {/* Mini row: Readiness / Recovery / Strain */}
      <div className="grid grid-cols-3 gap-1.5">
        <MiniStat label={t("coach_context_readiness")} value={readiness} />
        <MiniStat label={t("coach_context_recovery")} value={recovery} />
        <MiniStat label={t("coach_context_strain")} value={strain} />
      </div>
      <div className="flex items-center justify-between rounded-[var(--radius-control)] bg-surface2 px-2 py-1">
        <span className="text-[14px] font-medium text-faint">{t("coach_context_acwr")}</span>
        <span className="num text-[12px] font-semibold text-ink2">
          {acwr === null ? "—" : acwr.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center justify-between rounded-[var(--radius-control)] bg-surface2 px-2 py-1">
        <span className="text-[14px] font-medium text-faint">Alerts</span>
        <span className="num text-[12px] font-semibold text-ink2">
          {t("coach_context_alerts", { n: alerts.length })}
        </span>
      </div>

      <Hairline />

      {/* Next event + today's session */}
      <div className="flex flex-col gap-1.5">
        <div className="text-[14px] font-medium text-faint">{t("coach_context_next_event")}</div>
        {nextEvent ? (
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[12px] font-semibold text-ink">{nextEvent.title}</div>
              <div className="mono text-[12px] text-faint">
                {fmtDate(nextEvent.date, locale)}
                {(() => {
                  const d = dayCountdown(nextEvent.date);
                  if (!Number.isFinite(d)) return "";
                  if (d === 0) return locale === "it" ? " · oggi" : " · today";
                  if (d > 0) return ` · ${d}d`;
                  return ` · ${-d}d ago`;
                })()}
              </div>
            </div>
            <Badge tone="neutral" className="shrink-0">{nextEvent.kind}</Badge>
          </div>
        ) : (
          <div className="text-[12px] text-muted">—</div>
        )}
        <div className="text-[14px] font-medium text-faint">{t("coach_context_today_session")}</div>
        {todaySession ? (
          <div className="text-[12px] text-ink2">{todaySession.title}</div>
        ) : (
          <div className="text-[12px] text-muted">—</div>
        )}
      </div>

      <Hairline />

      {/* Context docs */}
      <div className="flex items-center justify-between">
        <div className="text-[14px] font-medium text-faint">Context documents</div>
        <button
          type="button"
          onClick={onEditDocs}
          className="text-[12px] font-semibold text-primaryText hover:underline"
        >
          {t("coach_doc_edit")} →
        </button>
      </div>
      <div className="flex flex-col gap-1">
        {SORTED_DOC_KINDS.map((kind) => {
          const doc = docs.find((d) => d.kind === kind);
          const filled = !!doc && doc.char_count > 0;
          const labelKey = DOC_LABEL_KEYS[kind];
          return (
            <div
              key={kind}
              className="flex items-center justify-between rounded-[var(--radius-control)] bg-surface2/60 px-2 py-1"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span
                  className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${filled ? "bg-positive" : "bg-faint"}`}
                  aria-label={filled ? "filled" : "empty"}
                />
                <span className="text-[12px] text-ink2 truncate">{t(labelKey)}</span>
              </div>
              <span className="mono text-[12px] text-faint shrink-0">
                {filled
                  ? timeAgo(doc!.updated_at, locale)
                  : t("coach_doc_empty")}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

const DOC_LABEL_KEYS: Record<DocKind, string> = {
  profile: "coach_doc_profile",
  goals: "coach_doc_goals",
  injuries: "coach_doc_injuries",
  equipment: "coach_doc_equipment",
  preferences: "coach_doc_preferences",
  season_plan: "coach_doc_season",
};

function MiniStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex flex-col rounded-[var(--radius-control)] bg-surface2 px-2 py-1">
      <span className="text-[14px] font-medium text-faint">{label}</span>
      <span className="num text-[13px] font-semibold text-ink2">
        {value === null || value === undefined ? "—" : Math.round(value)}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- suggested prompts */

interface SuggestedPrompt {
  label: string;
  text: string;
}

function buildSuggestedPrompts(
  overview: Overview | null,
  events: { id: number; title: string; date: string }[],
  gear: { id: number; name: string; usage_pct: number }[],
  t: (p: string, vars?: Record<string, string | number>) => string,
): SuggestedPrompt[] {
  const out: SuggestedPrompt[] = [];
  const alerts = overview?.alerts ?? [];
  if (alerts.length > 0) {
    const a = alerts[0];
    const label = (a.type || "alert").replace(/_/g, " ");
    const text = `Explain my ${label} alert. What does it mean and what should I do?`;
    out.push({ label: t("coach_prompt_alert", { alert: label }), text });
  }
  const now = Date.now();
  const upcoming = events.find((e) => {
    const t = new Date(e.date).getTime();
    return t >= now && t - now <= 14 * 86_400_000;
  });
  if (upcoming) {
    out.push({
      label: t("coach_prompt_event", { event: upcoming.title }),
      text: `Plan this week around ${upcoming.title} on ${fmtDate(upcoming.date, "en")}.`,
    });
  }
  const dueGear = gear.find((g) => g.usage_pct >= 80);
  if (dueGear) {
    out.push({
      label: t("coach_prompt_gear", { gear: dueGear.name }),
      text: `Is my ${dueGear.name} due for service? It is at ${Math.round(dueGear.usage_pct)}% of its service interval.`,
    });
  }
  out.push({ label: t("coach_prompt_evergreen_1"), text: t("coach_prompt_evergreen_1") });
  out.push({ label: t("coach_prompt_evergreen_2"), text: t("coach_prompt_evergreen_2") });
  return out;
}

/* --------------------------------------------------------------- main component */

export function CoachPage() {
  const t = useT();
  const ui = useApexUi();
  const { toast } = useToast();
  const locale = ui.locale;

  // -- sessions + messages
  const [sessions, setSessions] = useState<ChatSessionRow[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [currentId, setCurrentId] = useState<number | null>(getUserItem<number | null>(me.user_id, "coach.activeChatId", null));
  const [messages, setMessages] = useState<ChatMessageRow[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // composer
  const [input, setInput] = useState<string>(() => getUserItem<string>(me.user_id, "coach.draft", ""));
  const taRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // context panel data
  const [overview, setOverview] = useState<Overview | null>(null);
  const [events, setEvents] = useState<{ id: number; title: string; date: string; kind: string }[]>([]);
  const [docs, setDocs] = useState<ContextDocRow[]>([]);

  // mobile sheets
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);

  const currentSession = useMemo(
    () => (currentId === null ? null : sessions.find((s) => s.id === currentId) ?? null),
    [currentId, sessions],
  );

  const suggestedPrompts = useMemo(
    () => buildSuggestedPrompts(overview, events, [], t),
    [overview, events, t],
  );

  /* ----- persist composer draft + active chat id (per-user) */
  useEffect(() => {
    setUserItem(me.user_id, "coach.draft", input);
  }, [input]);
  useEffect(() => {
    setUserItem(me.user_id, "coach.activeChatId", currentId);
    // Use the stable getState() accessor to avoid subscribing to the whole
    // store (which would re-run this effect every render → infinite loop).
    useApexUi.getState().selectChat(currentId);
  }, [currentId]);

  /* ----- auto-grow textarea */
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const maxH = 96;
    ta.style.height = `${Math.min(ta.scrollHeight, maxH)}px`;
  }, [input]);

  /* ----- auto-scroll to bottom on new messages / sending */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, sending, currentId]);

  /* ----- fetch sessions list on mount */
  const refreshSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const r = await fetch("/api/coach/chats", { cache: "no-store" });
      const j = await r.json();
      if (j?.ok) {
        setSessions(j.sessions as ChatSessionRow[]);
        // Pick a default current id if none chosen.
        if (currentId === null && j.sessions.length > 0) {
          setCurrentId(j.sessions[0].id);
        }
      }
    } catch {
      /* ignore */
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  /* ----- fetch session detail when currentId changes */
  useEffect(() => {
    if (currentId === null) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setMessagesLoading(true);
    setError(null);
    (async () => {
      try {
        const r = await fetch(`/api/coach/chats/${currentId}`, { cache: "no-store" });
        const j = await r.json();
        if (cancelled) return;
        if (j?.ok) {
          setMessages(j.messages as ChatMessageRow[]);
        } else {
          setError(j?.error ?? "Failed to load chat");
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Network error");
      } finally {
        if (!cancelled) setMessagesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentId]);

  /* ----- fetch context panel data (overview, events, docs) */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [oR, eR, dR] = await Promise.all([
          fetch("/api/dashboard", { cache: "no-store" }),
          fetch("/api/events", { cache: "no-store" }),
          fetch("/api/context-docs", { cache: "no-store" }),
        ]);
        const [oJ, eJ, dJ] = await Promise.all([oR.json(), eR.json(), dR.json()]);
        if (cancelled) return;
        if (oJ?.ok && oJ.overview) setOverview(oJ.overview as Overview);
        if (eJ?.ok && eJ.events) setEvents(eJ.events as { id: number; title: string; date: string; kind: string }[]);
        if (dJ?.ok && dJ.docs) setDocs(dJ.docs as ContextDocRow[]);
      } catch {
        /* ignore — context panel simply stays empty */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ----- handlers */
  function startNew() {
    setError(null);
    setMessages([]);
    setCurrentId(null);
    setSessionsOpen(false);
    requestAnimationFrame(() => taRef.current?.focus());
  }

  function selectSession(id: number) {
    if (id === currentId) {
      setSessionsOpen(false);
      return;
    }
    setError(null);
    setCurrentId(id);
    setSessionsOpen(false);
  }

  async function deleteSession(id: number) {
    try {
      const r = await fetch(`/api/coach/chats/${id}`, { method: "DELETE" });
      const j = await r.json();
      if (!j?.ok) {
        toast({ title: "Delete failed", description: j?.error ?? "" });
        return;
      }
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (currentId === id) {
        setCurrentId(null);
        setMessages([]);
      }
    } catch (e) {
      toast({ title: "Delete failed", description: e instanceof Error ? e.message : "" });
    }
  }

  function jumpTo(view: "biometrics" | "sleep" | "training" | "activities" | "overview", metric?: string) {
    if (metric) ui.selectMetric(metric);
    ui.setView(view);
  }

  async function confirmDiscardDraft(draftId: string, action: "confirm" | "discard") {
    if (currentId === null) return;
    try {
      const r = await fetch(`/api/coach/chats/${currentId}/drafts/${encodeURIComponent(draftId)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }),
      });
      const j = await r.json();
      if (!r.ok || !j?.ok) throw new Error(j?.error || "Draft update failed");
      setMessages((prev) => prev.map((m) => m.drafts?.some((d) => d.id === draftId) ? { ...m, drafts: j.drafts } : m));
    } catch (error) {
      toast({ title: "Draft update failed", description: error instanceof Error ? error.message : "Network error" });
    }
  }

  /** Send a message. Optimistic for the user msg; assistant msg from the
   *  server response on success. On failure, mark the user msg as "error"
   *  and restore the composer text so the user can retry. */
  async function send(content: string, optimisticId?: number) {
    if (currentId === null) {
      // First create the session, then send.
      try {
        const r = await fetch("/api/coach/chats", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: content.slice(0, 48) }),
        });
        const j = await r.json();
        if (!j?.ok) {
          toast({ title: "Could not start chat", description: j?.error ?? "" });
          // Restore composer text
          setInput(content);
          return;
        }
        const newSession = j.session as ChatSessionRow;
        setSessions((prev) => [newSession, ...prev]);
        setCurrentId(newSession.id);
        // Now recurse-send into the new session.
        await sendInSession(newSession.id, content, optimisticId);
      } catch (e) {
        toast({ title: "Network error", description: e instanceof Error ? e.message : "" });
        setInput(content);
      }
      return;
    }
    await sendInSession(currentId, content, optimisticId);
  }

  async function sendInSession(sessionId: number, content: string, optimisticId?: number) {
    setSending(true);
    setError(null);
    const tempId = optimisticId ?? nextTempId();
    const optimistic: ChatMessageRow = {
      id: tempId,
      role: "user",
      content,
      referenced_data: null,
      drafts: null,
      kind: "data",
      created_at: new Date().toISOString(),
      status: "sending",
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const r = await fetch(`/api/coach/chats/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const j = await r.json();
      if (!j?.ok) {
        // Mark optimistic as error + restore composer text.
        setMessages((prev) =>
          prev.map((m) => (m.id === tempId ? { ...m, status: "error" } : m)),
        );
        setInput(content); // restore
        setError(j?.error ?? "Send failed");
        requestAnimationFrame(() => taRef.current?.focus());
        return;
      }
      // Replace optimistic with server user_message + append assistant_message.
      const userMsg = j.user_message as ChatMessageRow;
      const assistantMsg = j.assistant_message as ChatMessageRow;
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempId),
        { ...userMsg, status: "sent" },
        assistantMsg,
      ]);
      // Update the sessions rail last_activity_at + preview.
      setSessions((prev) =>
        prev
          .map((s) =>
            s.id === sessionId
              ? { ...s, last_activity_at: new Date().toISOString(), preview: content.slice(0, 140), message_count: s.message_count + 2 }
              : s,
          )
          .sort((a, b) => new Date(b.last_activity_at).getTime() - new Date(a.last_activity_at).getTime()),
      );
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) => (m.id === tempId ? { ...m, status: "error" } : m)),
      );
      setInput(content); // restore
      setError(e instanceof Error ? e.message : "Network error");
      requestAnimationFrame(() => taRef.current?.focus());
    } finally {
      setSending(false);
    }
  }

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setInput("");
    void send(trimmed);
  }

  function handleRetry(msg: ChatMessageRow) {
    // Remove the failed user message and re-send.
    setMessages((prev) => prev.filter((m) => m.id !== msg.id));
    void send(msg.content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function pickSuggestion(p: SuggestedPrompt) {
    setInput(p.text);
    requestAnimationFrame(() => {
      taRef.current?.focus();
      const len = p.text.length;
      taRef.current?.setSelectionRange(len, len);
    });
  }

  /* ----- session title shown in conversation header */
  const headerTitle = currentId === null ? t("coach_new_chat") : currentSession?.title ?? t("coach_new_chat");

  /* ----- render */
  return (
    <div className="mx-auto max-w-[1320px]">
      <PageHeader title={t("nav.coach")} subtitle={locale === "it" ? "Chiedi. Verifica. Agisci." : "Ask. Verify. Act."} />

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[260px_minmax(0,1fr)] 2xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        {/* ----------- Column B — conversation (FIRST child on mobile) */}
        <section className="order-1 flex flex-col gap-3 xl:order-2">
          {/* Mobile-only header buttons to open sheets */}
          <div className="flex items-center gap-2 xl:hidden">
            <ApexButton
              variant="secondary"
              size="sm"
              icon={<History size={13} />}
              onClick={() => setSessionsOpen(true)}
            >
              {sessions.length > 0 ? `${sessions.length}` : ""}
              <span className="hidden sm:inline"> chats</span>
            </ApexButton>
            <ApexButton
              variant="secondary"
              size="sm"
              icon={<Sparkles size={13} />}
              onClick={() => setContextOpen(true)}
            >
              <span className="hidden sm:inline">Context</span>
            </ApexButton>
            <div className="ml-auto min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">
              {headerTitle}
            </div>
          </div>

          {/* Conversation card */}
          <Card pad={false} className="flex min-h-[60vh] flex-1 flex-col xl:min-h-[calc(100vh-220px)]">
            {/* Header (desktop) */}
            <div className="hidden items-center justify-between gap-3 border-b border-hairline px-4 py-3 xl:flex">
              <div className="min-w-0 truncate text-[15px] font-semibold text-ink">{headerTitle}</div>
              <div className="flex items-center gap-2 text-faint">
                <Clock size={11} />
                <span className="mono text-[12px]">
                  {currentSession
                    ? timeAgo(currentSession.last_activity_at, locale)
                    : locale === "it" ? "nuova" : "new"}
                </span>
              </div>
            </div>

            {/* Messages scroll area */}
            <div
              ref={scrollRef}
              className="scroll-area flex flex-1 flex-col gap-3 overflow-y-auto p-4"
            >
              {messages.length === 0 && !messagesLoading && !sending && (
                <div className="flex flex-1 flex-col items-center justify-center gap-4 py-8 text-center">
                  <div>
                    <div className="text-[14px] font-medium text-faint">{t("coach_suggested")}</div>
                    <div className="mt-1 max-w-md text-[12px] text-muted">
                      {overview
                        ? locale === "it"
                          ? `Prontezza ${Math.round(overview.readiness?.value ?? 0)} · HRV ${overview.hrv_ms ?? "—"} ms · ${overview.alerts?.length ?? 0} avvisi.`
                          : `Readiness ${Math.round(overview.readiness?.value ?? 0)} · HRV ${overview.hrv_ms ?? "—"} ms · ${overview.alerts?.length ?? 0} alert(s).`
                        : t("coach.placeholder")}
                    </div>
                  </div>
                  <div className="flex max-w-lg flex-wrap justify-center gap-2">
                    {suggestedPrompts.map((p, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => pickSuggestion(p)}
                        className="num rounded-[var(--radius-control)] bg-surface2 px-3 py-1.5 text-[12px] text-ink2 transition-colors hover:bg-surface3"
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messagesLoading && messages.length === 0 && (
                <div className="flex flex-1 items-center justify-center">
                  <Loading label={t("coach.loading") === "coach.loading" ? "Loading…" : t("coach.loading")} />
                </div>
              )}
              {messages.map((m) =>
                m.role === "user" ? (
                  <UserMessage
                    key={m.id}
                    msg={m}
                    locale={locale}
                    onRetry={() => handleRetry(m)}
                  />
                ) : (
                  <AssistantMessage
                    key={m.id}
                    msg={m}
                    t={t}
                    locale={locale}
                    onJump={jumpTo}
                    onConfirmDraft={(id) => confirmDiscardDraft(id, "confirm")}
                    onDiscardDraft={(id) => confirmDiscardDraft(id, "discard")}
                  />
                ),
              )}
              {sending && <WorkingRow t={t} />}
              {error && (
                <div className="rounded-[var(--radius-card)] border border-alert/40 bg-alertSoft/40 px-3 py-2 text-[12px] text-alertText">
                  {error}
                </div>
              )}
            </div>

            <Hairline />

            {/* Suggested prompts after each reply (when not sending) */}
            {messages.length > 0 && !sending && !error && (
              <div className="px-4 pt-2">
                <div className="flex flex-wrap gap-1.5">
                  {suggestedPrompts.slice(0, 4).map((p, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => pickSuggestion(p)}
                      className="num rounded-[var(--radius-control)] bg-surface2 px-2.5 py-1 text-[12px] text-muted transition-colors hover:bg-surface3 hover:text-ink2"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Composer */}
            <div className="p-3">
              <div className="flex items-end gap-2">
                <textarea
                  ref={taRef}
                  value={input}
                  rows={1}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={t("coach.placeholder")}
                  className="num w-full resize-none rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2 text-[13px] leading-[20px] text-ink transition-colors placeholder:text-faint focus:border-primary/60 focus:outline-none"
                />
                <ApexButton
                  variant="primary"
                  size="md"
                  icon={<Send size={14} strokeWidth={2.25} />}
                  onClick={handleSend}
                  disabled={input.trim().length === 0 || sending}
                  aria-label={t("coach.send")}
                >
                  <span className="hidden sm:inline">{t("coach.send")}</span>
                </ApexButton>
              </div>
              <p className="mt-2 px-1 text-[12px] italic text-alertText/40">{t("coach.ai_warning")}</p>
            </div>
          </Card>
        </section>

        {/* ----------- Column A — sessions rail (desktop) */}
        <aside className="order-2 hidden xl:order-1 xl:flex">
          <Card pad={false} className="flex w-full flex-col p-3">
            {sessionsLoading ? (
              <Loading label="Loading chats…" />
            ) : (
              <SessionsRail
                sessions={sessions}
                currentId={currentId}
                search={search}
                onSearch={setSearch}
                onSelect={selectSession}
                onNew={startNew}
                onDelete={deleteSession}
                t={t}
                locale={locale}
              />
            )}
          </Card>
        </aside>

        {/* ----------- Column C — context panel (2xl only) */}
        <aside className="order-3 hidden 2xl:block 2xl:order-3">
          <ContextPanel
            overview={overview}
            events={events}
            docs={docs}
            t={t}
            locale={locale}
            onEditDocs={() => ui.setView("settings")}
          />
        </aside>
      </div>

      {/* ----------- Mobile sheets */}
      {sessionsOpen && (
        <div className="fixed inset-0 z-50 xl:hidden" role="dialog" aria-modal>
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSessionsOpen(false)}
            aria-hidden
          />
          <div className="absolute left-0 top-0 h-full w-[85%] max-w-[320px] overflow-y-auto border-r border-hairline bg-surface p-3 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[14px] font-medium text-ink2">{t("coach.past_chats")}</div>
              <button
                type="button"
                onClick={() => setSessionsOpen(false)}
                className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-faint hover:bg-surface2 hover:text-ink2"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
            <SessionsRail
              sessions={sessions}
              currentId={currentId}
              search={search}
              onSearch={setSearch}
              onSelect={selectSession}
              onNew={startNew}
              onDelete={deleteSession}
              t={t}
              locale={locale}
            />
          </div>
        </div>
      )}
      {contextOpen && (
        <div className="fixed inset-0 z-50 2xl:hidden" role="dialog" aria-modal>
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setContextOpen(false)}
            aria-hidden
          />
          <div className="absolute right-0 top-0 h-full w-[85%] max-w-[360px] overflow-y-auto border-l border-hairline bg-surface p-3 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[14px] font-medium text-ink2">{t("coach_context_panel")}</div>
              <button
                type="button"
                onClick={() => setContextOpen(false)}
                className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-faint hover:bg-surface2 hover:text-ink2"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>
            <ContextPanel
              overview={overview}
              events={events}
              docs={docs}
              t={t}
              locale={locale}
              onEditDocs={() => {
                setContextOpen(false);
                ui.setView("settings");
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
