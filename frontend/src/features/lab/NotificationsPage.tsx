import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
} from "../../components/kit";
import {
  Field,
  Form,
  num,
  QueryState,
  useAction,
  useLab,
  useToday,
} from "./shared";
interface Notice {
  id: number;
  category: string;
  severity: string;
  state: string;
  payload: { title: string; why: string; action: string; href: string };
  expires_at: string;
  snoozed_until: string | null;
}
export default function NotificationsPage() {
  const { t } = useTranslation();
  const today = useToday();
  const q = useLab<{
    quiet_hours_active: boolean;
    preferences: {
      quiet_start_hour: number;
      quiet_end_hour: number;
      daily_cap: number;
      muted_classes: string[];
    };
    items: Notice[];
  }>("/lab/notifications");
  const save = useAction();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("lab.notifications")}
        subtitle={t("lab.notifications_sub")}
      />
      {q.data?.quiet_hours_active && <Badge>{t("lab.quiet_active")}</Badge>}
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-4">
          <QueryState
            loading={q.isLoading}
            error={q.isError}
            empty={q.data?.items.length === 0}
          />
          {q.data?.items.map((n) => (
            <Card key={n.id}>
              <CardHeader
                title={n.payload.title}
                right={
                  <Badge
                    tone={
                      n.state === "resolved"
                        ? "positive"
                        : n.severity === "action"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {t("lab.states." + n.state, { defaultValue: n.state })}
                  </Badge>
                }
              />
              <p className="text-[14px] leading-relaxed">{n.payload.why}</p>
              <Link className="text-link mt-4" to={n.payload.href}>
                {n.payload.action} ↗
              </Link>
              <div className="mt-5 flex flex-wrap gap-2">
                {["read", "snoozed", "resolved"].map((state) => (
                  <Button
                    key={state}
                    variant="ghost"
                    disabled={save.isPending || n.state === state}
                    onClick={() =>
                      save.mutate({
                        path: `/lab/notifications/${n.id}`,
                        body: { state, snooze_hours: 24 },
                      })
                    }
                  >
                    {t("lab.notification_actions." + state)}
                  </Button>
                ))}
              </div>
            </Card>
          ))}
          {save.isError && <ErrorNote message={save.error.message} />}
        </div>
        <Card>
          <CardHeader title={t("lab.notification_preferences")} />
          {q.data && (
            <Form
              pending={save.isPending}
              error={save.error}
              onSave={(f) =>
                save.mutate({
                  path: "/lab/entries",
                  body: {
                    entry: {
                      kind: "notification_preferences",
                      date: today,
                      quiet_start_hour: num(f, "start"),
                      quiet_end_hour: num(f, "end"),
                      daily_cap: num(f, "cap"),
                      muted_classes: f.getAll("muted"),
                    },
                  },
                })
              }
            >
              <Field
                name="start"
                label={t("lab.quiet_start")}
                type="number"
                value={q.data.preferences.quiet_start_hour}
                min={0}
                max={23}
                required
              />
              <Field
                name="end"
                label={t("lab.quiet_end")}
                type="number"
                value={q.data.preferences.quiet_end_hour}
                min={0}
                max={23}
                required
              />
              <Field
                name="cap"
                label={t("lab.daily_cap")}
                type="number"
                value={q.data.preferences.daily_cap}
                min={0}
                max={20}
                required
              />
              <p className="text-[12px] text-muted">{t("lab.mute_classes")}</p>
              {[
                "sync",
                "data_quality",
                "training",
                "event",
                "gear",
                "system",
              ].map((k) => (
                <label key={k} className="flex gap-2 text-[13px]">
                  <input
                    type="checkbox"
                    name="muted"
                    value={k}
                    defaultChecked={q.data?.preferences.muted_classes.includes(
                      k,
                    )}
                  />
                  {t("lab.notification_classes." + k)}
                </label>
              ))}
              <p className="text-[12px] text-muted">
                {t("lab.external_delivery_note")}
              </p>
            </Form>
          )}
        </Card>
      </div>
    </div>
  );
}
