"use client";

/**
 * Apex Health — Training page (redesign per plan §2).
 *
 * Layout (top → bottom):
 *   Row 1: Today's session (xl:8)   +   Why this plan (xl:4)
 *   Row 2: This week (7 day cells)
 *   Row 3: Load chart (xl:8)        +   Events list (xl:4)
 *   Row 4: Feedback form + history
 *
 * Phase 0 fixes verified here:
 *   1. Live-session Steppers send ACTUAL weight + ACTUAL reps (not reps_min).
 *   2. Feedback form sends rpe + soreness + injuryFlag + bodyArea + notes.
 *   3. local_today computed in user's timezone (Europe/Rome) via Intl en-CA.
 *   4. Events have a PATCH route (Edit button works).
 *   5. Empty states use Training-specific strings (not social.no_data).
 *   6. Training nav icon was already swapped to Dumbbell (no action).
 *
 * Coherence law: every visual primitive comes from `@/components/apex/kit`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Calendar,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Edit2,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me, overview } from "@/lib/apex/data";
import { localToday, addDays, dayDiff, isoWeekday } from "@/lib/apex/localTime";
import { fmtDate, fmtNum } from "@/lib/apex/format";
import {
  Card,
  Section,
  PageSentence,
  StatusDot,
  Empty,
  Loading,
  ApexButton,
  Hairline,
  Segmented,
  Stepper,
  RestTimerRing,
  ConfirmPopover,
} from "@/components/apex/kit";
import {
  InteractiveComboChart,
  ChartLegend,
  ChartInfoBadge,
  type BarCategory,
  type BarSeries,
  type LineSeries,
} from "@/components/apex/charts";

/* --------------------------------------------------------------- types */

type PlanStatus = "draft" | "confirmed" | "done";

interface PlanExercise {
  id: number;
  name: string;
  muscle_group: string;
  sets: number;
  reps: string;
  reps_min?: number;
  reps_max?: number;
  weight_kg: number | null;
  rest_s: number;
  notes: string | null;
}

interface SetLog {
  id: number;
  exerciseId: number;
  exerciseName: string;
  setIndex: number;
  weightKg: number;
  reps: number;
  rpe: number | null;
  loggedAt: string;
}

interface Plan {
  id: number;
  date: string;
  title: string;
  status: PlanStatus;
  adjustmentNote: string | null;
  exercises: PlanExercise[];
  setLogs: SetLog[];
  createdAt: string;
  updatedAt: string;
}

interface ExerciseHistoryEntry {
  date: string;
  weightKg: number;
  reps: number;
  rpe: number | null;
  setIndex: number;
  loggedAt: string;
}

interface ApexEvent {
  id: number;
  title: string;
  kind: string;
  date: string;
  endDate?: string | null;
  priority: string;
  taperDays: number | null;
  note?: string | null;
}

interface FeedbackEntry {
  id: number;
  date: string;
  rpe: number;
  soreness: number;
  injuryFlag: boolean;
  bodyArea: string | null;
  notes: string | null;
}

interface DayLoad {
  date: string;
  load: number;
  acute: number | null;
  chronic: number | null;
  acwr: number | null;
  events: { id: number; title: string; kind: string; priority: string; taperDays: number | null }[];
}

interface TaperWindow {
  eventId: number;
  start: string;
  end: string;
}

/* ----------------------------------------------------------- helpers */

const WEEKDAY_KEYS = ["train_mon", "train_tue", "train_wed", "train_thu", "train_fri", "train_sat", "train_sun"] as const;

function fmtMSS(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/** parse a "8" or "8–10" reps string into { min, max }. */
function parseReps(reps: string): { min: number; max: number } {
  const cleaned = reps.replace(/\s+/g, "");
  const m = cleaned.match(/^(\d+)[–-](\d+)$/);
  if (m) return { min: parseInt(m[1]), max: parseInt(m[2]) };
  const n = parseInt(cleaned);
  if (!Number.isNaN(n)) return { min: n, max: n };
  return { min: 8, max: 12 };
}

/** Default routine slots per weekday (1=Mon … 7=Sun). Rest day = empty. */
const DEFAULT_ROUTINE: Record<number, { title: string; start: string; discipline: string }> = {
  1: { title: "Lower Body · Squat Focus", start: "17:30", discipline: "strength" },
  2: { title: "Endurance Ride · Zone 2", start: "12:00", discipline: "cycling" },
  3: { title: "Upper Body · Push Pull", start: "17:30", discipline: "strength" },
  4: { title: "Rest / Mobility", start: "", discipline: "rest" },
  5: { title: "Threshold Intervals · 4×8", start: "12:00", discipline: "cycling" },
  6: { title: "Long Run · Aerobic", start: "08:00", discipline: "running" },
  7: { title: "Recovery Day", start: "", discipline: "rest" },
};

/** Calendar event kind → badge tone (matches spec: race=alert, session=primary, rest=muted). */
function eventToneForKind(kind: string): "alert" | "primary" | "muted" {
  if (["race", "competition", "enduro", "ski"].includes(kind)) return "alert";
  if (["session", "training_camp"].includes(kind)) return "primary";
  return "muted";
}

/** Build a 6×7 (42-cell) month grid of `YYYY-MM-DD` strings, Mon-start.
 *  Cells from the previous/next month are included so the grid is always full. */
function monthGrid(year: number, monthIdx: number): string[] {
  const first = new Date(Date.UTC(year, monthIdx, 1));
  const firstWd = first.getUTCDay() === 0 ? 7 : first.getUTCDay(); // 1=Mon … 7=Sun
  const start = new Date(first);
  start.setUTCDate(start.getUTCDate() - (firstWd - 1));
  const cells: string[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    cells.push(d.toISOString().slice(0, 10));
  }
  return cells;
}

/** Format a month label like "October 2026" / "ottobre 2026" using the user's locale. */
function monthLabel(year: number, monthIdx: number, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale === "it" ? "it-IT" : "en-US", {
      year: "numeric",
      month: "long",
    }).format(new Date(Date.UTC(year, monthIdx, 1)));
  } catch {
    const names = locale === "it"
      ? ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
      : ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    return `${names[monthIdx]} ${year}`;
  }
}

/* ----------------------------------------------------------- main page */

export function TrainingPage() {
  const t = useT();
  const ui = useApexUi();
  const today = useMemo(() => localToday(me.timezone), []);

  // ----- plan -----
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [planError, setPlanError] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    setPlanLoading(true);
    setPlanError(null);
    try {
      const res = await fetch(`/api/gym/plan?date=${today}`, { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "Failed to load plan");
      setPlan(json.plan);
    } catch (e) {
      setPlanError(e instanceof Error ? e.message : "Unknown");
    } finally {
      setPlanLoading(false);
    }
  }, [today]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  // ----- events -----
  const [events, setEvents] = useState<ApexEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const res = await fetch("/api/events", { cache: "no-store" });
      const json = await res.json();
      if (json.ok) setEvents(json.events);
    } finally {
      setEventsLoading(false);
    }
  }, []);
  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  // ----- load metrics -----
  const [load, setLoad] = useState<{
    series: DayLoad[];
    taperWindows: TaperWindow[];
    summary: { acute_load: number | null; chronic_load: number | null; acwr: number | null };
  } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/metrics/load?days=56", { cache: "no-store" });
        const json = await res.json();
        if (json.ok) setLoad(json);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  // ----- activity dates (for "activity done" dots in the month calendar) -----
  // Fetch up to 100 most-recent activities (covers ~1 year of sessions for the
  // demo user). We only need local_date — built into a Set for O(1) lookup.
  const [activityDates, setActivityDates] = useState<Set<string>>(new Set());
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/activities?days=365&limit=100", { cache: "no-store" });
        const json = await res.json();
        if (json.ok && Array.isArray(json.activities)) {
          setActivityDates(new Set(json.activities.map((a: { local_date?: string }) => a.local_date).filter(Boolean)));
        }
      } catch {
        /* ignore — calendar still works, just no activity dots */
      }
    })();
  }, []);

  // ----- feedback (server seeded + local additions) -----
  const [feedbackHistory, setFeedbackHistory] = useState<FeedbackEntry[]>([]);
  const [feedbackLoading, setFeedbackLoading] = useState(true);
  const loadFeedback = useCallback(async () => {
    setFeedbackLoading(true);
    try {
      const res = await fetch("/api/gym/feedback", { cache: "no-store" });
      const json = await res.json();
      const seeded: FeedbackEntry[] = json.ok ? json.feedback : [];
      // merge with locally-stored additions (per-user)
      const local = readLocalFeedback(me.user_id);
      setFeedbackHistory([...local, ...seeded]);
    } finally {
      setFeedbackLoading(false);
    }
  }, []);
  useEffect(() => {
    loadFeedback();
  }, [loadFeedback]);

  // Derive the page sentence (principle 1: one answer per screen).
  const pageSentence = useMemo(() => {
    if (planLoading) return ui.locale === "it" ? "Carico la sessione di oggi…" : "Loading today's session…";
    if (planError) return ui.locale === "it" ? "Non riesco a caricare il piano." : "Couldn't load your plan.";
    if (!plan) {
      const wd = isoWeekday(today);
      const routine = DEFAULT_ROUTINE[wd];
      if (routine?.discipline === "rest") {
        return ui.locale === "it"
          ? "Giorno di riposo. Genera un piano quando sei pronto."
          : "Rest day today. Generate a plan when you're ready.";
      }
      return ui.locale === "it"
        ? "Nessun piano per oggi. Genera una bozza per iniziare."
        : "No plan yet for today. Generate a draft to get started.";
    }
    const exerciseCount = plan.exercises.length;
    const statusWord = plan.status === "confirmed"
      ? (ui.locale === "it" ? "Confermata" : "Confirmed")
      : plan.status === "done"
      ? (ui.locale === "it" ? "Completata" : "Done")
      : (ui.locale === "it" ? "Bozza" : "Draft");
    return ui.locale === "it"
      ? `Oggi: ${plan.title} · ${exerciseCount} esercizi · ${statusWord}`
      : `Today: ${plan.title} · ${exerciseCount} exercises · ${statusWord}`;
  }, [plan, planLoading, planError, today, ui.locale]);

  return (
    <div className="mx-auto max-w-[1240px] space-y-8 px-6 py-8 pb-16">
      {/* ====== Page title + sentence (principle 1) ====== */}
      <div>
        <h1 className="page-title">{ui.locale === "it" ? "Allenamento" : "Training"}</h1>
        <PageSentence className="mt-2">{pageSentence}</PageSentence>
      </div>

      {/* ====== Hero — Today's session (principle 2: one hero, 2× anything) ====== */}
      <TodaySessionCard
        today={today}
        plan={plan}
        planLoading={planLoading}
        planError={planError}
        onReload={loadPlan}
      />

      {/* ====== Why this plan (secondary, supports the hero) ====== */}
      {plan && (
        <WhyThisPlanCard plan={plan} today={today} />
      )}

      {/* ====== This week / This month (expandable calendar) ====== */}
      <ExpandableCalendarCard
        today={today}
        plan={plan}
        events={events}
        activityDates={activityDates}
        onEventsChanged={loadEvents}
      />

      {/* ====== Load chart + Events ====== */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <LoadCard load={load} events={events} />
        </div>
        <div className="xl:col-span-4">
          <EventsCard
            events={events}
            loading={eventsLoading}
            today={today}
            onChange={loadEvents}
          />
        </div>
      </div>

      {/* ====== Feedback ====== */}
      <FeedbackCard
        today={today}
        history={feedbackHistory}
        loading={feedbackLoading}
        onSubmitted={loadFeedback}
      />
    </div>
  );
}

