import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, type ActivityListItem } from "../../app/api";
import { localDay } from "../../components/data";
import { useUi } from "../../app/stores/ui";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
} from "../../components/kit";
import type { Constraints, Event } from "./types";
import {
  Field,
  Form,
  num,
  QueryState,
  str,
  useAction,
  useLab,
  useToday,
} from "./shared";
function dateInZone(timestamp: string, zone?: string) {
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return timestamp.slice(0, 10);
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: zone || "UTC", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}
function monthBounds(month: string) {
  const [year, number] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, number - 1, 1));
  const last = new Date(Date.UTC(year, number, 0));
  const iso = (date: Date) => date.toISOString().slice(0, 10);
  return { first, last, start: iso(first), end: iso(last), days: last.getUTCDate(), offset: (first.getUTCDay() + 6) % 7 };
}
function shiftMonth(month: string, delta: number) {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1 + delta, 1)).toISOString().slice(0, 7);
}
export default function CalendarPage() {
  const { t } = useTranslation();
  const today = useToday();
  const timezone = useUi((s) => s.me?.timezone);
  const [month, setMonth] = useState(() => localDay(timezone).slice(0, 7));
  const bounds = useMemo(() => monthBounds(month), [month]);
  const events = useLab<Event[]>("/events?horizon_days=365");
  const monthlyEvents = useLab<Event[]>(`/events?start=${bounds.start}&end=${bounds.end}`);
  const constraints = useLab<Constraints>("/lab/constraints");
  const monthlySessions = useLab<{ sessions: Constraints["sessions"] }>(`/schedule/calendar?start=${bounds.start}&end=${bounds.end}`);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const activities = useQuery({
    queryKey: ["calendar-activities", month],
    queryFn: async () => {
      const items: ActivityListItem[] = [];
      let offset = 0;
      let total = 0;
      do {
        const page = await api.get<{ items: ActivityListItem[]; total: number }>(`/activities?limit=100&offset=${offset}&start=${bounds.start}&end=${bounds.end}`);
        items.push(...page.items);
        offset += page.items.length;
        total = page.total;
        if (page.items.length === 0) break;
      } while (offset < total);
      return items;
    },
  });
  const itemsByDay = useMemo(() => {
    const map = new Map<string, { label: string; href?: string; kind: string }[]>();
    const add = (day: string, item: { label: string; href?: string; kind: string }) => map.set(day, [...(map.get(day) ?? []), item]);
    for (const event of monthlyEvents.data ?? []) {
      const start = dateInZone(event.starts_at, timezone);
      const end = event.ends_at ? dateInZone(event.ends_at, timezone) : start;
      let cursor = new Date(`${start}T12:00:00Z`);
      const last = new Date(`${end}T12:00:00Z`);
      for (let days = 0; cursor <= last && days < 367; days++) {
        add(cursor.toISOString().slice(0, 10), { label: event.title, kind: "event" });
        cursor = new Date(cursor.getTime() + 86_400_000);
      }
    }
    for (const session of monthlySessions.data?.sessions ?? []) add(session.date, { label: session.session_type, kind: "plan" });
    for (const activity of activities.data ?? []) add(activity.local_date, { label: activity.discipline ?? t("activities.title"), href: `/app/activities/${activity.id}`, kind: "activity" });
    return map;
  }, [monthlyEvents.data, monthlySessions.data, activities.data, timezone, t]);
  const save = useAction();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("lab.calendar")} subtitle={t("lab.calendar_sub")} />
      <Card>
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-[18px] font-semibold">{new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" }).format(bounds.first)}</h2>
            <p className="text-[12px] text-muted">{t("navigation.calendar_summary")}</p>
          </div>
          <div className="flex items-center gap-1">
            <button type="button" aria-label={t("navigation.previous_month")} onClick={() => setMonth(shiftMonth(month, -1))} className="p-2 hover:bg-surface2"><ChevronLeft size={18} /></button>
            <button type="button" onClick={() => setMonth(localDay(timezone).slice(0, 7))} className="px-2 py-2 text-[12px] hover:bg-surface2">{t("navigation.today")}</button>
            <button type="button" aria-label={t("navigation.next_month")} onClick={() => setMonth(shiftMonth(month, 1))} className="p-2 hover:bg-surface2"><ChevronRight size={18} /></button>
          </div>
        </div>
        {(monthlyEvents.isError || monthlySessions.isError || activities.isError) && <ErrorNote />}
        <div className="grid grid-cols-7 gap-px bg-hairline border border-hairline" role="grid" aria-label={t("lab.calendar")}>
          <div role="row" className="contents">
            {Array.from({ length: 7 }, (_, i) => <div key={`head-${i}`} role="columnheader" className="bg-surface2 px-1 py-2 text-center text-[11px] text-muted">{new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + i)))}</div>)}
          </div>
          {Array.from({ length: Math.ceil((bounds.offset + bounds.days) / 7) }, (_, week) => <div key={week} role="row" className="contents">
            {Array.from({ length: 7 }, (_, weekday) => {
            const index = week * 7 + weekday;
            const dayNumber = index - bounds.offset + 1;
            const inMonth = dayNumber > 0 && dayNumber <= bounds.days;
            const day = `${month}-${String(dayNumber).padStart(2, "0")}`;
            const entries = inMonth ? itemsByDay.get(day) ?? [] : [];
            return <div key={index} role="gridcell" aria-label={inMonth ? `${day}, ${entries.length} ${t("navigation.calendar_items")}` : undefined}
              className="min-h-24 min-w-0 bg-surface p-1.5 sm:min-h-28 sm:p-2">
              {inMonth && <><button type="button" aria-label={day} aria-pressed={selectedDay === day} onClick={() => setSelectedDay(day)} className={day === today ? "inline-flex h-6 w-6 items-center justify-center rounded-full bg-ink text-[11px] text-canvas" : "text-[11px] text-muted hover:underline"}>{dayNumber}</button>
                <div className="mt-1 flex flex-col gap-1">{entries.slice(0, 3).map((entry, i) => entry.href
                  ? <Link key={i} to={entry.href} title={entry.label} className="truncate bg-positiveSoft px-1 py-0.5 text-[10px] text-positiveText">{entry.label}</Link>
                  : <span key={i} title={entry.label} className={"truncate px-1 py-0.5 text-[10px] " + (entry.kind === "plan" ? "bg-primarySoft text-primaryText" : "bg-warningSoft text-warningText")}>{entry.label}</span>)}
                  {entries.length > 3 && <button type="button" onClick={() => setSelectedDay(day)} className="text-left text-[10px] text-muted hover:underline">+{entries.length - 3}</button>}</div></>}
            </div>;
            })}
          </div>)}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 text-[11px] text-muted"><span>● {t("navigation.calendar_activity")}</span><span>● {t("navigation.calendar_plan")}</span><span>● {t("navigation.calendar_event")}</span></div>
        {selectedDay?.startsWith(month) && <div className="mt-5 border-t border-hairline pt-4" aria-live="polite">
          <h3 className="mb-3 text-[14px] font-medium">{new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${selectedDay}T12:00:00Z`))}</h3>
          {(itemsByDay.get(selectedDay) ?? []).length === 0 ? <p className="text-[12px] text-muted">{t("navigation.no_calendar_items")}</p> :
            <ul className="flex flex-col gap-2">{(itemsByDay.get(selectedDay) ?? []).map((entry, index) => <li key={index} className="text-[13px]">
              <span className="mr-2 text-muted">{t(`navigation.calendar_${entry.kind}`)}</span>
              {entry.href ? <Link className="text-link" to={entry.href}>{entry.label} ↗</Link> : entry.label}
            </li>)}</ul>}
        </div>}
      </Card>
      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title={t("lab.upcoming")} />
            <QueryState
              loading={events.isLoading}
              error={events.isError}
              empty={events.data?.length === 0}
            />
            {events.data?.map((e) => (
              <div
                key={e.id}
                className="flex items-start justify-between gap-4 border-t border-hairline py-5"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <strong className="text-[15px]">{e.title}</strong>
                    <Badge tone={e.priority === 1 ? "warning" : "neutral"}>
                      {t("lab.priority")} {e.priority}
                    </Badge>
                  </div>
                  <p className="mt-2 text-[13px] text-muted">
                    {e.date_only ? new Date(e.starts_at).toLocaleDateString(undefined, { timeZone: timezone }) : new Date(e.starts_at).toLocaleString()} · {t("lab.taper")}{" "}
                    {e.taper_days} {t("lab.days")}
                  </p>
                  {e.notes && <p className="mt-3 text-[13px]">{e.notes}</p>}
                </div>
                {e.profile_focus ? <Link className="text-link text-[13px]" to="/app/settings?tab=profile">{t("athlete.edit_profile_target")}</Link> : <Button
                  variant="ghost"
                  disabled={save.isPending}
                  onClick={() => save.mutate({ path: `/events/${e.id}`, method: "delete" })}
                >{t("training.delete")}</Button>}
              </div>
            ))}
          </Card>
          <Card>
            <div className="mb-4">
              <Button
                variant="ghost"
                disabled={save.isPending}
                onClick={() => save.mutate({ path: "/lab/replan", body: {} })}
              >
                {t("lab.minimal_replan")}
              </Button>
            </div>
            {save.isSuccess && save.variables.path === "/lab/replan" && (
              <p role="status" className="mb-4 text-[13px] text-muted">
                {t(
                  (save.data as { state?: string })?.state === "draft"
                    ? "lab.replan_drafted"
                    : "lab.replan_unchanged",
                )}
              </p>
            )}
            <CardHeader
              title={t("lab.planned_sessions")}
              right={
                <Link to="/app/coach?tab=changes" className="text-link">
                  {t("lab.changes")} ↗
                </Link>
              }
            />
            <QueryState
              loading={constraints.isLoading}
              error={constraints.isError}
              empty={constraints.data?.sessions.length === 0}
            />
            {constraints.data?.sessions.map((s) => (
              <details
                key={s.id}
                className="border-t border-hairline py-4 text-[13px]"
              >
                <summary className="cursor-pointer">
                  {s.date} · {s.session_type} · {s.duration_min ?? "—"} min
                </summary>
                <p className="my-4 text-muted">{s.description}</p>
                <Form
                  pending={save.isPending}
                  error={save.error}
                  label={t("lab.draft_change")}
                  onSave={(f) =>
                    save.mutate({
                      path: "/lab/changes",
                      body: {
                        change: {
                          kind: "session_patch",
                          target_id: s.id,
                          date: str(f, "date"),
                          target_duration_min: num(f, "duration"),
                        },
                        reason: str(f, "reason"),
                      },
                    })
                  }
                >
                  <div className="grid grid-cols-2 gap-3">
                    <Field
                      name="date"
                      type="date"
                      label={t("lab.start")}
                      value={s.date}
                      required
                    />
                    <Field
                      name="duration"
                      type="number"
                      min={0}
                      max={1440}
                      label={t("lab.duration")}
                      value={s.duration_min ?? 30}
                      required
                    />
                  </div>
                  <Field name="reason" label={t("lab.reason")} required />
                </Form>
                <a
                  href={`/lab/workouts/${s.id}/export`}
                  className="text-link mt-4"
                >
                  {t("lab.export_workout")} ↗
                </a>
              </details>
            ))}
          </Card>
          {save.isError && <ErrorNote message={save.error.message} />}
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader title={t("lab.add_event")} />
            <Form
              pending={save.isPending}
              error={save.error}
              onSave={(f) =>
                save.mutate({
                  path: "/events",
                  body: {
                    title: str(f, "title"),
                    kind: str(f, "kind"),
                    starts_at: new Date(str(f, "start")).toISOString(),
                    priority: num(f, "priority"),
                    taper_days: num(f, "taper"),
                    notes: str(f, "notes"),
                  },
                })
              }
            >
              <Field name="title" label={t("lab.title")} required />
              <Field name="kind" label={t("lab.event_kind")} value="race">
                {[
                  "race",
                  "run",
                  "ride",
                  "ski",
                  "sailing",
                  "competition",
                  "trip",
                  "training_camp",
                  "gym",
                  "other",
                ].map((k) => (
                  <option key={k} value={k}>
                    {t("lab.events." + k)}
                  </option>
                ))}
              </Field>
              <Field
                name="start"
                type="datetime-local"
                label={t("lab.start")}
                required
              />
              <div className="grid grid-cols-2 gap-3">
                <Field
                  name="priority"
                  label={t("lab.priority")}
                  type="number"
                  value={2}
                  min={1}
                  max={3}
                  required
                />
                <Field
                  name="taper"
                  label={t("lab.taper")}
                  type="number"
                  value={3}
                  min={0}
                  max={21}
                  required
                />
              </div>
              <Field name="notes" label={t("lab.notes")} type="textarea" />
            </Form>
          </Card>
          <Card>
            <CardHeader title={t("lab.availability")} />
            <Form
              pending={save.isPending}
              error={save.error}
              onSave={(f) =>
                save.mutate({
                  path: "/lab/entries",
                  body: {
                    entry: {
                      kind: "availability",
                      date: str(f, "date"),
                      minutes: num(f, "minutes"),
                      notes: str(f, "notes"),
                    },
                  },
                })
              }
            >
              <Field
                name="date"
                label={t("lab.start")}
                type="date"
                value={today}
                required
              />
              <Field
                name="minutes"
                label={t("lab.available_minutes")}
                type="number"
                min={0}
                max={1440}
                value={60}
                required
              />
              <Field name="notes" label={t("lab.notes")} type="textarea" />
            </Form>
          </Card>
        </div>
      </div>
    </div>
  );
}
