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
export default function CalendarPage() {
  const { t } = useTranslation();
  const today = useToday();
  const events = useLab<Event[]>("/events?horizon_days=180");
  const constraints = useLab<Constraints>("/lab/constraints");
  const save = useAction();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("lab.calendar")} subtitle={t("lab.calendar_sub")} />
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
                    {new Date(e.starts_at).toLocaleString()} · {t("lab.taper")}{" "}
                    {e.taper_days} {t("lab.days")}
                  </p>
                  {e.notes && <p className="mt-3 text-[13px]">{e.notes}</p>}
                </div>
                <Button
                  variant="ghost"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate({ path: `/events/${e.id}`, method: "delete" })
                  }
                >
                  {t("training.delete")}
                </Button>
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
