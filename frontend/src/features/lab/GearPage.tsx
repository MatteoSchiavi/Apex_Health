import { useTranslation } from "react-i18next";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
  StatPod,
  fmtNum,
} from "../../components/kit";
import { Field, Form, num, QueryState, str, useAction, useLab } from "./shared";
interface Gear {
  gear_id: number;
  name: string;
  gear_type: string;
  active: boolean;
  hours_since_service: number;
  km_since_service: number;
  usage_pct: number | null;
  last_serviced_at: string | null;
}
export default function GearPage() {
  const { t } = useTranslation();
  const q = useLab<Gear[]>("/gear");
  const save = useAction();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("lab.gear")} subtitle={t("lab.gear_sub")} />
      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-5">
          <QueryState
            loading={q.isLoading}
            error={q.isError}
            empty={q.data?.length === 0}
          />
          {q.data?.map((g) => (
            <Card key={g.gear_id}>
              <CardHeader
                title={g.name}
                right={
                  <Badge
                    tone={
                      g.active && (g.usage_pct ?? 0) >= 100
                        ? "warning"
                        : "neutral"
                    }
                  >
                    {!g.active
                      ? t("lab.retired")
                      : (g.usage_pct ?? 0) >= 100
                        ? t("lab.service_due")
                        : t("lab.usage")}
                  </Badge>
                }
              />
              <div className="grid grid-cols-3 gap-4">
                <StatPod
                  label={t("lab.hours")}
                  value={fmtNum(g.hours_since_service, 1)}
                  unit="h"
                />
                <StatPod
                  label={t("lab.distance")}
                  value={fmtNum(g.km_since_service)}
                  unit="km"
                />
                <StatPod
                  label={t("lab.service_interval")}
                  value={fmtNum(g.usage_pct)}
                  unit="%"
                />
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  variant="ghost"
                  disabled={save.isPending || !g.active}
                  onClick={() =>
                    save.mutate({
                      path: `/gear/${g.gear_id}/service`,
                      body: { service_type: "inspection" },
                    })
                  }
                >
                  {t("lab.record_service")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={save.isPending || !g.active}
                  onClick={() =>
                    save.mutate({
                      path: `/gear/${g.gear_id}`,
                      method: "patch",
                      body: { active: false },
                    })
                  }
                >
                  {t("lab.retire")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader title={t("lab.add_gear")} />
          <Form
            pending={save.isPending}
            error={save.error}
            onSave={(f) =>
              save.mutate({
                path: "/gear",
                body: {
                  name: str(f, "name"),
                  gear_type: str(f, "type"),
                  service_interval_hours: num(f, "hours"),
                  service_interval_km: num(f, "km"),
                },
              })
            }
          >
            <Field name="name" label={t("lab.title")} required />
            <Field name="type" label={t("lab.gear_type")} value="bike">
              <option value="bike">{t("lab.gear_types.bike")}</option>
              <option value="shoes">{t("lab.gear_types.shoes")}</option>
              <option value="other">{t("lab.gear_types.other")}</option>
            </Field>
            <Field
              name="hours"
              label={t("lab.interval_hours")}
              type="number"
              min={1}
            />
            <Field
              name="km"
              label={t("lab.interval_km")}
              type="number"
              min={1}
            />
          </Form>
          {save.isError && <ErrorNote message={save.error.message} />}
        </Card>
      </div>
    </div>
  );
}