/* =========================================================== ROW 1A: Today's session */

function TodaySessionCard({
  today,
  plan,
  planLoading,
  planError,
  onReload,
}: {
  today: string;
  plan: Plan | null;
  planLoading: boolean;
  planError: string | null;
  onReload: () => void;
}) {
  const t = useT();
  const ui = useApexUi();

  if (planLoading) {
    return (
      <Card>
        <Section label={ui.locale === "it" ? "Oggi" : "Today"}>
          <Loading label={ui.locale === "it" ? "Carico il piano…" : "Loading plan…"} />
        </Section>
      </Card>
    );
  }
  if (planError) {
    return (
      <Card>
        <Section label={ui.locale === "it" ? "Oggi" : "Today"}>
          <div className="text-[14px] text-alertText">{planError}</div>
          <div className="mt-3">
            <ApexButton variant="secondary" size="sm" onClick={onReload}>
              {ui.locale === "it" ? "Riprova" : "Retry"}
            </ApexButton>
          </div>
        </Section>
      </Card>
    );
  }

  if (!plan) {
    return <NoPlanCard today={today} onGenerated={onReload} />;
  }
  if (plan.status === "draft") {
    return <DraftPlanCard plan={plan} onReload={onReload} />;
  }
  // confirmed or done → live session mode
  return <LiveSessionCard plan={plan} onReload={onReload} />;
}

/* ---- No plan state ---- */
function NoPlanCard({ today, onGenerated }: { today: string; onGenerated: () => void }) {
  const t = useT();
  const ui = useApexUi();
  const weekday = isoWeekday(today);
  const routine = DEFAULT_ROUTINE[weekday];
  const isRest = routine?.discipline === "rest";
  const [creating, setCreating] = useState(false);

  async function generate() {
    setCreating(true);
    try {
      await fetch("/api/gym/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: today }),
      });
      onGenerated();
    } finally {
      setCreating(false);
    }
  }

  return (
    <Card>
      <Section label={ui.locale === "it" ? "Oggi" : "Today"}>
        {/* Hero line — the plan title (or rest day) is the dominant element */}
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">
            {isRest
              ? (ui.locale === "it" ? "Giorno di riposo" : "Rest day")
              : (routine?.title || (ui.locale === "it" ? "Nessun piano" : t("train_no_plan")))}
          </h2>
          <span className="num text-[14px] text-muted">{fmtDate(today, ui.locale)}</span>
        </div>
        <p className="mt-2 text-[16px] text-ink2">
          {isRest
            ? (ui.locale === "it"
              ? "Recupero attivo — camminata leggera, mobilità, sonno prioritizzato."
              : "Active recovery — light walk, mobility, sleep prioritised.")
            : (ui.locale === "it"
              ? `Slot di routine: ${routine?.start || "—"} · ${routine?.discipline}`
              : `Routine slot: ${routine?.start || "—"} · ${routine?.discipline}`)}
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <ApexButton onClick={generate} disabled={creating} icon={<Plus size={14} />}>
            {creating
              ? (ui.locale === "it" ? "Genero…" : "Generating…")
              : t("train_generate")}
          </ApexButton>
          {!isRest && (
            <span className="text-[14px] text-muted">
              {ui.locale === "it"
                ? "Il coach creerà un piano da confermare."
                : "The coach will draft a plan you can confirm."}
            </span>
          )}
        </div>
      </Section>
    </Card>
  );
}

