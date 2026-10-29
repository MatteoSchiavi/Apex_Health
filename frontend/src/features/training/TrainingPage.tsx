import { TrainingSections } from "./TrainingSections";
/**
 * Training Plan & Load — event calendar (AI-aware: race/ski/sail events
 * drive the gym tapper), the ACWR load chart, and the gym prescription with
 * session execution (next exercise / set logging / rest timer) fed by the
 * /coach/gym APIs.
 *
 * Contracts mirror the backend exactly (app/api/coach.py + queries/gym_detail.py):
 *  - events: {id,title,kind,starts_at,ends_at,priority,taper_days,notes,bucket}
 *  - GET /gym/plan/{day} → {date, plan: PlanView|null, template}
 *  - POST /gym/session/{plan_id}/log {gym_day_exercise_id,set_number,reps_done,weight_kg}
 *  - POST /gym/feedback {date,activity_kind,rpe?,soreness?,injury_flag,notes?}
 */

import { YourDay } from "../athlete/YourDay";
import { LifeEvents } from "../athlete/LifeEvents";
import { TrainingPlanWorkspace } from "../athlete/TrainingPlanWorkspace";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, ChevronRight, Dumbbell } from "lucide-react";
import { api, ApiError, type Overview } from "../../app/api";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Input,
  Loading,
  Select,
} from "../../components/kit";
import { TrendChart } from "../../components/charts/TrendChart";
import { Tabs } from "../../components/Tabs";
import { localDay } from "../../components/data";
import { useUi } from "../../app/stores/ui";

/* ------------------------------------------------------------- event types */

interface EventOut {
  id: number;
  title: string;
  kind: string;
  starts_at: string;
  ends_at: string | null;
  priority: number;
  taper_days: number;
  notes: string | null;
  bucket: string;
}

const EVENT_KINDS = [
  "race",
  "competition",
  "ride",
  "run",
  "ski",
  "enduro",
  "sailing",
  "training_camp",
  "gym",
  "other",
] as const;
type EventKind = (typeof EVENT_KINDS)[number];

const HIGH_PRIORITY_KINDS: readonly string[] = [
  "race",
  "competition",
  "enduro",
  "ski",
];

function todayIso(): string {
  return localDay(useUi.getState().me?.timezone);
}

function AddEvent({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<EventKind>("race");
  const [date, setDate] = useState(todayIso());
  const [notes, setNotes] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.post("/events", {
        title,
        kind,
        starts_at: `${date}T12:00:00Z`,
        priority: HIGH_PRIORITY_KINDS.includes(kind) ? 1 : 2,
        taper_days: HIGH_PRIORITY_KINDS.includes(kind) ? 5 : 3,
        notes: notes || null,
      }),
    onSuccess: () => {
      setTitle("");
      setNotes("");
      qc.invalidateQueries({ queryKey: ["events"] });
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        create.mutate();
      }}
      className="flex flex-col gap-3"
    >
      <Input
        label={t("training.event_title")}
        value={title}
        onChange={setTitle}
        required
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <Select
          label={t("training.event_type")}
          value={kind}
          onChange={(v) => setKind(v as EventKind)}
          options={EVENT_KINDS.map((k) => ({
            value: k,
            label: t(`training.${k}`),
          }))}
        />
        <Input
          label={t("training.event_date")}
          type="date"
          value={date}
          onChange={setDate}
          required
        />
      </div>
      {create.isError && <ErrorNote />}
      <Input label={t("training.notes")} value={notes} onChange={setNotes} />
      <Button type="submit" disabled={create.isPending} className="self-start">
        {t("training.save")}
      </Button>
    </form>
  );
}

