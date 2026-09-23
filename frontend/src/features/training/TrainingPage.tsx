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

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
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
import { EChart, useChartTheme } from "../../components/charts/EChart";

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
  return new Date().toISOString().slice(0, 10);
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
      <Input label={t("training.event_title")} value={title} onChange={setTitle} required />
      <div className="grid grid-cols-2 gap-3">
        <Select
          label={t("training.event_type")}
          value={kind}
          onChange={(v) => setKind(v as EventKind)}
          options={EVENT_KINDS.map((k) => ({ value: k, label: t(`training.${k}`) }))}
        />
        <Input label={t("training.event_date")} type="date" value={date} onChange={setDate} required />
      </div>
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
  const { data, isLoading } = useQuery({
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
          <Button variant="ghost" onClick={() => setAdding((v) => !v)} className="!h-7 !px-2.5 text-[12px]">
            {adding ? t("common.cancel") : `+ ${t("training.add_event")}`}
          </Button>
        }
      />
      {adding && (
        <div className="mb-3 rounded-card border border-hairline bg-surface2 p-3">
          <AddEvent onDone={() => setAdding(false)} />
        </div>
      )}
      {isLoading ? (
        <Loading />
      ) : upcoming.length === 0 ? (
        <Empty>{t("social.no_data")}</Empty>
      ) : (
        <div className="flex flex-col gap-2">
          {upcoming.map((e) => {
            const days = Math.round(
              (new Date(e.day + "T00:00:00").getTime() - new Date(todayIso() + "T00:00:00").getTime()) / 86400000,
            );
            return (
              <div
                key={e.id}
                className="flex items-center gap-3 rounded-card border border-hairline bg-surface2 px-3 py-2.5"
              >
                <div className="num flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-control bg-primarySoft text-primaryText">
                  <span className="text-[14px] font-bold">{e.day.slice(8)}</span>
                  <span className="text-[8px] uppercase">{e.day.slice(5, 7)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-semibold text-ink">{e.title}</span>
                    {e.priority === 1 && <Badge tone="primary">{t("training.priority")}</Badge>}
                  </div>
                  <div className="num text-[11px] text-muted">
                    {days === 0 ? t("common.today") : `${days} d`} · {t(`training.${e.kind}`)}
                    {e.notes ? ` · ${e.notes}` : ""}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => del.mutate(e.id)}
                  className="text-[11px] text-muted hover:text-alertText"
                >
                  {t("training.delete")}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {del.isError && <div className="mt-3"><ErrorNote /></div>}
    </Card>
  );
}

/* ------------------------------------------------------------- load chart */

function LoadChart() {
  const { t } = useTranslation();
  const c = useChartTheme();
  const acute = useQuery({
    queryKey: ["metric", "acute_load", 56],
    queryFn: () => api.get<import("../../app/api").MetricTrend>("/metrics/acute_load?days=56"),
  });
  const chronic = useQuery({
    queryKey: ["metric", "chronic_load", 56],
    queryFn: () => api.get<import("../../app/api").MetricTrend>("/metrics/chronic_load?days=56"),
  });

  if (acute.isLoading || chronic.isLoading) return <Loading />;
  const pts = acute.data?.points ?? [];
  const cps = chronic.data?.points ?? [];
  if (!pts.some((p) => p.value !== null)) return <Empty>{t("biometrics.no_data")}</Empty>;

  return (
    <Card>
      <CardHeader eyebrow={t("training.load_chart")} />
      <EChart
        option={{
          grid: { left: 40, right: 12, top: 24, bottom: 24 },
          legend: {
            top: 0,
            left: 0,
            icon: "rect",
            itemWidth: 10,
            itemHeight: 2,
            textStyle: { color: c.muted, fontSize: 10 },
          },
          tooltip: {
            trigger: "axis",
            backgroundColor: c.surface,
            borderColor: c.hairline,
            textStyle: { color: c.ink, fontSize: 11 },
          },
          xAxis: {
            type: "time",
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
          },
          yAxis: {
            type: "value",
            splitLine: { lineStyle: { color: c.hairline, type: "dashed" } },
            axisLabel: { color: c.muted, fontSize: 10, fontFamily: "JetBrains Mono" },
          },
          series: [
            {
              name: t("overview.acute_load"),
              type: "bar",
              data: pts.map((p) => [p.date, p.value]),
              barMaxWidth: 7,
              itemStyle: { color: c.hairline, borderRadius: [2, 2, 0, 0] },
            },
            {
              name: t("overview.chronic_load"),
              type: "line",
              data: cps.map((p) => [p.date, p.value]),
              showSymbol: false,
              smooth: true,
              lineStyle: { color: c.primary, width: 2 },
              itemStyle: { color: c.primary },
            },
          ],
        }}
        height={260}
      />
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
  reps_min: number;
  reps_max: number | null;
  rest_seconds: number | null;
  notes: string | null;
  sets_done: number;
  complete: boolean;
}

interface PlanView {
  plan_id: number;
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

function GymPlan() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const day = todayIso();
  const [rest, setRest] = useState<number | null>(null);

  const plan = useQuery({
    queryKey: ["gym-plan", day],
    queryFn: () => api.get<GymPlanResp>(`/gym/plan/${day}`),
  });

  const generate = useMutation({
    mutationFn: () => api.post(`/gym/plan/${day}/generate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gym-plan", day] }),
  });
  const confirm = useMutation({
    mutationFn: () => api.post(`/gym/plan/${day}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gym-plan", day] }),
  });

  const logOne = useMutation({
    mutationFn: (payload: {
      plan_id: number;
      gym_day_exercise_id: number;
      set_number: number;
      reps_done: number;
    }) =>
      api.post<{ rest_seconds: number | null }>(`/gym/session/${payload.plan_id}/log`, {
        gym_day_exercise_id: payload.gym_day_exercise_id,
        set_number: payload.set_number,
        reps_done: payload.reps_done,
      }),
    onSuccess: (resp) => {
      setRest(resp?.rest_seconds ?? 90);
      qc.invalidateQueries({ queryKey: ["gym-plan", day] });
    },
  });

  useEffect(() => {
    if (rest === null || rest <= 0) return undefined;
    const timer = setInterval(() => setRest((r) => (r !== null && r > 0 ? r - 1 : 0)), 1000);
    return () => clearInterval(timer);
  }, [rest]);

  if (plan.isLoading) return <Loading />;
  if (plan.isError) return <ErrorNote />;
  const data = plan.data;
  const p = data?.plan ?? null;
  const exercises = p?.exercises ?? [];
  const nextEx = exercises.find((e) => !e.complete) ?? null;

  function logSet(ex: GymExerciseRow) {
    if (!p) return;
    logOne.mutate({
      plan_id: p.plan_id,
      gym_day_exercise_id: ex.gym_day_exercise_id,
      set_number: ex.sets_done + 1,
      reps_done: ex.reps_min,
    });
  }

  return (
    <Card>
      <CardHeader
        eyebrow={t("training.gym_plan")}
        title={p ? p.title : data?.template?.title ?? undefined}
        right={
          <div className="flex items-center gap-2">
            {p && <Badge tone={p.status === "done" ? "positive" : "primary"}>{p.status}</Badge>}
            {!p && data?.template && (
              <Button variant="ghost" onClick={() => generate.mutate()} disabled={generate.isPending} className="!h-7 !px-2.5 text-[12px]">
                {t("training.gym_generate")}
              </Button>
            )}
            {p?.status === "draft" && (
              <Button onClick={() => confirm.mutate()} disabled={confirm.isPending} className="!h-7 !px-2.5 text-[12px]">
                {t("training.gym_confirm")}
              </Button>
            )}
          </div>
        }
      />

      {p?.adjustment_note && (
        <div className="mb-3 rounded-card bg-primarySoft px-3 py-2 text-[12px] text-ink2">
          <span className="eyebrow mr-2 text-primaryText">{t("training.gym_advice")}</span>
          {p.adjustment_note}
        </div>
      )}

      {exercises.length === 0 ? (
        <Empty>
          {data?.template
            ? `${t("training.gym_no_plan")} — ${data.template.title ?? ""}`
            : t("training.gym_no_plan")}
        </Empty>
      ) : (
        <>
          {/* live session card — the gym-tracker companion to the Connect IQ app */}
          {nextEx && (
            <div className="mb-3 rounded-card border border-primary/40 bg-surface2 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="eyebrow">
                    {t("training.next_exercise")} ·{" "}
                    {t("training.set_progress", {
                      done: p?.progress.sets_done ?? 0,
                      total: p?.progress.sets_total ?? 0,
                    })}
                  </div>
                  <div className="mt-0.5 text-[16px] font-semibold text-ink">{nextEx.name}</div>
                  <div className="num mt-0.5 text-[12px] text-muted">
                    {t("training.sets_short", { done: nextEx.sets_done, total: nextEx.sets })} ×{" "}
                    {nextEx.reps_min}
                    {nextEx.reps_max ? `-${nextEx.reps_max}` : ""}
                  </div>
                </div>
                {rest !== null && rest > 0 && (
                  <div className="text-right">
                    <div className="eyebrow">{t("training.rest_timer")}</div>
                    <div className="num text-[28px] font-bold text-primaryText">
                      {Math.floor(rest / 60)}:{String(rest % 60).padStart(2, "0")}
                    </div>
                  </div>
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  onClick={() => logSet(nextEx)}
                  disabled={logOne.isPending}
                  className="!h-8 text-[12px]"
                >
                  {t("training.log_set")}
                </Button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-hairline text-left">
                  <th className="eyebrow py-2 pr-3">#</th>
                  <th className="eyebrow py-2 pr-3">{t("training.exercise")}</th>
                  <th className="eyebrow py-2 pr-3">{t("training.sets")}</th>
                  <th className="eyebrow py-2 pr-3">{t("training.reps")}</th>
                  <th className="eyebrow py-2">{t("training.rest_timer")}</th>
                </tr>
              </thead>
              <tbody className="num text-ink2">
                {exercises.map((ex, i) => (
                  <tr
                    key={ex.gym_day_exercise_id}
                    className={`border-b border-hairline last:border-0 ${
                      nextEx && ex.gym_day_exercise_id === nextEx.gym_day_exercise_id
                        ? "bg-primarySoft/40"
                        : ""
                    }`}
                  >
                    <td className="py-2 pr-3">{i + 1}</td>
                    <td className="py-2 pr-3 font-medium text-ink">
                      {ex.name}
                      {ex.complete && (
                        <span className="ml-2">
                          <Badge tone="positive">{t("training.done")}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3">
                      {t("training.sets_short", { done: ex.sets_done, total: ex.sets })}
                    </td>
                    <td className="py-2 pr-3">
                      {ex.reps_min}
                      {ex.reps_max ? `-${ex.reps_max}` : ""}
                    </td>
                    <td className="py-2">{ex.rest_seconds ?? 90}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Feedback />
        </>
      )}
    </Card>
  );
}

function Feedback() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const submit = useMutation({
    mutationFn: () =>
      api.post("/gym/feedback", {
        date: todayIso(),
        activity_kind: "gym",
        notes: text,
      }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["gym-plan"] });
    },
  });
  return (
    <div className="mt-4 border-t border-hairline pt-3">
      <div className="eyebrow mb-2">{t("training.feedback")}</div>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("training.feedback_placeholder")}
          className="h-9 flex-1 rounded-control border border-hairline bg-surface2 px-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
        />
        <Button onClick={() => submit.mutate()} disabled={!text || submit.isPending} className="!h-9">
          {t("training.submit")}
        </Button>
      </div>
    </div>
  );
}

export default function TrainingPage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="eyebrow">{t("app.name")} {t("app.suffix")}</div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          {t("training.title")}
        </h1>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <EventCalendar />
        <LoadChart />
      </div>
      <GymPlan />
    </div>
  );
}
