"use client";

/**
 * Apex Health — Training Plan & Load page.
 *
 * Route purpose: "What am I planning and how am I progressing?"
 *
 * Composition:
 *  - PageHeader with a 14-day forward range subtitle.
 *  - Load summary row (3 StatPods): ACWR / Freshness / 7d Load.
 *  - 21-day calendar (last 7 days + next 14 days) — distinguishes RECURRING
 *    ROUTINE templates (status="planned") from DATE-SPECIFIC CONFIRMED PLANS
 *    (status="confirmed"), and from done/skipped history.
 *  - Side panel: next upcoming session + status legend.
 *  - Gym session surface: a fast, phone-friendly workout runner with a
 *    live rest-timer state machine (idle → active → rest → active… → done).
 *
 * Coherence law: every visual primitive comes from `@/components/apex/kit`.
 * No new card/badge variants are invented here.
 */

import { useEffect, useMemo, useState } from "react";
import { Check, X } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { getTrainingSchedule, gymSessions, overview } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  StatPod,
  Badge,
  SportIcon,
  SectionHeader,
  Empty,
  ApexButton,
  Hairline,
  SourcePill,
} from "@/components/apex/kit";
import { fmtDate, fmtNum, friendlyDiscipline } from "@/lib/apex/format";
import type { GymSession, TrainingPlanItem } from "@/lib/apex/types";

/* --------------------------------------------------------------- tones */

const INTENSITY_TONE: Record<
  NonNullable<TrainingPlanItem["intensity"]>,
  string
> = {
  easy: "text-muted",
  moderate: "text-primaryText",
  hard: "text-alertText",
  threshold: "text-warningText",
  recovery: "text-positiveText",
};

const STATUS_DOT: Record<TrainingPlanItem["status"], string> = {
  planned: "bg-surface3",
  confirmed: "bg-primary",
  done: "bg-positive",
  skipped: "bg-alert",
};

/* ----------------------------------------------------------- helpers */

function startOfDay(iso: string): Date {
  const d = new Date(iso);
  d.setHours(0, 0, 0, 0);
  return d;
}

function isToday(iso: string): boolean {
  const d = startOfDay(iso);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return d.getTime() === now.getTime();
}

function isPast(iso: string): boolean {
  const d = startOfDay(iso);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return d.getTime() < now.getTime();
}

function weekdayShort(iso: string, locale: "en" | "it"): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(locale === "it" ? "it-IT" : "en-GB", {
    weekday: "short",
  });
}

function dayNum(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return String(d.getDate()).padStart(2, "0");
}