function EventCalendar() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.get<EventOut[]>("/events"),
  });

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/events/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events"] }),
  });

  const upcoming = useMemo(() => {
    const today = todayIso();
    return (data ?? [])
      .map((e) => ({ ...e, day: e.starts_at.slice(0, 10) }))
      .filter((e) => e.day >= today)
      .sort((a, b) => a.day.localeCompare(b.day))
      .slice(0, 8);
  }, [data]);

  return (
    <Card>
      <CardHeader
        eyebrow={t("training.calendar")}
        right={
          <Button
            variant="ghost"
            onClick={() => setAdding((v) => !v)}
            className="min-h-11 !px-3 text-[13px]"
          >
            {adding ? t("common.cancel") : `+ ${t("training.add_event")}`}
          </Button>
        }
      />
      {adding && (
        <div className="mb-3 bg-surface2 p-3">
          <AddEvent onDone={() => setAdding(false)} />
        </div>
      )}
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <div className="space-y-3"><ErrorNote /><Button variant="ghost" disabled={isFetching} onClick={() => void refetch()}>{t("common.retry")}</Button></div>
      ) : upcoming.length === 0 ? (
        <Empty>{t("design.no_events")}</Empty>
      ) : (
        <div className="flex flex-col gap-2">
          {upcoming.map((e) => {
            const days = Math.round(
              (new Date(e.day + "T00:00:00").getTime() -
                new Date(todayIso() + "T00:00:00").getTime()) /
                86400000,
            );
            return (
              <div
                key={e.id}
                className="flex items-center gap-4 border-b border-hairline py-5 last:border-0"
              >
                <div className="num flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-control bg-surface2 text-ink">
                  <span className="text-[14px] font-bold">
                    {e.day.slice(8)}
                  </span>
                  <span className="text-[12px]">{e.day.slice(5, 7)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="break-words text-[13px] font-medium text-ink">
                      {e.title}
                    </span>
                    {e.priority === 1 && (
                      <Badge tone="primary">{t("training.priority")}</Badge>
                    )}
                  </div>
                  <div className="num text-[12px] text-muted">
                    {days === 0 ? t("common.today") : `${days} d`} ·{" "}
                    {t(`training.${e.kind}`)}
                    {e.notes ? ` · ${e.notes}` : ""}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => del.mutate(e.id)}
                  disabled={del.isPending}
                  aria-label={t("redesign.training.delete_event", { title: e.title })}
                  className="inline-flex min-h-11 shrink-0 items-center rounded-control px-2 text-[12px] text-muted hover:text-alertText disabled:opacity-50"
                >
                  {t("training.delete")}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {del.isError && (
        <div className="mt-3">
          <ErrorNote />
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------- load chart */

function LoadChart() {
  const { t } = useTranslation();
  const [metric, setMetric] = useState("acute_load");
  const overview = useQuery({
    queryKey: ["overview", "latest"],
    queryFn: () => api.get<Overview>("/dashboard/overview"),
  });
  const load = overview.data?.load_metadata;
  const method = load?.method === "garmin_recorded"
    ? t("training.load_garmin")
    : load?.method === "edwards_trimp"
      ? t("training.load_edwards")
      : t("training.load_method_unavailable");
  const query = useQuery({
    queryKey: ["metric", metric, 56],
    queryFn: () =>
      api.get<import("../../app/api").MetricTrend>(
        "/metrics/" + metric + "?days=56",
      ),
  });
  return (
    <Card>
      <CardHeader title={t("training.load_chart")} />
      <Tabs
        value={metric}
        onChange={setMetric}
        label={t("training.load_chart")}
        options={[
          { value: "acute_load", label: t("design.acute") },
          { value: "chronic_load", label: t("design.chronic") },
          { value: "acwr", label: "ACWR" },
        ]}
      />
      <p className="mt-4 text-[12px] text-muted">
        {metric === "acwr" ? t("design.ratio") : t("training.load_week_unit")} · {t("design.days56")}
      </p>
      {query.isLoading ? (
        <Loading />
      ) : query.isError ? (
        <div className="space-y-3"><ErrorNote /><Button variant="ghost" disabled={query.isFetching} onClick={() => void query.refetch()}>{t("common.retry")}</Button></div>
      ) : (
        <TrendChart
          points={query.data?.points ?? []}
          start={query.data?.start_date}
          end={query.data?.end_date}
          label={t("training.load_chart")}
          unit={metric === "acwr" ? t("design.ratio") : t("training.load_week_unit")}
          height={280}
        />
      )}
      {load && (
        <p className="mt-4 text-sm text-muted">
          {t("training.load_provenance", {
            method,
            unit: load.method === "garmin_recorded" ? t("training.load_unit_garmin") : load.unit,
            included: load.included_sessions,
            excluded: load.excluded_sessions,
          })}
        </p>
      )}
      <p className="mt-4 text-[12px] text-muted">{t("design.load_note")}</p>
    </Card>
  );
}

/* --------------------------------------------------------------- gym plan */

interface GymExerciseRow {
  gym_day_exercise_id: number;
  exercise_id: number;
  name: string;
  muscle_group: string;
  movement_pattern: string;
  position: number;
  sets: number;
  reps_min: number | null;
  duration_min_s?: number | null;
  duration_max_s?: number | null;
  reps_max: number | null;
  rest_seconds: number | null;
  notes: string | null;
  sets_done: number;
  next_set_number?: number | null;
  complete: boolean;
}

interface PlanView {
  plan_id: number;
  revision?: number;
  date: string;
  title: string;
  source: string;
  status: string;
  adjustment_note: string | null;
  exercises: GymExerciseRow[];
  progress: { sets_done: number; sets_total: number; complete: boolean };
}

interface GymPlanResp {
  date: string;
  plan: PlanView | null;
  template: { title?: string; start_time?: string } | null;
  hint?: string;
}

function useGymPlan(day: string, enabled: boolean) {
  return useQuery({
    queryKey: ["gym-plan", day],
    queryFn: () => api.get<GymPlanResp>(`/gym/plan/${day}`),
    enabled,
  });
}

function GymPlan({ day, plan }: { day: string; plan: ReturnType<typeof useGymPlan> }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const editable = day === todayIso();
  const [restUntil, setRestUntil] = useState<number | null>(null);
  const [clock, setClock] = useState(Date.now());
  const [entry, setEntry] = useState({ exerciseId: 0, reps: "", weight: "" });
  const rest = restUntil === null ? 0 : Math.max(0, Math.ceil((restUntil - clock) / 1000));
  const refresh = () => Promise.all([
    qc.invalidateQueries({ queryKey: ["gym-plan", day] }),
    qc.invalidateQueries({ queryKey: ["athlete-day"] }),
    qc.invalidateQueries({ queryKey: ["athlete-sport-overview"] }),
    qc.invalidateQueries({ queryKey: ["lab"] }),
  ]);

  const generate = useMutation({
    mutationFn: () => api.post<PlanView>(`/gym/plan/${day}/generate`),
    onSuccess: () => {
      confirm.reset();
      return refresh();
    },
  });
  const confirm = useMutation({
    mutationFn: () => api.post(`/gym/plan/${day}/confirm`, {expected_revision: plan.data?.plan?.revision}),
    onSuccess: refresh,
  });

  const logOne = useMutation({
    mutationFn: (payload: {
      plan_id: number;
      gym_day_exercise_id: number;
      set_number: number;
      reps_done: number | null;
      duration_s: number | null;
      weight_kg: number | null;
    }) =>
      api.post<{ rest_seconds: number | null; next?: { done?: boolean } }>(
        `/gym/session/${payload.plan_id}/log`,
        {
          gym_day_exercise_id: payload.gym_day_exercise_id,
          set_number: payload.set_number,
          ...(payload.duration_s != null ? { duration_s: payload.duration_s } : { reps_done: payload.reps_done }),
          weight_kg: payload.weight_kg,
        },
      ),
    onSuccess: (resp) => {
      const now = Date.now();
      setClock(now);
      setRestUntil(!resp.next?.done && resp.rest_seconds != null && resp.rest_seconds > 0
        ? now + resp.rest_seconds * 1000 : null);
      return refresh();
    },
  });

  useEffect(() => {
    if (restUntil === null) return;
    const update = () => {
      const now = Date.now();
      setClock(now);
      if (now >= restUntil) setRestUntil(null);
    };
    const timer = setInterval(update, 250);
    document.addEventListener("visibilitychange", update);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", update); };
  }, [restUntil]);

  if (plan.isLoading) return <div id="gym-session"><Card><Loading /></Card></div>;
  if (plan.isError) return <div id="gym-session"><Card><ErrorNote /><Button variant="ghost" className="mt-3 min-h-11" disabled={plan.isFetching} onClick={() => void plan.refetch()}>{t("common.retry")}</Button></Card></div>;
  const data = plan.data;
  const p = data?.plan ?? null;
  const exercises = p?.exercises ?? [];
  const complete = p?.progress.complete || p?.status === "done" || p?.status === "completed";
  const nextEx = complete ? null : exercises.find((e) => !e.complete) ?? null;
  const currentEntry = entry.exerciseId === nextEx?.gym_day_exercise_id
    ? entry : { exerciseId: nextEx?.gym_day_exercise_id ?? 0, reps: String(nextEx?.duration_min_s ?? nextEx?.reps_min ?? ""), weight: "" };
  const { reps, weight } = currentEntry;
  const timed = nextEx?.duration_min_s != null;
  const target = (ex: GymExerciseRow) => {
    const min = ex.duration_min_s ?? ex.reps_min;
    const max = ex.duration_min_s != null ? ex.duration_max_s : ex.reps_max;
    return `${min ?? "—"}${max != null && max !== min ? `–${max}` : ""}${ex.duration_min_s != null ? " s" : ""}`;
  };
  const validEntry = reps !== "" && Number.isInteger(Number(reps)) && Number(reps) >= 1 && Number(reps) <= (timed ? 86400 : 500)
    && (weight === "" || (Number.isFinite(Number(weight)) && Number(weight) >= 0 && Number(weight) <= 500));

  function logSet(ex: GymExerciseRow) {
    if (!p || !editable || !validEntry || logOne.isPending || complete || !["confirmed", "active"].includes(p.status)) return;
    const setNumber = ex.next_set_number === undefined ? ex.sets_done + 1 : ex.next_set_number;
    if (setNumber === null) return;
    logOne.mutate({
      plan_id: p.plan_id,
      gym_day_exercise_id: ex.gym_day_exercise_id,
      set_number: setNumber,
      reps_done: timed ? null : Number(reps),
      duration_s: timed ? Number(reps) : null,
      weight_kg: weight ? Number(weight) : null,
    });
  }

  return (
    <div id="gym-session"><Card className="!p-4 sm:!p-6">
      {(generate.isError || confirm.isError || logOne.isError) && <ErrorNote message={t(confirm.error instanceof ApiError && confirm.error.status === 409 ? "betaNavigation.gym_context_changed" : "betaNavigation.gym_action_failed")} />}
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">{t("training.gym_plan")}</p>
          <h2 className="mt-1 flex min-w-0 items-start gap-2 text-[16px] font-medium leading-snug text-ink sm:text-[18px]"><Dumbbell size={18} className="mt-0.5 shrink-0 text-primaryText" aria-hidden="true" /><span className="break-words">{p?.title ?? data?.template?.title ?? t("redesign.training.gym_title")}</span></h2>
        </div>
        {p && <Badge tone={complete ? "positive" : "primary"}>{t(complete ? "betaNavigation.gym_status_done" : p.status === "active" ? "v01Training.in_progress" : "betaNavigation.gym_status_"+p.status,{defaultValue:p.status})}</Badge>}
      </header>

      {editable && (!p || p.status === "draft") && <div className="mb-4 flex flex-wrap items-center gap-2">
            {editable && !p && (
              <Button
                variant="ghost"
                onClick={() => generate.mutate()}
                disabled={generate.isPending}
                className="min-h-11 !px-3 text-[13px]"
              >
                {t("training.gym_generate")}
              </Button>
            )}
            {editable && p?.status === "draft" && <Button variant="ghost" disabled={generate.isPending || confirm.isPending} onClick={()=>generate.mutate()}>{t("betaNavigation.refresh_gym")}</Button>}
            {editable && p?.status === "draft" && (
              <Button
                onClick={() => confirm.mutate()}
                disabled={confirm.isPending || generate.isPending || exercises.length === 0}
                className="min-h-11 !px-3 text-[13px]"
              >
                {t("training.gym_confirm")}
              </Button>
            )}
      </div>}

      {editable && p?.status === "draft" && <p className="mb-4 max-w-xl rounded-control bg-primarySoft p-4 text-[13px] text-ink2">{t("redesign.training.gym_review_note")}</p>}
      {!editable && <p className="mb-4 text-[13px] text-muted">{t("v01Training.read_only")}</p>}
      {complete && <p role="status" className="mb-4 rounded-control bg-primarySoft p-4 text-[14px]">{t("v01Training.completed")}</p>}

      {(generate.data?.adjustment_note ?? p?.adjustment_note) && (
        <div className="mb-3 rounded-card bg-primarySoft px-3 py-2 text-[12px] text-ink2">
          <span className="eyebrow mr-2 text-primaryText">
            {t("training.gym_advice")}
          </span>
          {generate.data?.adjustment_note ?? p?.adjustment_note}
        </div>
      )}

      {exercises.length === 0 ? (
        <p className="max-w-xl text-[13px] text-muted">{t(editable ? "redesign.training.gym_empty" : "training.gym_no_plan")}</p>
      ) : (
        <>
          {/* live session card — the gym-tracker companion to the Connect IQ app */}
          {editable && nextEx && p && ["confirmed", "active"].includes(p.status) && (
            <div className="mb-4 rounded-card border border-primary/20 bg-primarySoft/50 p-3 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="eyebrow">
                    {t("training.next_exercise")} ·{" "}
                    {t("training.set_progress", {
                      done: p?.progress.sets_done ?? 0,
                      total: p?.progress.sets_total ?? 0,
                    })}
                  </div>
                  <div className="mt-0.5 break-words text-[20px] font-medium leading-snug text-ink">
                    {nextEx.name}
                  </div>
                  <div className="num mt-0.5 text-[12px] text-muted">
                    {t("training.sets_short", {
                      done: nextEx.sets_done,
                      total: nextEx.sets,
                    })}{" "}
                    × {target(nextEx)}
                  </div>
                  {nextEx.notes && <p className="mt-2 max-w-lg text-[12px] text-muted">{nextEx.notes}</p>}
                </div>
                {rest > 0 && (
                  <div className="text-right">
                    <div className="eyebrow">{t("training.rest_timer")}</div>
                    <div role="timer" aria-label={t("training.rest_timer")} className="num text-[28px] font-medium text-ink">
                      {Math.floor(rest / 60)}:
                      {String(rest % 60).padStart(2, "0")}
                    </div>
                    <Button variant="ghost" onClick={() => setRestUntil(null)}>{t("v01Training.skip_rest")}</Button>
                  </div>
                )}
              </div>
              <form className="mt-4" onSubmit={event => { event.preventDefault(); logSet(nextEx); }}>
                <fieldset disabled={logOne.isPending} className="flex flex-wrap items-end gap-3">
                <Input
                  label={t(timed ? "v01Training.duration_seconds" : "training.reps")}
                  type="number"
                  min={1}
                  max={timed ? 86400 : 500}
                  step={1}
                  value={reps}
                  onChange={reps => setEntry({ ...currentEntry, reps })}
                  placeholder={String(nextEx.duration_min_s ?? nextEx.reps_min ?? "")}
                  className="w-24"
                />
                <Input
                  label={t("training.weight") + " (kg)"}
                  type="number"
                  min={0}
                  max={500}
                  step={0.5}
                  value={weight}
                  onChange={weight => setEntry({ ...currentEntry, weight })}
                  className="w-28"
                />
                <Button
                  type="submit"
                  disabled={logOne.isPending || !validEntry}
                  className="min-h-11"
                >
                  {t(logOne.isPending ? "v01Training.saving" : "training.log_set")}
                </Button>
                </fieldset>
              </form>
            </div>
          )}

          <details open={p?.status === "draft" || !editable || complete} className="rounded-control border border-hairline px-4">
          <summary className="min-h-11 cursor-pointer py-3 text-[13px] font-medium text-ink2">{t("redesign.training.exercise_list", { count: exercises.length })}</summary>
          <div className="pb-4">
          <ol className="space-y-3 sm:hidden" data-testid="gym-exercise-list">
            {exercises.map((ex, i) => <li key={ex.gym_day_exercise_id} className={`border border-hairline p-3 ${ex.gym_day_exercise_id === nextEx?.gym_day_exercise_id ? "bg-primarySoft/40" : ""}`}>
              <div className="flex flex-wrap items-start justify-between gap-2"><p className="min-w-0 text-[14px] font-medium">{i + 1}. {ex.name}</p>{ex.complete && <Badge tone="positive">{t("training.done")}</Badge>}</div>
              {ex.notes && <p className="mt-2 break-words text-[12px] text-muted">{ex.notes}</p>}
              <dl className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
                <div><dt className="text-muted">{t("betaNavigation.sets_label")}</dt><dd className="num mt-1">{ex.sets}</dd></div>
                <div><dt className="text-muted">{t("v01Training.target")}</dt><dd className="num mt-1">{target(ex)}</dd></div>
                <div><dt className="text-muted">{t("training.rest_timer")}</dt><dd className="num mt-1">{ex.rest_seconds == null ? "—" : `${ex.rest_seconds}s`}</dd></div>
              </dl>
              {p?.status !== "draft" && <p className="mt-3 text-[12px] text-muted">{t("betaNavigation.sets_completed", {count: ex.sets_done ?? 0})}</p>}
            </li>)}
          </ol>
          <div className="hidden overflow-x-auto sm:block">
            <table className="data-table">
              <thead>
                <tr className="border-b border-hairline text-left">
                  <th className="eyebrow py-2 pr-3">#</th>
                  <th className="eyebrow py-2 pr-3">
                    {t("training.exercise")}
                  </th>
                  <th className="eyebrow py-2 pr-3">{t("betaNavigation.sets_label")}</th>
                  <th className="eyebrow py-2 pr-3">{t("v01Training.target")}</th>
                  <th className="eyebrow py-2">{t("training.rest_timer")}</th>
                </tr>
              </thead>
              <tbody className="num text-ink2">
                {exercises.map((ex, i) => (
                  <tr
                    key={ex.gym_day_exercise_id}
                    className={`border-b border-hairline last:border-0 ${
                      nextEx &&
                      ex.gym_day_exercise_id === nextEx.gym_day_exercise_id
                        ? "bg-primarySoft/40"
                        : ""
                    }`}
                  >
                    <td className="py-2 pr-3">{i + 1}</td>
                    <td className="py-2 pr-3 font-medium text-ink">
                      {ex.name}
                      {ex.notes && <p className="mt-1 max-w-64 whitespace-normal text-[12px] font-normal text-muted">{ex.notes}</p>}
                      {ex.complete && (
                        <span className="ml-2">
                          <Badge tone="positive">{t("training.done")}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      {ex.sets}
                      {p?.status !== "draft" && <span className="mt-1 block text-[12px] text-muted">{t("betaNavigation.sets_completed", {count: ex.sets_done ?? 0})}</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {target(ex)}
                    </td>
                    <td className="py-2">{ex.rest_seconds == null ? "—" : `${ex.rest_seconds}s`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          </div>
          </details>
          {editable && p?.status !== "draft" && <details className="mt-4 border-t border-hairline"><summary className="min-h-11 cursor-pointer py-3 text-[13px] text-ink2">{t("training.feedback")}</summary><Feedback day={day} /></details>}
        </>
      )}
    </Card></div>
  );
}

function Feedback({ day }: { day: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const submit = useMutation({
    mutationFn: () =>
      api.post("/gym/feedback", {
        date: day,
        activity_kind: "gym",
        notes: text.trim(),
      }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["gym-plan"] });
      qc.invalidateQueries({ queryKey: ["athlete-day"] });
    },
  });
  return (
    <div className="pb-1">
      {submit.isError && <ErrorNote />}
      {submit.isSuccess && <Badge tone="positive">{t("settings.saved")}</Badge>}
      <div className="flex flex-wrap gap-2">
        <input
          aria-label={t("training.feedback")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("training.feedback_placeholder")}
          className="h-11 min-w-0 flex-1 rounded-control border border-hairline bg-surface2 px-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
        />
        <Button
          onClick={() => submit.mutate()}
          disabled={!text.trim() || submit.isPending}
          className="min-h-11"
        >
          {t("training.submit")}
        </Button>
      </div>
    </div>
  );
}

type TrainingWorkspace = "today" | "planning" | "progress";

function shiftedDay(day: string, offset: number) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

export default function TrainingPage() {
  const { t, i18n } = useTranslation();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const today = localDay(useUi(s => s.me?.timezone));
  const requestedDay = params.get("date") ?? today;
  const day = /^\d{4}-\d{2}-\d{2}$/.test(requestedDay) && !Number.isNaN(Date.parse(requestedDay))
    && new Date(requestedDay).toISOString().slice(0, 10) === requestedDay ? requestedDay : today;
  const requestedTab = params.get("tab");
  // Keep established plan, planning, calendar and load links working.
  const workspace: TrainingWorkspace = requestedTab === "planning" || requestedTab === "calendar"
    ? "planning" : requestedTab === "load" || requestedTab === "progress" ? "progress" : "today";
  const [hasOpenedToday, setHasOpenedToday] = useState(workspace === "today");
  useEffect(() => { if (workspace === "today") setHasOpenedToday(true); }, [workspace]);
  const gymPlan = useGymPlan(day, workspace === "today" || hasOpenedToday);
  const hasGymPlan = !!gymPlan.data?.plan;
  // Stable keys preserve the mounted day, check-in drafts and timer when a real
  // strength plan becomes available and moves ahead of supporting day context.
  const dayContext = <YourDay key={`day:${day}`} date={day} />;
  const gymExecution = <GymPlan key={`gym:${day}`} day={day} plan={gymPlan} />;
  const changeParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    // Date navigation and workspace switches retain the selected day and anchor.
    const hash = key === "tab" && value === "planning" && location.hash === "#gym-session" ? "" : location.hash;
    navigate({ pathname: location.pathname, search: `?${next}`, hash });
  };
  const dateLabel = new Date(`${day}T12:00:00Z`).toLocaleDateString(i18n.language, {
    timeZone: "UTC", weekday: "short", month: "short", day: "numeric",
  });

  return (
    <div className="flex min-w-0 flex-col gap-3 sm:gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow hidden text-primaryText sm:block">{t("redesign.training.eyebrow")}</p>
          <h1 className="text-[24px] font-medium tracking-tight text-ink sm:mt-2 sm:text-[32px]">{t("redesign.training.title")}</h1>
          <p className={`${workspace === "today" ? "hidden sm:block" : ""} mt-2 max-w-xl text-[14px] text-muted`}>{t(`redesign.training.intro_${workspace}`)}</p>
        </div>
      </header>

      <Tabs
        value={workspace}
        onChange={tab => changeParam("tab", tab === "today" ? "plan" : tab)}
        label={t("redesign.training.workspaces")}
        options={[
          { value: "today", label: t("redesign.training.today") },
          { value: "planning", label: t("redesign.training.plan") },
          { value: "progress", label: t("redesign.training.progress") },
        ]}
      />

      {/* Keep an opened session mounted across workspaces so its rest timer survives. */}
      {(workspace === "today" || hasOpenedToday) && <section hidden={workspace !== "today"} aria-label={t("redesign.training.today")}>
        <div className="flex flex-col gap-3 sm:gap-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="hidden text-[14px] font-medium text-ink sm:block">{day === today ? `${t("common.today")} · ${dateLabel}` : dateLabel}</p>
            <div className="flex max-w-full flex-wrap items-center gap-2">
              <button type="button" aria-label={t("redesign.training.previous_day")} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-control border border-hairline text-ink2 hover:bg-surface2" onClick={() => changeParam("date", shiftedDay(day, -1))}><ArrowLeft size={17} aria-hidden="true" /></button>
              <label className="min-w-0"><span className="sr-only">{t("v01Training.date")}</span><input type="date" value={day} onChange={event => { if (event.target.value) changeParam("date", event.target.value); }} className="h-11 min-w-0 max-w-full rounded-control border border-hairline bg-transparent px-2 text-[13px] text-ink" /></label>
              <button type="button" aria-label={t("redesign.training.next_day")} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-control border border-hairline text-ink2 hover:bg-surface2" onClick={() => changeParam("date", shiftedDay(day, 1))}><ArrowRight size={17} aria-hidden="true" /></button>
              {day !== today && <Button variant="ghost" className="min-h-11" onClick={() => changeParam("date", today)}>{t("v01Training.return_today")}</Button>}
            </div>
          </div>
          {hasGymPlan ? [gymExecution, dayContext] : [dayContext, gymExecution]}
          {day === today && <details className="rounded-card border border-hairline bg-surface px-4 sm:px-5">
            <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 text-[14px] font-medium text-ink2">{t("redesign.training.day_context")}<ChevronRight size={17} className="shrink-0" aria-hidden="true" /></summary>
            <p className="mb-4 max-w-xl text-[13px] text-muted">{t("redesign.training.day_context_note")}</p>
            <div className="pb-4"><LifeEvents /></div>
          </details>}
        </div>
      </section>}

      {workspace === "planning" && <section aria-label={t("redesign.training.plan")} className="min-w-0 space-y-5">
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("redesign.training.plan_tools")}>
          <Button variant={requestedTab === "calendar" ? "ghost" : "subtle"} className="min-h-11" onClick={() => changeParam("tab", "planning")}>{t("redesign.training.review_plan")}</Button>
          <Button variant={requestedTab === "calendar" ? "subtle" : "ghost"} className="min-h-11" onClick={() => changeParam("tab", "calendar")}>{t("training.calendar")}</Button>
        </div>
        {requestedTab === "calendar" ? <EventCalendar /> : <TrainingPlanWorkspace />}
      </section>}

      {workspace === "progress" && <section aria-label={t("redesign.training.progress")} className="min-w-0 space-y-5">
        <div className="rounded-card border border-hairline bg-surface p-5">
          <h2 className="text-[16px] font-medium text-ink">{t("redesign.training.sport_progress")}</h2>
          <p className="mb-4 mt-1 text-[13px] text-muted">{t("redesign.training.sport_progress_note")}</p>
          <TrainingSections />
        </div>
        <LoadChart />
      </section>}
    </div>
  );
}