/* ---- Draft state ---- */
function DraftPlanCard({ plan, onReload }: { plan: Plan; onReload: () => void }) {
  const t = useT();
  const ui = useApexUi();
  const [confirming, setConfirming] = useState(false);

  async function confirm() {
    setConfirming(true);
    try {
      const res = await fetch(`/api/gym/plan/${plan.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "confirmed" }),
      });
      const json = await res.json();
      if (json.ok) onReload();
    } finally {
      setConfirming(false);
    }
  }

  return (
    <Card>
      <Section label={ui.locale === "it" ? "Oggi" : "Today"}>
        {/* Hero line — the plan title is the dominant element */}
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">
            {plan.title}
          </h2>
          <div className="flex shrink-0 items-center gap-3">
            <StatusDot tone="watch" label={t("train_draft")} />
            <span className="num text-[14px] text-muted">{fmtDate(plan.date, ui.locale)}</span>
          </div>
        </div>

        {plan.adjustmentNote && (
          <div className="mt-3 rounded-[var(--radius-control)] bg-surface2 p-4">
            <div className="text-[14px] font-medium text-ink2">
              {t("train_adjustment_note")}
            </div>
            <div className="mt-1 text-[14px] leading-relaxed text-ink2">
              {plan.adjustmentNote}
            </div>
          </div>
        )}

        {/* Exercise list — flat table, surface-2 header, divider rows (no Card border) */}
        <div className="mt-5 overflow-hidden rounded-[var(--radius-control)] bg-surface2">
          <table className="w-full text-left text-[14px]">
            <thead className="text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">{ui.locale === "it" ? "Esercizio" : "Exercise"}</th>
                <th className="px-3 py-2 font-medium">{ui.locale === "it" ? "Gruppo" : "Group"}</th>
                <th className="px-3 py-2 text-right font-medium">Sets</th>
                <th className="px-3 py-2 text-right font-medium">Reps</th>
                <th className="px-3 py-2 text-right font-medium">kg</th>
              </tr>
            </thead>
            <tbody>
              {plan.exercises.map((ex, i) => (
                <tr key={ex.id} className="border-t border-[var(--c-divider)]">
                  <td className="px-3 py-2 text-muted">{i + 1}</td>
                  <td className="px-3 py-2 font-semibold text-ink">{ex.name}</td>
                  <td className="px-3 py-2 text-muted">{ex.muscle_group}</td>
                  <td className="num px-3 py-2 text-right">{ex.sets}</td>
                  <td className="num px-3 py-2 text-right">{ex.reps}</td>
                  <td className="num px-3 py-2 text-right">{ex.weight_kg ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <ApexButton onClick={confirm} disabled={confirming} icon={<Check size={14} />}>
            {confirming
              ? (ui.locale === "it" ? "Confermo…" : "Confirming…")
              : t("train_confirm")}
          </ApexButton>
          <span className="text-[14px] text-muted">
            {ui.locale === "it"
              ? "La conferma avvia la modalità sessione live."
              : "Confirming starts live session mode."}
          </span>
        </div>
      </Section>
    </Card>
  );
}

/* ---- Live session (confirmed) ---- */

type LiveMode = "active" | "rest" | "complete";

function LiveSessionCard({ plan, onReload }: { plan: Plan; onReload: () => void }) {
  const t = useT();
  const ui = useApexUi();

  // start at first set of first exercise with no logged sets yet
  const initialIdx = useMemo(() => {
    const logged = new Set(plan.setLogs.map((l) => `${l.exerciseId}:${l.setIndex}`));
    for (let ei = 0; ei < plan.exercises.length; ei++) {
      const ex = plan.exercises[ei];
      for (let s = 0; s < ex.sets; s++) {
        if (!logged.has(`${ex.id}:${s}`)) return { exIdx: ei, setIdx: s };
      }
    }
    return { exIdx: 0, setIdx: 0 };
  }, [plan]);

  const [mode, setMode] = useState<LiveMode>("active");
  const [exIdx, setExIdx] = useState(initialIdx.exIdx);
  const [setIdx, setSetIdx] = useState(initialIdx.setIdx);
  const [restLeft, setRestLeft] = useState(0);
  const [restTotal, setRestTotal] = useState(0);
  const [collapsedUpNext, setCollapsedUpNext] = useState(false);
  const [showWhole, setShowWhole] = useState(false);

  // session timer (for finish summary)
  const startedAtRef = useRef<number>(Date.now());

  const ex = plan.exercises[exIdx];
  const logsForEx = plan.setLogs.filter((l) => l.exerciseId === ex?.id);

  // local stepper state — defaults to last-session weight + lower rep target
  const [weight, setWeight] = useState(0);
  const [reps, setReps] = useState(8);
  const [rpe, setRpe] = useState<number | null>(null);
  const [history, setHistory] = useState<ExerciseHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // when exercise changes, load its history + reset steppers to the smart default
  useEffect(() => {
    if (!ex) return;
    setHistoryLoading(true);
    setRpe(null);
    (async () => {
      try {
        const res = await fetch(`/api/gym/exercises/${ex.id}/history?limit=5`, { cache: "no-store" });
        const json = await res.json();
        setHistory(json.ok ? json.history : []);
        // pre-fill weight + reps from last time, else template
        const last = json.history?.[0];
        const parsed = parseReps(ex.reps);
        setWeight(last ? Math.round(last.weightKg) : ex.weight_kg ?? 0);
        setReps(last ? last.reps : parsed.min);
      } catch {
        const parsed = parseReps(ex.reps);
        setWeight(ex.weight_kg ?? 0);
        setReps(parsed.min);
      } finally {
        setHistoryLoading(false);
      }
    })();
  }, [ex]);

  // rest timer effect
  useEffect(() => {
    if (mode !== "rest") return;
    if (restLeft <= 0) {
      advanceAfterRest();
      return;
    }
    const id = window.setInterval(() => setRestLeft((s) => s - 1), 1000);
    return () => window.clearInterval(id);
  }, [mode, restLeft]);

  function advanceAfterRest() {
    if (!ex) return;
    if (setIdx + 1 < ex.sets) {
      setSetIdx((s) => s + 1);
      setMode("active");
      return;
    }
    if (exIdx + 1 < plan.exercises.length) {
      setExIdx((i) => i + 1);
      setSetIdx(0);
      setMode("active");
    } else {
      setMode("complete");
    }
  }

  function adjustRest(delta: number) {
    setRestLeft((s) => Math.max(0, s + delta));
    setRestTotal((t) => Math.max(1, t + delta));
  }

  async function logSet() {
    if (!ex) return;
    // Phase 0 fix #1 — send ACTUAL weight + ACTUAL reps (not reps_min), plus optional RPE.
    await fetch(`/api/gym/plan/${plan.id}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        exerciseId: ex.id,
        exerciseName: ex.name,
        setIndex: setIdx,
        weightKg: weight,
        reps,
        rpe: rpe,
      }),
    });
    // start rest timer
    setRestTotal(ex.rest_s);
    setRestLeft(ex.rest_s);
    setMode("rest");
    onReload();
  }

  if (!ex) {
    return (
      <Card>
        <Section label={ui.locale === "it" ? "Oggi" : "Today"}>
          <div className="text-[28px] font-semibold tracking-[-0.02em] text-ink">{plan.title}</div>
          <Empty title={ui.locale === "it" ? "Nessun esercizio nel piano." : "No exercises in plan."} />
        </Section>
      </Card>
    );
  }

  const totalSets = plan.exercises.reduce((acc, e) => acc + e.sets, 0);
  const completedSets = plan.setLogs.length;
  const isLastSetOfEx = setIdx + 1 >= ex.sets;
  const upNext = plan.exercises.slice(exIdx + 1);

  return (
    <Card>
      <Section label={ui.locale === "it" ? "Sessione live" : "Live session"}>
        {/* Hero line — plan title is the dominant element */}
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">
            {plan.title}
          </h2>
          <div className="flex shrink-0 items-center gap-3">
            <StatusDot
              tone={mode === "complete" ? "ok" : "neutral"}
              label={mode === "complete"
                ? t("training.done")
                : (ui.locale === "it" ? `Serie ${completedSets}/${totalSets}` : `Set ${completedSets}/${totalSets}`)}
            />
            <span className="num text-[14px] text-muted">{fmtDate(plan.date, ui.locale)}</span>
          </div>
        </div>
      </Section>

      {/* progress bar */}
      {mode !== "complete" && (
        <div className="mt-4">
          <div className="num h-1.5 w-full overflow-hidden rounded-full bg-surface3">
            <div
              className="bg-primary transition-all"
              style={{ width: `${(completedSets / Math.max(totalSets, 1)) * 100}%` }}
            />
          </div>
        </div>
      )}

      {mode === "complete" ? (
        <div className="mt-4"><FinishSummary plan={plan} startedAt={startedAtRef.current} /></div>
      ) : mode === "rest" ? (
        <div className="mt-4 flex flex-col items-center gap-4 py-4">
          <RestTimerRing
            secondsLeft={restLeft}
            total={restTotal || ex.rest_s}
            onAdjust={adjustRest}
            onSkip={() => {
              setRestLeft(0);
            }}
          />
          <div className="text-[14px] text-muted">
            {ui.locale === "it" ? "Prossimo" : "Up next"}:{" "}
            <span className="text-ink2">
              {isLastSetOfEx
                ? upNext[0]?.name ?? (ui.locale === "it" ? "Completato" : "Done")
                : `${ex.name} · ${ui.locale === "it" ? "serie" : "set"} ${setIdx + 2}/${ex.sets}`}
            </span>
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {/* current exercise — surface-2 panel inside the Card, NO border */}
          <div className="rounded-[var(--radius-card)] bg-surface2 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[14px] text-ink2">
                  {ui.locale === "it" ? "Esercizio" : "Exercise"} {exIdx + 1}/{plan.exercises.length}
                </div>
                <div className="mt-1 text-[24px] font-semibold tracking-[-0.01em] text-ink">
                  {ex.name}
                </div>
                <div className="text-[14px] text-muted">{ex.muscle_group}</div>
              </div>
              <div className="text-right">
                <div className="num text-[14px] text-muted">
                  {t("train_target", { sets: ex.sets, reps: ex.reps })}
                </div>
                <SetDots total={ex.sets} current={setIdx} logs={logsForEx} />
              </div>
            </div>

            <Hairline className="my-3 !bg-[var(--c-divider)]" />

            {/* Last time line */}
            <div className="text-[14px] text-muted">
              {historyLoading ? (
                <span>…</span>
              ) : history.length > 0 ? (
                <>
                  <span className="text-ink2">{t("train_last_time")}</span>{" "}
                  <span className="num text-ink2">
                    {history[0].weightKg} kg × {history[0].reps}{" "}
                    <span className="text-muted">· {fmtDate(history[0].date, ui.locale)}</span>
                  </span>
                </>
              ) : (
                <>
                  <span className="text-ink2">{t("train_last_time")}</span>{" "}
                  <span className="text-muted">
                    {ui.locale === "it" ? "prima volta" : "first time"}
                  </span>
                </>
              )}
            </div>

            {/* steppers */}
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1.5 text-[14px] font-medium text-ink2">{t("train_weight")}</div>
                <Stepper value={weight} onChange={setWeight} step={2.5} min={0} max={400} suffix="kg" />
              </div>
              <div>
                <div className="mb-1.5 text-[14px] font-medium text-ink2">{t("train_reps")}</div>
                <Stepper value={reps} onChange={setReps} step={1} min={0} max={50} />
              </div>
            </div>

            {ex.notes && (
              <div className="mt-3 text-[14px] italic leading-snug text-muted">{ex.notes}</div>
            )}

            {/* RPE chip row — only on the last set of an exercise */}
            {isLastSetOfEx && (
              <div className="mt-4">
                <div className="mb-1.5 text-[14px] font-medium text-ink2">{t("train_rpe")} (6–10)</div>
                <div className="flex flex-wrap gap-1.5">
                  {[6, 7, 8, 9, 10].map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setRpe(rpe === r ? null : r)}
                      className={`num h-7 rounded-[var(--radius-control)] px-2.5 text-[14px] font-semibold transition-colors ${
                        rpe === r
                          ? "bg-primarySoft text-primaryText"
                          : "bg-surface text-muted hover:bg-surface3 hover:text-ink2"
                      }`}
                    >
                      {r}
                    </button>
                  ))}
                  {rpe !== null && (
                    <button
                      type="button"
                      onClick={() => setRpe(null)}
                      className="h-7 rounded-[var(--radius-control)] bg-surface px-2 text-muted hover:bg-surface3 hover:text-ink"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="mt-4">
              <ApexButton size="lg" className="w-full" onClick={logSet}>
                {t("train_log_set")}
              </ApexButton>
            </div>
          </div>

          {/* Up next (collapsible) — surface-2 panel, NO border */}
          {upNext.length > 0 && (
            <div className="rounded-[var(--radius-card)] bg-surface2">
              <button
                type="button"
                onClick={() => setCollapsedUpNext((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left"
              >
                <span className="text-[14px] font-medium text-ink2">{t("train_up_next")}</span>
                <span className="flex items-center gap-2 text-[14px] text-muted">
                  {upNext.length} {ui.locale === "it" ? "esercizi" : "exercises"}
                  {collapsedUpNext ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                </span>
              </button>
              {!collapsedUpNext && (
                <div className="border-t border-[var(--c-divider)] px-4 py-2">
                  {upNext.map((e, i) => (
                    <div
                      key={e.id}
                      className="flex items-center justify-between py-1.5 text-[14px]"
                    >
                      <span className="text-ink2">
                        {exIdx + 2 + i}. {e.name}
                      </span>
                      <span className="num text-muted">
                        {e.sets} × {e.reps} · {e.weight_kg ?? 0}kg
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Whole session expander — surface-2 panel, NO border */}
          <div className="rounded-[var(--radius-card)] bg-surface2">
            <button
              type="button"
              onClick={() => setShowWhole((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-left"
            >
              <span className="text-[14px] font-medium text-ink2">{t("train_whole_session")}</span>
              {showWhole ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
            {showWhole && (
              <div className="border-t border-[var(--c-divider)] px-4 py-2">
                {plan.exercises.map((e, i) => {
                  const done = plan.setLogs.filter((l) => l.exerciseId === e.id).length;
                  return (
                    <div
                      key={e.id}
                      className={`flex items-center justify-between py-1.5 text-[14px] ${
                        i === exIdx ? "text-primaryText" : ""
                      }`}
                    >
                      <span className={i === exIdx ? "font-semibold" : "text-ink2"}>
                        {i + 1}. {e.name}
                      </span>
                      <span className="num text-muted">
                        {done}/{e.sets}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function SetDots({
  total,
  current,
  logs,
}: {
  total: number;
  current: number;
  logs: SetLog[];
}) {
  const loggedIdx = new Set(logs.map((l) => l.setIndex));
  // dots: ● for done, ◐ for current, ○ for upcoming
  const dots: React.ReactNode[] = [];
  for (let i = 0; i < total; i++) {
    let sym: string;
    let cls: string;
    if (loggedIdx.has(i)) {
      sym = "●";
      cls = "text-primary";
    } else if (i === current) {
      sym = "●";
      cls = "text-primaryText";
    } else {
      sym = "○";
      cls = "text-faint";
    }
    dots.push(
      <span key={i} className={`num mono ${cls}`}>
        {sym}
      </span>
    );
  }
  return <div className="mt-1 flex gap-0.5">{dots}</div>;
}

function FinishSummary({ plan, startedAt }: { plan: Plan; startedAt: number }) {
  const t = useT();
  const ui = useApexUi();

  const totalVolume = plan.setLogs.reduce((acc, l) => acc + l.weightKg * l.reps, 0);
  const durationS = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
  const perExercise = new Map<number, { name: string; maxKg: number; maxReps: number }>();
  for (const e of plan.exercises) {
    const logs = plan.setLogs.filter((l) => l.exerciseId === e.id);
    if (logs.length === 0) continue;
    const maxKg = Math.max(...logs.map((l) => l.weightKg));
    const maxReps = Math.max(...logs.map((l) => l.reps));
    perExercise.set(e.id, { name: e.name, maxKg, maxReps });
  }

  return (
    <div>
      {/* Session-complete banner — surface contrast only (positive-soft fill), no border */}
      <div className="rounded-[var(--radius-card)] bg-positiveSoft px-4 py-3 text-[14px] font-medium text-positiveText">
        <div className="flex items-center gap-2">
          <StatusDot tone="ok" label={ui.locale === "it" ? "Completata" : "Complete"} />
          <span>
            {ui.locale === "it"
              ? "Sessione completata. Recupero attivo consigliato."
              : "Session complete. Active recovery recommended."}
          </span>
        </div>
      </div>
      {/* 3 numbers — flat, surface-2 contrast only, no bordered tiles */}
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Fact label={t("train_total_volume")} value={fmtNum(totalVolume, 0)} unit="kg" />
        <Fact label={t("train_duration")} value={fmtMSS(durationS)} />
        <Fact
          label={ui.locale === "it" ? "Serie totali" : "Sets logged"}
          value={String(plan.setLogs.length)}
          unit={`${plan.exercises.length} ${ui.locale === "it" ? "esercizi" : "exercises"}`}
        />
      </div>
      <div className="mt-5">
        <div className="mb-2 text-[14px] font-medium text-ink2">{t("train_personal_bests")}</div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Array.from(perExercise.values()).map((e) => (
            <div
              key={e.name}
              className="flex items-center justify-between rounded-[var(--radius-control)] bg-surface2 px-3 py-2 text-[14px]"
            >
              <span className="text-ink2">{e.name}</span>
              <span className="num text-muted">
                {e.maxKg}kg × {e.maxReps}
              </span>
            </div>
          ))}
          {perExercise.size === 0 && (
            <div className="text-[14px] text-muted">
              {ui.locale === "it" ? "Nessuna serie registrata." : "No sets logged."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Fact — a small flat label + value (no border, no eyebrow). */
function Fact({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-[var(--radius-control)] bg-surface2 px-4 py-3">
      <div className="text-[14px] text-ink2">{label}</div>
      <div className="num mt-1 flex items-baseline gap-1 text-[28px] font-semibold text-ink">
        {value}
        {unit && <span className="text-[14px] font-medium text-ink2">{unit}</span>}
      </div>
    </div>
  );
}

/* =========================================================== ROW 1B: Why this plan */

function WhyThisPlanCard({ plan, today }: { plan: Plan | null; today: string }) {
  const t = useT();
  const ui = useApexUi();
  // hide if no plan
  if (!plan) return null;

  // local feedback history (last entry)
  const localFb = readLocalFeedback(me.user_id);
  const lastFb = localFb[0];

  return (
    <Card>
      <Section label={t("train_why_plan")}>
        <div className="space-y-4">
          <div>
            <div className="text-[14px] font-medium text-ink2">{t("train_adjustment_note")}</div>
            <div className="mt-1 text-[14px] leading-relaxed text-ink2">
              {plan.adjustmentNote || (ui.locale === "it" ? "—" : "—")}
            </div>
          </div>

          <Hairline className="!bg-[var(--c-divider)]" />

          <div>
            <div className="text-[14px] font-medium text-ink2">
              {ui.locale === "it" ? "Oggi" : "Today"}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-[14px]">
              <StatusDot
                tone={overview.readiness.value !== null && overview.readiness.value >= 75 ? "ok" : overview.readiness.value !== null && overview.readiness.value >= 50 ? "watch" : overview.readiness.value !== null ? "alert" : "neutral"}
                label={`${ui.locale === "it" ? "Prontezza" : "Readiness"} ${overview.readiness.value ?? "—"}`}
              />
              <StatusDot
                tone={overview.acwr == null ? "neutral" : overview.acwr >= 0.8 && overview.acwr <= 1.3 ? "ok" : overview.acwr > 1.5 ? "alert" : "watch"}
                label={`ACWR ${fmtNum(overview.acwr, 2)}`}
              />
            </div>
          </div>

          <Hairline className="!bg-[var(--c-divider)]" />

          <div>
            <div className="text-[14px] font-medium text-ink2">
              {ui.locale === "it" ? "Ultimo feedback" : "Last feedback"}
            </div>
            {lastFb ? (
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[14px] text-muted">
                <span className="num text-ink2">
                  {fmtDate(lastFb.date, ui.locale)}
                </span>
                <span>RPE {lastFb.rpe}</span>
                <span>{ui.locale === "it" ? "Indol." : "Soreness"} {lastFb.soreness}</span>
                {lastFb.injuryFlag && (
                  <StatusDot tone="alert" label={lastFb.bodyArea || (ui.locale === "it" ? "Infortunio" : "Injury")} />
                )}
              </div>
            ) : (
              <div className="mt-1 text-[14px] text-muted">
                {ui.locale === "it" ? "Nessun feedback recente." : "No recent feedback."}
              </div>
            )}
          </div>
        </div>
      </Section>
      <div className="mt-3 text-[13px] text-muted">
        {ui.locale === "it"
          ? "Aggiornato al fuso orario locale"
          : "Computed in your local timezone"}{" "}
        · {today}
      </div>
    </Card>
  );
}

/* =========================================================== ROW 2: This week */

function ThisWeekCard({
  today,
  plan,
  events,
}: {
  today: string;
  plan: Plan | null;
  events: ApexEvent[];
}) {
  // Backward-compat shim — the new expandable card below wraps this. Kept
  // only so any other internal callers don't break during the migration.
  return <ExpandableCalendarCard today={today} plan={plan} events={events} activityDates={new Set()} onEventsChanged={() => {}} />;
}

type CalendarMode = "week" | "month";

function ExpandableCalendarCard({
  today,
  plan,
  events,
  activityDates,
  onEventsChanged,
}: {
  today: string;
  plan: Plan | null;
  events: ApexEvent[];
  activityDates: Set<string>;
  onEventsChanged: () => void;
}) {
  const t = useT();
  const ui = useApexUi();

  // mode toggle (default: week)
  const [mode, setMode] = useState<CalendarMode>("week");

  // month navigation (only used in month mode). Anchored to today's month
  // initially so the user sees their current month first.
  const [cursor, setCursor] = useState<{ year: number; monthIdx: number }>(() => {
    const d = new Date(`${today}T00:00:00Z`);
    return { year: d.getUTCFullYear(), monthIdx: d.getUTCMonth() };
  });

  // routine editor state (week mode only — kept from the original card)
  const [editing, setEditing] = useState(false);
  const [routine, setRoutine] = useState<Record<number, { title: string; start: string; discipline: string }>>(DEFAULT_ROUTINE);

  // build Monday → Sunday of the current week (week mode)
  const todayWd = isoWeekday(today); // 1=Mon … 7=Sun
  const monday = addDays(today, -(todayWd - 1));
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(monday, i));

  // 6×7 month grid (month mode)
  const grid = useMemo(() => monthGrid(cursor.year, cursor.monthIdx), [cursor.year, cursor.monthIdx]);

  // add-event sheet (month mode tap-to-add)
  const [addDate, setAddDate] = useState<string | null>(null);

  function goPrevMonth() {
    setCursor((c) => {
      const m = c.monthIdx - 1;
      return m < 0 ? { year: c.year - 1, monthIdx: 11 } : { year: c.year, monthIdx: m };
    });
  }
  function goNextMonth() {
    setCursor((c) => {
      const m = c.monthIdx + 1;
      return m > 11 ? { year: c.year + 1, monthIdx: 0 } : { year: c.year, monthIdx: m };
    });
  }
  function goTodayMonth() {
    const d = new Date(`${today}T00:00:00Z`);
    setCursor({ year: d.getUTCFullYear(), monthIdx: d.getUTCMonth() });
  }

  // weekday header row labels (Mon … Sun)
  const weekdayHeaders = WEEKDAY_KEYS.map((k) => t(k));

  // ---- shared routine slot lookup (used by both views)
  const routineFor = (date: string) => {
    const wd = isoWeekday(date);
    return routine[wd];
  };

  return (
    <Card pad={false} className="overflow-hidden">
      <div className="p-7 pb-0">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <div className="text-[14px] text-ink2">{ui.locale === "it" ? "Lun → Dom" : "Mon → Sun"}</div>
            <div className="mt-1 text-[20px] font-semibold tracking-[-0.015em] text-ink">
              {mode === "week"
                ? t("train_this_week")
                : monthLabel(cursor.year, cursor.monthIdx, ui.locale)}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Segmented<CalendarMode>
              size="sm"
              value={mode}
              onChange={(v) => setMode(v)}
              options={[
                { value: "week", label: ui.locale === "it" ? "Settimana" : "Week" },
                { value: "month", label: ui.locale === "it" ? "Mese" : "Month" },
              ]}
            />
            {mode === "week" && (
              <ApexButton
                variant="secondary"
                size="sm"
                icon={<Edit2 size={12} />}
                onClick={() => setEditing((v) => !v)}
              >
                {t("train_edit_routine")}
              </ApexButton>
            )}
          </div>
        </div>
      </div>

      {mode === "week" ? (
        <div className="grid grid-cols-1 gap-px border-t border-[var(--c-divider)] bg-[var(--c-divider)] sm:grid-cols-4 lg:grid-cols-7">
          {weekDays.map((d) => {
            const wd = isoWeekday(d);
            const isToday = d === today;
            const isPast = dayDiff(d, today) < 0;
            const routineSlot = routine[wd];
            const isRest = routineSlot?.discipline === "rest";
            const ev = events.find((e) => e.date === d);
            const planForDay = d === today && plan ? plan : null;
            const planStatus: PlanStatus | null = planForDay?.status ?? null;
            const hasActivity = activityDates.has(d);
            return (
              <WeekDayCell
                key={d}
                date={d}
                weekdayKey={WEEKDAY_KEYS[wd - 1]}
                isToday={isToday}
                isPast={isPast}
                routineSlot={routineSlot}
                isRest={isRest}
                event={ev}
                planStatus={planStatus}
                editing={editing}
                onRoutineChange={(newSlot) => setRoutine((r) => ({ ...r, [wd]: newSlot }))}
                hasActivity={hasActivity}
              />
            );
          })}
        </div>
      ) : (
        <div className="border-t border-[var(--c-divider)]">
          {/* month navigation row */}
          <div className="flex items-center justify-between gap-2 px-4 py-2">
            <button
              type="button"
              onClick={goPrevMonth}
              className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface2 hover:text-ink"
              aria-label={ui.locale === "it" ? "Mese precedente" : "Previous month"}
            >
              <ChevronLeft size={14} />
            </button>
            <div className="flex items-center gap-2">
              <Calendar size={14} className="text-muted" />
              <span className="text-[14px] font-semibold text-ink">
                {monthLabel(cursor.year, cursor.monthIdx, ui.locale)}
              </span>
              <button
                type="button"
                onClick={goTodayMonth}
                className="num rounded-[var(--radius-control)] bg-surface2 px-2 py-0.5 text-[13px] font-semibold text-muted hover:bg-surface3 hover:text-ink"
              >
                {ui.locale === "it" ? "Oggi" : "Today"}
              </button>
            </div>
            <button
              type="button"
              onClick={goNextMonth}
              className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface2 hover:text-ink"
              aria-label={ui.locale === "it" ? "Mese successivo" : "Next month"}
            >
              <ChevronRight size={14} />
            </button>
          </div>

          {/* weekday header */}
          <div className="grid grid-cols-7 gap-px border-t border-[var(--c-divider)] bg-[var(--c-divider)]">
            {weekdayHeaders.map((label) => (
              <div key={label} className="bg-surface px-1 py-1.5 text-center text-[12px] font-medium text-muted">
                {label}
              </div>
            ))}
          </div>

          {/* 6×7 day grid */}
          <div className="grid grid-cols-7 gap-px bg-[var(--c-divider)]">
            {grid.map((date) => {
              const inMonth = date.slice(5, 7) === String(cursor.monthIdx + 1).padStart(2, "0")
                && date.slice(0, 4) === String(cursor.year);
              const isToday = date === today;
              const isPast = dayDiff(date, today) < 0;
              const dayEvents = events.filter((e) => e.date === date);
              const routineSlot = routineFor(date);
              const isRest = routineSlot?.discipline === "rest";
              const planForDay = date === today && plan ? plan : null;
              const planStatus: PlanStatus | null = planForDay?.status ?? null;
              const hasActivity = activityDates.has(date);

              return (
                <MonthDayCell
                  key={date}
                  date={date}
                  inMonth={inMonth}
                  isToday={isToday}
                  isPast={isPast}
                  isRest={isRest}
                  planStatus={planStatus}
                  events={dayEvents}
                  hasActivity={hasActivity}
                  onAddEvent={() => setAddDate(date)}
                />
              );
            })}
          </div>

          {/* small legend strip */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-[13px] text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-alert" />
              {ui.locale === "it" ? "Gara" : "Race"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-primary" />
              {ui.locale === "it" ? "Sessione" : "Session"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-surface3" />
              {ui.locale === "it" ? "Riposo" : "Rest"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-positive" />
              {ui.locale === "it" ? "Allenamento fatto" : "Activity done"}
            </span>
            <span className="ml-auto text-muted">
              {/* TODO i18n */}
              {ui.locale === "it" ? "Tocca un giorno per aggiungere" : "Tap a day to add an event"}
            </span>
          </div>
        </div>
      )}

      {/* tap-to-add sheet (month mode) */}
      {addDate && (
        <AddEventSheet
          date={addDate}
          today={today}
          onClose={() => setAddDate(null)}
          onSaved={() => {
            setAddDate(null);
            onEventsChanged();
          }}
        />
      )}
    </Card>
  );
}

/** A modal-ish sheet (fixed overlay) used to add a calendar event for a specific date. */
function AddEventSheet({
  date,
  today,
  onClose,
  onSaved,
}: {
  date: string;
  today: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ui = useApexUi();
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-2 sm:items-center sm:p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-[var(--radius-card)] bg-surface shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
        <div className="flex items-center justify-between border-b border-[var(--c-divider)] px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Plus size={14} className="text-primaryText" />
            <span className="text-[14px] font-semibold text-ink">
              {/* TODO i18n */}
              {ui.locale === "it" ? "Aggiungi evento" : "Add event"}
            </span>
            <span className="num text-[13px] text-muted">{fmtDate(date, ui.locale)}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface2 hover:text-ink"
            aria-label={ui.locale === "it" ? "Chiudi" : "Close"}
          >
            <X size={14} />
          </button>
        </div>
        <div className="p-5">
          <EventForm
            today={today}
            defaultDate={date}
            onClose={onClose}
            onSaved={onSaved}
          />
        </div>
      </div>
    </div>
  );
}

function MonthDayCell({
  date,
  inMonth,
  isToday,
  isPast,
  isRest,
  planStatus,
  events: dayEvents,
  hasActivity,
  onAddEvent,
}: {
  date: string;
  inMonth: boolean;
  isToday: boolean;
  isPast: boolean;
  isRest: boolean;
  planStatus: PlanStatus | null;
  events: ApexEvent[];
  hasActivity: boolean;
  onAddEvent: () => void;
}) {
  const ui = useApexUi();
  const dayNum = parseInt(date.slice(8, 10), 10);

  // status dot
  let statusDot: React.ReactNode = null;
  if (planStatus === "done") {
    statusDot = (
      <span className="flex h-3 w-3 items-center justify-center rounded-full bg-positiveSoft text-positive">
        <Check size={7} strokeWidth={3} />
      </span>
    );
  } else if (planStatus === "confirmed") {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" />;
  } else if (planStatus === "draft") {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-warning" />;
  } else if (isRest) {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-surface3" />;
  }

  return (
    <button
      type="button"
      onClick={onAddEvent}
      className={`group relative flex min-h-[58px] flex-col gap-1 bg-surface p-1.5 text-left transition-colors hover:bg-surface2 ${
        isToday ? "bg-surface2" : ""
      } ${inMonth ? "" : "opacity-40"}`}
      aria-label={`${fmtDate(date, ui.locale)} — ${ui.locale === "it" ? "aggiungi evento" : "add event"}`}
    >
      <div className="flex items-start justify-between gap-1">
        <span
          className={`num text-[12px] font-semibold leading-none ${
            isToday ? "text-primaryText" : inMonth ? "text-ink" : "text-muted"
          }`}
          style={{ fontFeatureSettings: '"tnum" 1' }}
        >
          {dayNum}
        </span>
        {statusDot}
      </div>

      {/* event dots row */}
      {dayEvents.length > 0 && (
        <div className="flex flex-wrap gap-0.5">
          {dayEvents.slice(0, 4).map((e) => {
            const tone = eventToneForKind(e.kind);
            const cls =
              tone === "alert"
                ? "bg-alert"
                : tone === "primary"
                ? "bg-primary"
                : "bg-muted";
            return (
              <span
                key={e.id}
                title={e.title}
                className={`inline-block h-1.5 w-1.5 rounded-full ${cls}`}
              />
            );
          })}
          {dayEvents.length > 4 && (
            <span className="num text-[12px] leading-none text-muted">+{dayEvents.length - 4}</span>
          )}
        </div>
      )}

      {/* activity-done indicator */}
      {hasActivity && (
        <div className="mt-auto flex items-center gap-0.5">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-positive" />
          <span className="text-[12px] leading-none text-positiveText">
            {/* TODO i18n */}
            {ui.locale === "it" ? "fatto" : "done"}
          </span>
        </div>
      )}

      {/* past-day dim overlay (no plan done) */}
      {isPast && !planStatus && !hasActivity && dayEvents.length === 0 && (
        <span className="absolute right-1 top-1 h-1 w-1 rounded-full bg-alert/40" />
      )}
    </button>
  );
}

function WeekDayCell({
  date,
  weekdayKey,
  isToday,
  isPast,
  routineSlot,
  isRest,
  event,
  planStatus,
  editing,
  onRoutineChange,
  hasActivity = false,
}: {
  date: string;
  weekdayKey: string;
  isToday: boolean;
  isPast: boolean;
  routineSlot: { title: string; start: string; discipline: string };
  isRest: boolean;
  event: ApexEvent | undefined;
  planStatus: PlanStatus | null;
  editing: boolean;
  onRoutineChange: (s: { title: string; start: string; discipline: string }) => void;
  hasActivity?: boolean;
}) {
  const t = useT();
  const ui = useApexUi();
  const dayNum = date.slice(8, 10);

  // status dot
  let statusDot: React.ReactNode = (
    <span className="inline-block h-1.5 w-1.5 rounded-full bg-surface3" />
  );
  let statusLabel = "";
  if (planStatus === "done") {
    statusDot = (
      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-positiveSoft text-positive">
        <Check size={9} strokeWidth={3} />
      </span>
    );
    statusLabel = t("training.done");
  } else if (planStatus === "confirmed") {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" />;
    statusLabel = t("training.confirmed");
  } else if (planStatus === "draft") {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-warning" />;
    statusLabel = t("train_draft");
  } else if (isRest) {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-surface3" />;
    statusLabel = t("train_rest_day");
  } else if (isPast) {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-alert/50" />;
    statusLabel = ui.locale === "it" ? "Mancato" : "Missed";
  } else {
    statusDot = <span className="inline-block h-1.5 w-1.5 rounded-full bg-surface3" />;
    statusLabel = t("training.planned");
  }

  return (
    <div
      className={`flex min-h-[112px] flex-col gap-2 bg-surface p-3 transition-colors ${
        isToday ? "bg-surface2" : ""
      } ${isPast && !planStatus ? "opacity-70" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[14px] font-medium text-muted">{t(weekdayKey)}</span>
          <span
            className={`num text-[20px] font-semibold leading-none ${
              isToday ? "text-primaryText" : "text-ink"
            }`}
            style={{ fontFeatureSettings: '"tnum" 1' }}
          >
            {dayNum}
          </span>
          {isToday && (
            <span className="text-[13px] font-medium text-primaryText">
              {ui.locale === "it" ? "oggi" : "today"}
            </span>
          )}
          {hasActivity && !isToday && (
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-positive"
              title={ui.locale === "it" ? "Attività registrata" : "Activity recorded"}
            />
          )}
        </div>
        {statusDot}
      </div>

      <Hairline className="!bg-[var(--c-divider)]" />

      {editing ? (
        <div className="space-y-1.5">
          <input
            type="text"
            value={routineSlot?.title || ""}
            onChange={(e) =>
              onRoutineChange({
                ...routineSlot,
                title: e.target.value,
              })
            }
            className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[14px] text-ink"
          />
          <input
            type="text"
            value={routineSlot?.start || ""}
            placeholder="HH:MM"
            onChange={(e) =>
              onRoutineChange({
                ...routineSlot,
                start: e.target.value,
              })
            }
            className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[14px] text-ink"
          />
        </div>
      ) : (
        <div>
          <div className="truncate text-[14px] font-semibold leading-tight text-ink2">
            {routineSlot?.title || (ui.locale === "it" ? "—" : "—")}
          </div>
          <div className="num mt-0.5 flex items-center gap-1.5 text-[13px] text-muted">
            {routineSlot?.start && <span>{routineSlot.start}</span>}
            <span>·</span>
            <span>{statusLabel}</span>
          </div>
        </div>
      )}

      {event && (
        <div className="mt-auto">
          <StatusDot
            tone={event.priority === "priority_1" || event.priority === "high" ? "watch" : "neutral"}
            label={event.title}
          />
        </div>
      )}
    </div>
  );
}

/* =========================================================== ROW 3A: Load chart */

function LoadCard({
  load,
  events,
}: {
  load: {
    series: DayLoad[];
    taperWindows: TaperWindow[];
    summary: { acute_load: number | null; chronic_load: number | null; acwr: number | null };
  } | null;
  events: ApexEvent[];
}) {
  const t = useT();
  const ui = useApexUi();

  // ChartInfoBadge text — explains what the three series mean.
  const infoText = ui.locale === "it"
    ? "Carico acuto = somma del carico di allenamento degli ultimi 7 giorni (affaticamento attuale). "
      + "Carico cronico = media mobile a 28 giorni (base di fitness). "
      + "ACWR = acuto ÷ cronico — tra 0.8 e 1.3 è la fascia ottimale."
    : "Acute load = 7-day training load (fatigue). "
      + "Chronic load = 28-day average (fitness base). "
      + "ACWR = acute ÷ chronic — 0.8–1.3 is optimal.";

  return (
    <Card>
      <Section label={t("train_load")}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-[14px] text-ink2">
            {ui.locale === "it" ? "56 giorni · banda 0.8–1.3" : "56 days · 0.8–1.3 band"}
          </div>
          <ChartInfoBadge text={infoText} />
        </div>
      </Section>
      {!load ? (
        <Loading label={ui.locale === "it" ? "Carico carico…" : "Loading load…"} />
      ) : load.series.length === 0 ? (
        <Empty title={ui.locale === "it" ? "Nessun dato" : "No data yet"} />
      ) : (
        <>
          {/* Summary row — compact numbers + StatusDot, no bordered tiles */}
          <div className="mb-5 grid grid-cols-3 gap-4">
            <LoadFact
              label={ui.locale === "it" ? "Carico acuto" : "Acute load"}
              value={fmtNum(load.summary.acute_load, 0)}
              unit="TSS"
              sub="7d"
            />
            <LoadFact
              label={ui.locale === "it" ? "Carico cronico" : "Chronic load"}
              value={fmtNum(load.summary.chronic_load, 0)}
              unit="TSS"
              sub="28d"
            />
            <div className="rounded-[var(--radius-control)] bg-surface2 px-4 py-3">
              <div className="text-[14px] text-ink2">ACWR</div>
              <div className="num mt-1 flex items-baseline gap-1 text-[28px] font-semibold text-ink">
                {fmtNum(load.summary.acwr, 2)}
              </div>
              <div className="mt-1">
                <StatusDot
                  tone={load.summary.acwr == null
                    ? "neutral"
                    : load.summary.acwr >= 0.8 && load.summary.acwr <= 1.3
                    ? "ok"
                    : load.summary.acwr > 1.5
                    ? "alert"
                    : "watch"}
                  label={load.summary.acwr == null
                    ? "—"
                    : load.summary.acwr >= 0.8 && load.summary.acwr <= 1.3
                    ? (ui.locale === "it" ? "Ottimale" : "Optimal")
                    : load.summary.acwr > 1.5
                    ? (ui.locale === "it" ? "Rischio alto" : "High risk")
                    : (ui.locale === "it" ? "Elevato" : "Elevated")}
                />
              </div>
            </div>
          </div>
          <LoadChart series={load.series} taperWindows={load.taperWindows} events={events} />

          {/* event markers strip — quick visual cue for events falling in the
              56-day window (the chart itself no longer draws the event lines
              since InteractiveComboChart doesn't accept overlay children). */}
          <EventMarkersStrip series={load.series} events={events} />
        </>
      )}
    </Card>
  );
}

/** LoadFact — a compact number for the load summary row. Surface-2 contrast
 *  only, no border, no eyebrow. */
function LoadFact({
  label,
  value,
  unit,
  sub,
}: {
  label: string;
  value: string;
  unit: string;
  sub: string;
}) {
  return (
    <div className="rounded-[var(--radius-control)] bg-surface2 px-4 py-3">
      <div className="text-[14px] text-ink2">{label}</div>
      <div className="num mt-1 flex items-baseline gap-1 text-[28px] font-semibold text-ink">
        {value}
        <span className="text-[14px] font-medium text-ink2">{unit}</span>
      </div>
      <div className="mt-1 text-[13px] text-muted">{sub}</div>
    </div>
  );
}

/** Per-bar ACWR state tone — used to colour the "ACWR state" mini-strip that
 *  runs beneath the chart. The InteractiveComboChart component takes a single
 *  BarSeries (one colour for all bars), so the spec's per-bar state-tone
 *  coloring is implemented as a separate thin strip here, where each day's
 *  ACWR state is shown as a tiny coloured cell aligned with the bar above. */
function acwrTone(acwr: number | null): "positive" | "warning" | "alert" | "primary" | "muted" {
  if (acwr == null) return "muted";
  if (acwr > 1.5) return "alert";
  if (acwr > 1.3) return "warning";
  if (acwr >= 0.8) return "positive";
  return "primary";
}

function LoadChart({
  series,
  taperWindows: _taperWindows,
  events: _events,
}: {
  series: DayLoad[];
  taperWindows: TaperWindow[];
  events: ApexEvent[];
}) {
  const ui = useApexUi();

  // Downsample if too many days — 56 bars at width 600 is fine but we cap at 56
  // anyway via the API. Categories are the dates (YYYY-MM-DD → short label).
  const categories: BarCategory[] = useMemo(
    () => series.map((s) => ({ label: s.date })),
    [series],
  );

  // Acute load bars (single series — InteractiveComboChart accepts one).
  // Colour is primary; per-bar ACWR state-tone is rendered in the strip below.
  const bars: BarSeries = {
    name: ui.locale === "it" ? "Carico acuto (7d)" : "Acute load (7d)",
    color: "var(--c-primary)",
    values: series.map((s) => s.acute),
  };

  // Two lines: chronic load (ink) + ACWR (warning). Note: InteractiveComboChart
  // uses a single shared y-scale for ALL lines, so ACWR (range ~0–2) renders
  // visually compressed at the bottom relative to chronic (~50–300). The
  // tooltip still shows the exact value per day; the ACWR state strip below
  // gives the at-a-glance visual state.
  const lines: LineSeries[] = [
    {
      name: ui.locale === "it" ? "Carico cronico (28d)" : "Chronic load (28d)",
      color: "var(--c-ink)",
      values: series.map((s) => s.chronic),
    },
    {
      name: "ACWR",
      color: "var(--c-warning)",
      values: series.map((s) => s.acwr),
    },
  ];

  // x-axis labels — short date (MM-DD). Show ~6 evenly spaced labels.
  const labelStride = Math.max(1, Math.floor(series.length / 6));

  return (
    <div className="w-full">
      <InteractiveComboChart
        categories={categories}
        bars={bars}
        lines={lines}
        height={220}
        barUnit="TSS"
        formatBarValue={(v) => (v === null ? "—" : `${v.toFixed(0)} TSS`)}
        formatLineValue={(v) => (v === null ? "—" : v.toFixed(2))}
      />

      {/* x-axis labels */}
      <div className="mt-1 flex justify-between text-[12px] text-muted">
        {series.map((s, i) =>
          i % labelStride === 0 || i === series.length - 1 ? (
            <span key={s.date} className="num">
              {s.date.slice(5)}
            </span>
          ) : null,
        )}
      </div>

      {/* per-bar ACWR state-tone strip — at-a-glance fatigue state per day */}
      <div className="mt-3">
        <div className="mb-1 text-[13px] text-muted">
          {ui.locale === "it" ? "Stato ACWR (per giorno)" : "ACWR state (per day)"}
        </div>
        <div
          className="flex h-2 w-full overflow-hidden rounded-[2px] bg-surface3"
          title={ui.locale === "it" ? "Verde = ottimale (0.8–1.3) · Giallo = alto (>1.3) · Rosso = critico (>1.5) · Blu = basso (<0.8)" : "Green = optimal (0.8–1.3) · Yellow = high (>1.3) · Red = critical (>1.5) · Blue = low (<0.8)"}
        >
          {series.map((s) => {
            const tone = acwrTone(s.acwr);
            const bg =
              tone === "alert"
                ? "var(--c-alert)"
                : tone === "warning"
                ? "var(--c-warning)"
                : tone === "positive"
                ? "var(--c-positive)"
                : tone === "primary"
                ? "var(--c-primary)"
                : "var(--c-surface3)";
            return (
              <span
                key={s.date}
                title={`${s.date} · ACWR ${s.acwr == null ? "—" : s.acwr.toFixed(2)}`}
                className="block flex-1"
                style={{ background: bg, minWidth: 1 }}
              />
            );
          })}
        </div>
      </div>

      {/* legend */}
      <div className="mt-3">
        <ChartLegend
          items={[
            { name: ui.locale === "it" ? "Carico acuto (7d)" : "Acute load (7d)", color: "var(--c-primary)" },
            { name: ui.locale === "it" ? "Carico cronico (28d)" : "Chronic load (28d)", color: "var(--c-ink)" },
            { name: "ACWR", color: "var(--c-warning)" },
            { name: ui.locale === "it" ? "Ottimale 0.8–1.3" : "Optimal 0.8–1.3", color: "var(--c-positive)" },
          ]}
        />
      </div>
    </div>
  );
}

/** Thin row listing events that fall within the loaded window, with their
 *  date + title so the user can see "what happened on this day" without the
 *  overlay lines we used to draw on the bespoke chart. */
function EventMarkersStrip({
  series,
  events,
}: {
  series: DayLoad[];
  events: ApexEvent[];
}) {
  const ui = useApexUi();
  const inWindow = events.filter((e) => series.some((s) => s.date === e.date));
  if (inWindow.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[var(--c-divider)] pt-3 text-[13px] text-muted">
      <span className="text-muted">
        {ui.locale === "it" ? "Eventi nella finestra" : "Events in window"}:
      </span>
      {inWindow.slice(0, 8).map((e) => (
        <span key={e.id} className="inline-flex items-center gap-1">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              e.priority === "priority_1" || e.priority === "high" ? "bg-alert" : "bg-primary"
            }`}
          />
          <span className="num">{e.date.slice(5)}</span>
          <span className="text-muted">·</span>
          <span className="text-ink2">{e.title}</span>
        </span>
      ))}
      {inWindow.length > 8 && (
        <span className="text-muted">+{inWindow.length - 8}</span>
      )}
    </div>
  );
}

function Legend({ color, label, opacity = 1 }: { color: string; label: string; opacity?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2 w-2 rounded-sm" style={{ background: color, opacity }} />
      {label}
    </span>
  );
}

/* =========================================================== ROW 3B: Events */

function EventsCard({
  events,
  loading,
  today,
  onChange,
}: {
  events: ApexEvent[];
  loading: boolean;
  today: string;
  onChange: () => void;
}) {
  const t = useT();
  const ui = useApexUi();

  const [showPast, setShowPast] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const upcoming = events.filter((e) => dayDiff(today, e.date) >= 0).sort((a, b) => a.date.localeCompare(b.date));
  const past = events.filter((e) => dayDiff(today, e.date) < 0).sort((a, b) => b.date.localeCompare(a.date));

  return (
    <Card>
      <Section label={t("train_events")}>
        <div className="flex items-center justify-end">
          <ApexButton
            variant="secondary"
            size="sm"
            icon={<Plus size={12} />}
            onClick={() => {
              setShowAdd(true);
              setEditingId(null);
            }}
          >
            {ui.locale === "it" ? "Aggiungi" : "Add"}
          </ApexButton>
        </div>
      </Section>

      {loading ? (
        <Loading />
      ) : upcoming.length === 0 && past.length === 0 ? (
        <Empty title={t("train_no_events")} />
      ) : (
        <div className="space-y-2">
          {showAdd && (
            <EventForm
              today={today}
              onClose={() => setShowAdd(false)}
              onSaved={() => {
                setShowAdd(false);
                onChange();
              }}
            />
          )}

          {upcoming.map((e) =>
            editingId === e.id ? (
              <EventForm
                key={e.id}
                event={e}
                today={today}
                onClose={() => setEditingId(null)}
                onSaved={() => {
                  setEditingId(null);
                  onChange();
                }}
              />
            ) : (
              <EventRow key={e.id} event={e} today={today} onEdit={() => setEditingId(e.id)} onDeleted={onChange} />
            )
          )}

          {past.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setShowPast((v) => !v)}
                className="flex w-full items-center justify-between pt-2 text-[14px] text-muted hover:text-ink"
              >
                <span className="text-[14px] font-medium">
                  {ui.locale === "it" ? `Passati (${past.length})` : `Past (${past.length})`}
                </span>
                {showPast ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {showPast &&
                past.map((e) => (
                  <EventRow key={e.id} event={e} today={today} past onEdit={() => setEditingId(e.id)} onDeleted={onChange} />
                ))}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

function EventRow({
  event,
  today,
  past = false,
  onEdit,
  onDeleted,
}: {
  event: ApexEvent;
  today: string;
  past?: boolean;
  onEdit: () => void;
  onDeleted: () => void;
}) {
  const t = useT();
  const ui = useApexUi();
  const days = dayDiff(today, event.date);
  const isPriority = event.priority === "priority_1" || event.priority === "high";
  const taper = event.taperDays ?? (isPriority ? 5 : 3);
  const inTaper = !past && days >= 0 && days < taper;
  const taperDay = taper - days;

  return (
    <div className="rounded-[var(--radius-card)] bg-surface2 p-4">
      <div className="flex items-start gap-3">
        <div className="num flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-[var(--radius-control)] bg-surface text-ink">
          <span className="text-[13px] leading-none text-muted">
            {event.date.slice(5, 7)}
          </span>
          <span className="text-[18px] font-bold leading-none">{event.date.slice(8, 10)}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="truncate text-[16px] font-semibold text-ink">{event.title}</div>
            <div className="flex shrink-0 items-center gap-1">
              {isPriority && (
                <StatusDot tone="watch" label={ui.locale === "it" ? "Priorità" : "Priority"} />
              )}
              <button
                type="button"
                onClick={onEdit}
                className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-surface3 hover:text-ink"
                aria-label={t("train_edit_event")}
              >
                <Edit2 size={14} />
              </button>
              <ConfirmPopover
                message={ui.locale === "it" ? "Eliminare questo evento?" : "Delete this event?"}
                onConfirm={async () => {
                  await fetch(`/api/events/${event.id}`, { method: "DELETE" });
                  onDeleted();
                }}
                onCancel={() => {}}
                confirmLabel={ui.locale === "it" ? "Elimina" : "Delete"}
                cancelLabel={ui.locale === "it" ? "Annulla" : "Cancel"}
              >
                <button
                  type="button"
                  className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-alertSoft hover:text-alertText"
                  aria-label={ui.locale === "it" ? "Elimina" : "Delete"}
                >
                  <Trash2 size={14} />
                </button>
              </ConfirmPopover>
            </div>
          </div>
          <div className="num mt-1 flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
            <span>{event.kind}</span>
            <span>·</span>
            <span>
              {past
                ? ui.locale === "it"
                  ? `${Math.abs(days)} gg fa`
                  : `${Math.abs(days)} d ago`
                : days === 0
                ? ui.locale === "it"
                  ? "oggi"
                  : "today"
                : ui.locale === "it"
                ? `tra ${days} gg`
                : `in ${days} d`}
            </span>
            {event.taperDays != null && (
              <>
                <span>·</span>
                <span>
                  {t("train_taper_days")}: {event.taperDays}
                </span>
              </>
            )}
          </div>
          {inTaper && (
            <div className="mt-2">
              <StatusDot
                tone="watch"
                label={t("train_taper_progress", { n: taperDay, total: taper })}
              />
            </div>
          )}
          {event.note && (
            <div className="mt-1 text-[14px] italic leading-snug text-muted">{event.note}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function EventForm({
  event,
  today,
  defaultDate,
  onClose,
  onSaved,
}: {
  event?: ApexEvent;
  today: string;
  /** Optional pre-filled date used by the month-calendar tap-to-add flow.
   *  Ignored when `event` is provided (editing an existing event). */
  defaultDate?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ui = useApexUi();
  const [title, setTitle] = useState(event?.title || "");
  const [kind, setKind] = useState(event?.kind || "session");
  const [date, setDate] = useState(event?.date || defaultDate || today);
  const [priority, setPriority] = useState(event?.priority || "normal");
  const [taperDays, setTaperDays] = useState<number>(event?.taperDays ?? 5);
  const [note, setNote] = useState(event?.note || "");
  const [saving, setSaving] = useState(false);

  // When kind changes, pre-fill priority + taper days per plan §2:
  // race/competition/enduro/ski → priority 1 + 5 taper days; else priority normal + 3 taper days.
  useEffect(() => {
    if (event) return; // don't override when editing existing
    const isPriority = ["race", "competition", "enduro", "ski"].includes(kind);
    setPriority(isPriority ? "priority_1" : "normal");
    setTaperDays(isPriority ? 5 : 3);
  }, [kind, event]);

  async function save() {
    setSaving(true);
    try {
      if (event) {
        await fetch(`/api/events/${event.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, kind, date, priority, taperDays, note }),
        });
      } else {
        await fetch("/api/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, kind, date, priority, taperDays, note }),
        });
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  const kindOptions: { value: string; label: string }[] = [
    { value: "session", label: ui.locale === "it" ? "Sessione" : "Session" },
    { value: "race", label: ui.locale === "it" ? "Gara" : "Race" },
    { value: "competition", label: ui.locale === "it" ? "Competizione" : "Competition" },
    { value: "enduro", label: "Enduro" },
    { value: "ski", label: ui.locale === "it" ? "Sci" : "Ski" },
    { value: "training_camp", label: ui.locale === "it" ? "Ritiro" : "Camp" },
  ];

  return (
    <div className="rounded-[var(--radius-card)] bg-surface2 p-4">
      <div className="space-y-2.5">
        <div>
          <div className="mb-1 text-[14px] font-medium text-ink2">
            {ui.locale === "it" ? "Titolo" : "Title"}
          </div>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
            placeholder="Marathon, ski trip…"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="mb-1 text-[14px] font-medium text-ink2">Kind</div>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
            >
              {kindOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-1 text-[14px] font-medium text-ink2">
              {ui.locale === "it" ? "Data" : "Date"}
            </div>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <div className="mb-1 text-[14px] font-medium text-ink2">
              {ui.locale === "it" ? "Priorità" : "Priority"}
            </div>
            <Segmented
              value={priority}
              onChange={(v) => setPriority(v)}
              options={[
                { value: "normal", label: ui.locale === "it" ? "Normale" : "Normal" },
                { value: "priority_1", label: ui.locale === "it" ? "Alta" : "High" },
              ]}
            />
          </div>
          <div>
            <div className="mb-1 text-[14px] font-medium text-ink2">
              {ui.locale === "it" ? "Taper (gg)" : "Taper (d)"}
            </div>
            <Stepper value={taperDays} onChange={setTaperDays} step={1} min={0} max={21} />
          </div>
        </div>
        <div>
          <div className="mb-1 text-[14px] font-medium text-ink2">{ui.locale === "it" ? "Note" : "Notes"}</div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
            rows={2}
          />
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <ApexButton variant="ghost" size="sm" onClick={onClose}>
            {ui.locale === "it" ? "Annulla" : "Cancel"}
          </ApexButton>
          <ApexButton size="sm" onClick={save} disabled={saving || !title || !date}>
            {saving
              ? ui.locale === "it"
                ? "Salvo…"
                : "Saving…"
              : event
              ? ui.locale === "it"
                ? "Aggiorna"
                : "Update"
              : ui.locale === "it"
              ? "Aggiungi"
              : "Add"}
          </ApexButton>
        </div>
      </div>
    </div>
  );
}

/* =========================================================== ROW 4: Feedback */

const LOCAL_FEEDBACK_KEY = "training.feedback.local";

function readLocalFeedback(userId: number): FeedbackEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(`apex.u${userId}.${LOCAL_FEEDBACK_KEY}`);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

function writeLocalFeedback(userId: number, list: FeedbackEntry[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`apex.u${userId}.${LOCAL_FEEDBACK_KEY}`, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

function FeedbackCard({
  today,
  history,
  loading,
  onSubmitted,
}: {
  today: string;
  history: FeedbackEntry[];
  loading: boolean;
  onSubmitted: () => void;
}) {
  const t = useT();
  const ui = useApexUi();

  const [rpe, setRpe] = useState<number | null>(null);
  const [soreness, setSoreness] = useState<number | null>(null);
  const [injuryFlag, setInjuryFlag] = useState(false);
  const [bodyArea, setBodyArea] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  function reset() {
    setRpe(null);
    setSoreness(null);
    setInjuryFlag(false);
    setBodyArea("");
    setNotes("");
  }

  async function submit() {
    if (rpe == null && soreness == null && !notes) return;
    setSaving(true);
    try {
      // Phase 0 fix #2 — send the full structured payload (not just notes).
      await fetch("/api/gym/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rpe,
          soreness,
          injuryFlag,
          bodyArea: injuryFlag ? bodyArea : null,
          notes: notes || null,
        }),
      });
      // store locally (route is not persistent — see route.ts header)
      const local = readLocalFeedback(me.user_id);
      const entry: FeedbackEntry = {
        id: Date.now(),
        date: today,
        rpe: rpe ?? 0,
        soreness: soreness ?? 0,
        injuryFlag,
        bodyArea: injuryFlag ? bodyArea : null,
        notes: notes || null,
      };
      writeLocalFeedback(me.user_id, [entry, ...local].slice(0, 30));
      reset();
      onSubmitted();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <Section label={t("train_feedback")}>
        <div className="flex items-center justify-end">
          <span className="num text-[14px] text-muted">
            {ui.locale === "it" ? "oggi" : "today"} · {fmtDate(today, ui.locale)}
          </span>
        </div>
      </Section>

      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-2 text-[14px] font-medium text-ink2">{t("train_rpe_label")}</div>
            <div className="flex flex-wrap gap-1.5">
              {Array.from({ length: 10 }, (_, i) => i + 1).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRpe(rpe === r ? null : r)}
                  className={`num h-7 rounded-[var(--radius-control)] px-2 text-[14px] font-semibold transition-colors ${
                    rpe === r
                      ? "bg-primarySoft text-primaryText"
                      : "bg-surface2 text-muted hover:bg-surface3 hover:text-ink2"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-2 text-[14px] font-medium text-ink2">{t("train_soreness")}</div>
            <div className="flex flex-wrap gap-1.5">
              {Array.from({ length: 5 }, (_, i) => i + 1).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSoreness(soreness === s ? null : s)}
                  className={`num h-7 rounded-[var(--radius-control)] px-2.5 text-[14px] font-semibold transition-colors ${
                    soreness === s
                      ? "bg-primarySoft text-primaryText"
                      : "bg-surface2 text-muted hover:bg-surface3 hover:text-ink2"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        <Hairline className="!bg-[var(--c-divider)]" />

        <div>
          <label className="flex cursor-pointer items-center gap-2.5">
            <input
              type="checkbox"
              checked={injuryFlag}
              onChange={(e) => setInjuryFlag(e.target.checked)}
              className="h-4 w-4 rounded border-hairline2"
            />
            <span className="text-[14px] font-medium text-ink2">
              {t("train_injury_flag")}
            </span>
          </label>
          {injuryFlag && (
            <div className="mt-2.5">
              <div className="mb-1.5 text-[14px] font-medium text-ink2">{t("train_body_area")}</div>
              <input
                type="text"
                value={bodyArea}
                onChange={(e) => setBodyArea(e.target.value)}
                placeholder="Knee, lower back, right shoulder…"
                className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
              />
            </div>
          )}
        </div>

        <div>
          <div className="mb-1.5 text-[14px] font-medium text-ink2">{t("train_notes")}</div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1.5 text-[14px] text-ink"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <ApexButton onClick={submit} disabled={saving || (rpe == null && soreness == null && !notes)}>
            {saving
              ? (ui.locale === "it" ? "Salvo…" : "Saving…")
              : (ui.locale === "it" ? "Salva" : "Save")}
          </ApexButton>
          <span className="text-[13px] text-muted">
            {/* TODO i18n: train_feedback_local_hint */}
            {ui.locale === "it"
              ? "Salvato in questo dispositivo (nessun modello Feedback nello schema)."
              : "Saved on this device (no Feedback model in schema yet)."}
          </span>
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 text-[14px] font-medium text-ink2">
          {ui.locale === "it" ? "Cronologia" : "History"}
        </div>
        {loading ? (
          <Loading />
        ) : history.length === 0 ? (
          <Empty title={t("train_no_feedback")} />
        ) : (
          <ul className="divide-y divide-[var(--c-divider)]">
            {history.map((f) => (
              <li
                key={f.id}
                className="flex flex-wrap items-center gap-3 py-2.5 text-[14px]"
              >
                <span className="num shrink-0 text-muted">{fmtDate(f.date, ui.locale)}</span>
                <div className="flex flex-wrap items-center gap-3">
                  {f.rpe > 0 && <span className="text-ink2">RPE {f.rpe}</span>}
                  {f.soreness > 0 && (
                    <span className="text-ink2">
                      {ui.locale === "it" ? "Indol." : "Sore"} {f.soreness}
                    </span>
                  )}
                  {f.injuryFlag && (
                    <StatusDot tone="alert" label={f.bodyArea || (ui.locale === "it" ? "Infortunio" : "Injury")} />
                  )}
                  {f.notes && <span className="text-muted">· {f.notes}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