function fmtMSS(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/* ----------------------------------------------------------- main page */

export function TrainingPage() {
  const t = useT();
  const ui = useApexUi();

  const schedule = useMemo(() => getTrainingSchedule(14, 7), []);
  const todayIso = new Date();
  todayIso.setHours(0, 0, 0, 0);
  const startRangeIso = new Date(todayIso);
  const endRangeIso = new Date(todayIso);
  endRangeIso.setDate(endRangeIso.getDate() + 14);
  const subtitle = `${fmtDate(startRangeIso.toISOString(), ui.locale)} – ${fmtDate(
    endRangeIso.toISOString(),
    ui.locale
  )} · ${ui.locale === "it" ? "prossimi 14 giorni" : "next 14 days"}`;

  // next planned gym session
  const plannedGym = useMemo(
    () => gymSessions.find((s) => s.status === "planned") ?? null,
    []
  );

  return (
    <div className="mx-auto max-w-[1240px] pb-16">
      <PageHeader title={t("training.title")} subtitle={subtitle} />

      {/* load summary row */}
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatPod
          label={t("training.acwr_title")}
          value={fmtNum(overview.acwr, 2)}
          unit="ratio"
          tone={
            overview.acwr === null
              ? "ink"
              : overview.acwr >= 0.8 && overview.acwr <= 1.3
              ? "ink"
              : overview.acwr > 1.3
              ? "alert"
              : "primary"
          }
          sub={`${t("overview.optimal_window")} 0.80 – 1.30`}
        />
        <StatPod
          label={t("training.freshness_title")}
          value={
            overview.chronic_load !== null && overview.acute_load !== null
              ? fmtNum(overview.chronic_load - overview.acute_load, 0)
              : "—"
          }
          unit="load"
          tone={
            overview.chronic_load !== null && overview.acute_load !== null
              ? overview.chronic_load - overview.acute_load >= 0
                ? "ink"
                : "alert"
              : "ink"
          }
          sub={`${fmtNum(overview.chronic_load, 0)} chronic · ${fmtNum(
            overview.acute_load,
            0
          )} acute`}
        />
        <StatPod
          label={t("overview.acute_load")}
          value={fmtNum(overview.training_load_7d, 0)}
          unit="load"
          tone="ink"
          sub={`${fmtNum(overview.chronic_load, 0)} chronic`}
        />
      </div>

      {/* calendar + side panel */}
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Calendar schedule={schedule} />
        </div>
        <div className="lg:col-span-4">
          <SidePanel schedule={schedule} plannedGymId={plannedGym?.id ?? null} />
        </div>
      </div>

      {/* gym session surface */}
      <div className="mt-6">
        <GymSessionSurface session={plannedGym} />
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- calendar */

function Calendar({ schedule }: { schedule: TrainingPlanItem[] }) {
  const t = useT();
  const ui = useApexUi();

  return (
    <Card pad={false} className="overflow-hidden">
      <div className="p-4 pb-0">
        <SectionHeader
          eyebrow={
            ui.locale === "it"
              ? "Ultimi 7 · Prossimi 14"
              : "Last 7 · Next 14"
          }
          title={t("training.calendar_title")}
          right={
            <span className="num text-[11px] text-faint">
              {schedule.length}
              {ui.locale === "it" ? " giorni" : " days"}
            </span>
          }
        />
      </div>
      <div className="grid grid-cols-1 gap-px border-t border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-7">
        {schedule.map((item) => (
          <DayCell key={item.id} item={item} />
        ))}
      </div>
    </Card>
  );
}

function DayCell({ item }: { item: TrainingPlanItem }) {
  const t = useT();
  const ui = useApexUi();
  const today = isToday(item.date);
  const past = isPast(item.date);

  const intensity = item.intensity;
  const intensityTone = intensity ? INTENSITY_TONE[intensity] : "text-muted";
  const intensityLabel = intensity ? t(`training.intensity_${intensity}`) : "";

  // status badge
  let statusBadge: React.ReactNode = null;
  if (item.status === "confirmed") {
    statusBadge = (
      <Badge tone="primary" dot>
        {t("training.confirmed_plan")}
      </Badge>
    );
  } else if (item.status === "planned") {
    statusBadge = (
      <Badge tone="neutral" dot>
        {t("training.routine_template")}
      </Badge>
    );
  } else if (item.status === "done") {
    statusBadge = (
      <Badge tone="positive" dot>
        {t("training.done")}
      </Badge>
    );
  }

  // status indicator (dot or check/x)
  let statusIndicator: React.ReactNode = (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_DOT[item.status]}`}
    />
  );
  if (item.status === "done") {
    statusIndicator = (
      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-positiveSoft text-positive">
        <Check size={9} strokeWidth={3} />
      </span>
    );
  } else if (item.status === "skipped") {
    statusIndicator = (
      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-alertSoft text-alert">
        <X size={9} strokeWidth={3} />
      </span>
    );
  }

  return (
    <div
      className={`group relative flex min-h-[112px] flex-col gap-2 bg-surface p-3 transition-colors ${
        today ? "bg-surface2" : ""
      } ${past ? "opacity-70" : ""} hover:bg-surface2`}
    >
      {/* top row: weekday + status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="mono eyebrow !text-[10px] !tracking-[0.08em]">
            {weekdayShort(item.date, ui.locale)}
          </span>
          <span
            className={`num mono text-[20px] font-semibold leading-none ${
              today ? "text-primaryText" : "text-ink"
            }`}
            style={{ fontFeatureSettings: '"tnum" 1' }}
          >
            {dayNum(item.date)}
          </span>
          {today && (
            <span className="eyebrow !text-[9px] !tracking-[0.08em] text-primaryText">
              {ui.locale === "it" ? "oggi" : "today"}
            </span>
          )}
        </div>
        {statusIndicator}
      </div>

      <Hairline className="!bg-hairline/60" />

      {/* title + sport icon */}
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 text-muted">
          <SportIcon discipline={item.discipline} size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold leading-tight text-ink2">
            {item.title}
          </div>
          <div className="num mt-0.5 flex items-center gap-1.5 text-[10px] text-faint">
            {item.duration_min != null && (
              <span>{fmtNum(item.duration_min, 0)} min</span>
            )}
            {intensityLabel && (
              <>
                <span>·</span>
                <span className={intensityTone}>{intensityLabel}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* badge row */}
      {statusBadge && (
        <div className="mt-auto pt-1">
          {statusBadge}
          {item.note && item.status === "confirmed" && (
            <div className="num mt-1 text-[10px] italic leading-tight text-faint">
              {item.note}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- side panel */

function SidePanel({
  schedule,
  plannedGymId,
}: {
  schedule: TrainingPlanItem[];
  plannedGymId: number | null;
}) {
  const t = useT();
  const ui = useApexUi();

  // next upcoming confirmed or planned session (prefer non-rest)
  const nextSession = useMemo(() => {
    const todayIso = new Date();
    todayIso.setHours(0, 0, 0, 0);
    const upcoming = schedule
      .filter(
        (i) =>
          !isPast(i.date) &&
          (i.status === "planned" || i.status === "confirmed")
      )
      .sort((a, b) => a.date.localeCompare(b.date));
    return (
      upcoming.find((i) => i.type !== "rest") ?? upcoming[0] ?? null
    );
  }, [schedule]);

  const intensity = nextSession?.intensity;
  const intensityTone = intensity ? INTENSITY_TONE[intensity] : "text-muted";
  const intensityLabel = intensity ? t(`training.intensity_${intensity}`) : "";

  return (
    <div className="flex flex-col gap-4">
      {/* next session */}
      <Card>
        <CardHeader eyebrow={t("training.next_session_title")} />
        {nextSession ? (
          <div>
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText">
                <SportIcon discipline={nextSession.discipline} size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold leading-tight text-ink">
                  {nextSession.title}
                </div>
                <div className="num mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                  <span>{fmtDate(nextSession.date, ui.locale)}</span>
                  <span>·</span>
                  <span>
                    {friendlyDiscipline(nextSession.discipline, ui.locale)}
                  </span>
                  {nextSession.duration_min != null && (
                    <>
                      <span>·</span>
                      <span>{fmtNum(nextSession.duration_min, 0)} min</span>
                    </>
                  )}
                  {intensityLabel && (
                    <>
                      <span>·</span>
                      <span className={intensityTone}>{intensityLabel}</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {nextSession.status === "confirmed" ? (
                <Badge tone="primary" dot>
                  {t("training.confirmed_plan")}
                </Badge>
              ) : (
                <Badge tone="neutral" dot>
                  {t("training.routine_template")}
                </Badge>
              )}
            </div>

            {nextSession.note && (
              <div className="num mt-3 rounded-[var(--radius-control)] bg-surface2 px-2.5 py-2 text-[11px] italic leading-snug text-muted">
                {nextSession.note}
              </div>
            )}

            {nextSession.discipline === "strength" && plannedGymId != null && (
              <div className="mt-3">
                <ApexButton
                  variant="secondary"
                  size="md"
                  className="w-full"
                  onClick={() => {
                    ui.setActiveGymSession(plannedGymId);
                    // scroll to gym section
                    setTimeout(() => {
                      const el = document.getElementById("apex-gym-session");
                      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                    }, 0);
                  }}
                >
                  {t("training.open_gym")}
                </ApexButton>
              </div>
            )}
          </div>
        ) : (
          <Empty title={t("training.no_active_session")} />
        )}
      </Card>

      {/* legend */}
      <Card>
        <CardHeader eyebrow={t("training.plan_legend")} />
        <div className="grid grid-cols-2 gap-2.5">
          <LegendRow tone="muted" label={t("training.planned")} />
          <LegendRow tone="primary" label={t("training.confirmed")} />
          <LegendRow tone="positive" label={t("training.done")} />
          <LegendRow tone="rest" label={t("training.rest")} />
          <LegendRow tone="alert" label={ui.locale === "it" ? "Saltato" : "Skipped"} />
          <LegendRow tone="warning" label={t("training.race")} />
        </div>
      </Card>
    </div>
  );
}

function LegendRow({
  tone,
  label,
}: {
  tone: "muted" | "primary" | "positive" | "alert" | "warning" | "rest";
  label: string;
}) {
  const dotCls =
    tone === "muted"
      ? "bg-surface3"
      : tone === "primary"
      ? "bg-primary"
      : tone === "positive"
      ? "bg-positive"
      : tone === "alert"
      ? "bg-alert"
      : tone === "warning"
      ? "bg-warning"
      : "bg-transparent border border-hairline2";
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted">
      <span className={`inline-block h-2 w-2 rounded-full ${dotCls}`} />
      <span className="truncate">{label}</span>
    </div>
  );
}

/* ----------------------------------------------------------- gym session */

type GymMode = "idle" | "active" | "rest" | "complete";

function GymSessionSurface({ session }: { session: GymSession | null }) {
  const t = useT();
  const ui = useApexUi();

  // session runner state
  const [mode, setMode] = useState<GymMode>("idle");
  const [exerciseIdx, setExerciseIdx] = useState(0);
  const [setIdx, setSetIdx] = useState(0); // 0-based current set index
  const [restRemaining, setRestRemaining] = useState(0);

  function startSession() {
    setMode("active");
    setExerciseIdx(0);
    setSetIdx(0);
    setRestRemaining(0);
  }

  function startRest() {
    const ex = session?.exercises[exerciseIdx];
    if (!ex) return;
    setRestRemaining(ex.rest_s);
    setMode("rest");
  }

  function skipRest() {
    setRestRemaining(0);
    advanceAfterRest();
  }

  function advanceAfterRest() {
    if (!session) return;
    const ex = session.exercises[exerciseIdx];
    if (!ex) return;
    // advance set, then exercise
    if (setIdx + 1 < ex.sets) {
      setSetIdx((s) => s + 1);
      setMode("active");
      return;
    }
    // last set of this exercise done → next exercise
    if (exerciseIdx + 1 < session.exercises.length) {
      setExerciseIdx((i) => i + 1);
      setSetIdx(0);
      setMode("active");
    } else {
      // session complete
      setMode("complete");
    }
  }

  // timer effect
  useEffect(() => {
    if (mode !== "rest") return;
    if (restRemaining <= 0) {
      // advance to next set / exercise
      advanceAfterRest();
      return;
    }
    const id = window.setInterval(() => {
      setRestRemaining((s) => s - 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [mode, restRemaining]);

  if (!session) {
    return (
      <Card>
        <SectionHeader eyebrow={t("training.gym_session_title")} />
        <Empty title={t("training.no_active_session")} />
      </Card>
    );
  }

  const totalSets = session.exercises.reduce((acc, e) => acc + e.sets, 0);
  const completedSets =
    mode === "idle"
      ? 0
      : session.exercises
          .slice(0, exerciseIdx)
          .reduce((acc, e) => acc + e.sets, 0) + setIdx;

  return (
    <Card pad={false} className="overflow-hidden">
      <div id="apex-gym-session" />
      <div className="p-4">
        <SectionHeader
          eyebrow={t("training.gym_session_title")}
          title={session.title}
          right={
            <div className="flex items-center gap-2">
              <SourcePill>{fmtDate(session.date)}</SourcePill>
              {mode === "idle" && (
                <ApexButton size="sm" onClick={startSession}>
                  {t("training.start_session")}
                </ApexButton>
              )}
              {mode === "complete" && (
                <Badge tone="positive" dot>
                  {t("training.done")}
                </Badge>
              )}
            </div>
          }
        />

        {/* active runner progress bar */}
        {mode !== "idle" && (
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="eyebrow">
                {mode === "complete"
                  ? t("training.done")
                  : ui.locale === "it"
                  ? "Avanzamento"
                  : "Progress"}
              </span>
              <span className="num text-[11px] text-faint">
                {mode === "complete"
                  ? t("training.done")
                  : `${completedSets} / ${totalSets}`}
              </span>
            </div>
            <div className="num h-1.5 w-full overflow-hidden rounded-full bg-surface3">
              <div
                className="bg-primary transition-all"
                style={{
                  width: `${
                    mode === "complete"
                      ? 100
                      : (completedSets / Math.max(totalSets, 1)) * 100
                  }%`,
                }}
              />
            </div>
          </div>
        )}

        {/* completion banner */}
        {mode === "complete" && (
          <div className="mb-4 rounded-[var(--radius-control)] border border-positive/40 bg-positiveSoft px-3 py-2.5 text-[12px] font-medium text-positiveText">
            {ui.locale === "it"
              ? "Sessione completata. Recupero attivo consigliato."
              : "Session complete. Active recovery recommended."}
          </div>
        )}

        {/* rest timer big display */}
        {mode === "rest" && (
          <RestTimer
            remaining={restRemaining}
            onSkip={skipRest}
          />
        )}
      </div>

      {/* exercise list */}
      <div className="border-t border-hairline">
        {session.exercises.map((ex, idx) => {
          const isActive =
            mode === "active" && idx === exerciseIdx;
          const isComplete =
            mode === "complete" || idx < exerciseIdx;
          return (
            <ExerciseRow
              key={ex.id}
              num={idx + 1}
              name={ex.name}
              muscleGroup={ex.muscle_group}
              sets={ex.sets}
              reps={ex.reps}
              weightKg={ex.weight_kg}
              restS={ex.rest_s}
              notes={ex.notes}
              active={isActive}
              complete={isComplete}
              currentSet={isActive ? setIdx + 1 : null}
            />
          );
        })}
      </div>

      {/* footer actions during active session */}
      {mode === "active" && (
        <div className="border-t border-hairline bg-surface2 p-3">
          <ApexButton
            size="lg"
            className="w-full"
            onClick={startRest}
          >
            {t("training.start_rest")}
          </ApexButton>
        </div>
      )}
    </Card>
  );
}

/* ----------------------------------------------------- exercise row */

function ExerciseRow({
  num,
  name,
  muscleGroup,
  sets,
  reps,
  weightKg,
  restS,
  notes,
  active,
  complete,
  currentSet,
}: {
  num: number;
  name: string;
  muscleGroup: string;
  sets: number;
  reps: string;
  weightKg: number | null;
  restS: number;
  notes: string | null;
  active: boolean;
  complete: boolean;
  currentSet: number | null;
}) {
  const t = useT();
  const ui = useApexUi();
  return (
    <div
      className={`flex flex-col gap-3 border-b border-hairline p-4 last:border-b-0 sm:flex-row sm:items-center sm:gap-4 ${
        active ? "bg-primarySoft/50" : complete ? "opacity-50" : ""
      }`}
    >
      {/* number / status */}
      <div className="flex items-center gap-3 sm:w-10">
        <span
          className={`num mono flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-[12px] font-semibold ${
            active
              ? "bg-primary text-white"
              : complete
              ? "bg-positiveSoft text-positive"
              : "bg-surface3 text-muted"
          }`}
        >
          {complete ? <Check size={12} strokeWidth={3} /> : num}
        </span>
      </div>

      {/* exercise name + muscle group */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold leading-tight text-ink">
            {name}
          </span>
          {active && currentSet != null && (
            <Badge tone="primary">
              {ui.locale === "it" ? "Serie" : "Set"} {currentSet}/{sets}
            </Badge>
          )}
        </div>
        <div className="eyebrow !text-[10px] mt-1">{muscleGroup}</div>
        {notes && (
          <div className="mt-1.5 text-[11px] italic leading-snug text-muted">
            {notes}
          </div>
        )}
      </div>

      {/* stats */}
      <div className="flex items-end gap-4 sm:gap-5">
        <Stat label={t("training.sets_reps")} value={`${sets} × ${reps}`} />
        <Stat
          label={t("training.weight_kg")}
          value={weightKg != null ? fmtNum(weightKg, 1) : "—"}
          unit="kg"
        />
        <Stat label={t("training.rest_timer")} value={fmtMSS(restS)} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="eyebrow !text-[9px] !tracking-[0.06em]">{label}</div>
      <div className="num mono text-[14px] font-semibold leading-none text-ink">
        {value}
        {unit && <span className="ml-1 text-[10px] font-medium text-muted">{unit}</span>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------- rest timer */

function RestTimer({
  remaining,
  onSkip,
}: {
  remaining: number;
  onSkip: () => void;
}) {
  const t = useT();
  return (
    <div className="mb-2 rounded-[var(--radius-card)] border border-primary/40 bg-primarySoft/40 px-4 py-5 text-center">
      <div className="eyebrow text-primaryText">{t("training.rest_timer")}</div>
      <div
        className="num mono mt-2 text-[56px] font-bold leading-none text-ink sm:text-[72px]"
        style={{ fontFeatureSettings: '"tnum" 1' }}
      >
        {fmtMSS(remaining)}
      </div>
      <div className="mt-4">
        <ApexButton
          variant="secondary"
          size="lg"
          className="w-full sm:w-auto"
          onClick={onSkip}
        >
          {t("training.skip_rest")}
        </ApexButton>
      </div>
    </div>
  );
}
