import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button, Card, CardHeader, ErrorNote, Loading } from "../../components/kit";
import { Field, Form, num, useAction, useLab, useToday } from "./shared";

export interface Notice {
  id: number;
  category: string;
  severity: string;
  state: string;
  payload: { title: string; why: string; action: string; href: string };
  expires_at: string;
  snoozed_until: string | null;
}
export interface NotificationsData {
  quiet_hours_active: boolean;
  preferences: {
    quiet_start_hour: number;
    quiet_end_hour: number;
    daily_cap: number;
    muted_classes: string[];
  };
  items: Notice[];
}

export function NotificationPopover({ onNavigate }: { onNavigate: () => void }) {
  const { t } = useTranslation();
  const q = useLab<NotificationsData>("/lab/notifications");
  const save = useAction();
  return (
    <div className="max-h-[min(70vh,580px)] overflow-y-auto p-4">
      {q.isLoading && <Loading />}
      {q.isError && <ErrorNote />}
      {q.data?.quiet_hours_active && <p className="mb-3 text-[12px] text-muted">{t("lab.quiet_active")}</p>}
      {q.data?.items.length === 0 && <p className="py-6 text-center text-[13px] text-muted">{t("navigation.no_notifications")}</p>}
      {q.data?.items.map((n) => (
        <div key={n.id} className="border-t border-hairline py-4 first:border-0">
          <div className="flex items-start justify-between gap-3">
            <strong className="text-[13px]">{n.payload.title}</strong>
            {n.state === "created" && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-ink" aria-label={t("navigation.unread")} />}
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">{n.payload.why}</p>
          {n.payload.href && <Link onClick={onNavigate} className="text-link mt-2 inline-block text-[12px]" to={n.payload.href}>{n.payload.action} ↗</Link>}
          <div className="mt-3 flex flex-wrap gap-2">
            {["read", "snoozed", "resolved"].map((state) => (
              <Button key={state} variant="ghost" disabled={save.isPending || n.state === state}
                onClick={() => save.mutate({ path: `/lab/notifications/${n.id}`, body: { state, snooze_hours: 24 } })}>
                {t("lab.notification_actions." + state)}
              </Button>
            ))}
          </div>
        </div>
      ))}
      {save.isError && <ErrorNote message={save.error.message} />}
    </div>
  );
}

export function NotificationPreferences() {
  const { t } = useTranslation();
  const today = useToday();
  const q = useLab<NotificationsData>("/lab/notifications");
  const save = useAction();
  return (
    <Card>
      <CardHeader title={t("lab.notification_preferences")} />
      {q.isLoading && <Loading />}
      {q.isError && <ErrorNote />}
      {q.data && <Form key={JSON.stringify(q.data.preferences)} pending={save.isPending} error={save.error}
        onSave={(f) => save.mutate({ path: "/lab/entries", body: { entry: {
          kind: "notification_preferences", date: today,
          quiet_start_hour: num(f, "start"), quiet_end_hour: num(f, "end"),
          daily_cap: num(f, "cap"), muted_classes: f.getAll("muted"),
        } } })}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field name="start" label={t("lab.quiet_start")} type="number" value={q.data.preferences.quiet_start_hour} min={0} max={23} required />
          <Field name="end" label={t("lab.quiet_end")} type="number" value={q.data.preferences.quiet_end_hour} min={0} max={23} required />
          <Field name="cap" label={t("lab.daily_cap")} type="number" value={q.data.preferences.daily_cap} min={0} max={20} required />
        </div>
        <p className="text-[12px] text-muted">{t("lab.mute_classes")}</p>
        {["sync", "data_quality", "training", "event", "gear", "system"].map((k) => (
          <label key={k} className="flex gap-2 text-[13px]">
            <input type="checkbox" name="muted" value={k} defaultChecked={q.data.preferences.muted_classes.includes(k)} />
            {t("lab.notification_classes." + k)}
          </label>
        ))}
        <p className="text-[12px] text-muted">{t("lab.external_delivery_note")}</p>
      </Form>}
    </Card>
  );
}

export default NotificationPreferences;
