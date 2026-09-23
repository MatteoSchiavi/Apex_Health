/**
 * Activities list — paginated telemetry log with discipline + source chips.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, type ActivityListItem } from "../../app/api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  Loading,
  Segmented,
  fmtDuration,
  fmtNum,
} from "../../components/kit";

type Range = "30d" | "90d" | "12m";

function rangeStart(r: Range): string {
  const d = new Date();
  if (r === "30d") d.setDate(d.getDate() - 30);
  else if (r === "90d") d.setDate(d.getDate() - 90);
  else d.setMonth(d.getMonth() - 12);
  return d.toISOString().slice(0, 10);
}

export default function ActivitiesPage() {
  const { t } = useTranslation();
  const [range, setRange] = useState<Range>("90d");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["activities", range],
    queryFn: () =>
      api.get<{ items: ActivityListItem[]; total: number }>(
        `/activities?limit=60&start=${rangeStart(range)}`,
      ),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="eyebrow">{t("app.name")} {t("app.suffix")}</div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            {t("activities.title")}
          </h1>
        </div>
        <Segmented
          value={range}
          onChange={setRange}
          options={[
            { value: "30d", label: t("activities.30d") },
            { value: "90d", label: t("activities.90d") },
            { value: "12m", label: t("activities.12m") },
          ]}
        />
      </div>

      {isLoading && <Loading />}
      {isError && <ErrorNote />}
      {data && data.items.length === 0 && <Empty>{t("activities.empty")}</Empty>}

      {data && data.items.length > 0 && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.items.map((a) => (
            <Link key={a.id} to={`/app/activities/${a.id}`}>
              <Card className="transition-colors hover:bg-surface2" pad={false}>
                <div className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="eyebrow truncate">
                      {a.discipline ?? t("activities.title")}
                    </div>
                    <div className="flex items-center gap-1">
                      {a.sources.map((s) => (
                        <Badge key={s} tone="neutral">{s}</Badge>
                      ))}
                    </div>
                  </div>
                  <div className="num mt-1 flex items-baseline justify-between">
                    <span className="text-[13px] text-ink2">
                      {new Date(a.start_time).toLocaleDateString(undefined, {
                        weekday: "short",
                        day: "numeric",
                        month: "short",
                      })}{" "}
                      ·{" "}
                      {new Date(a.start_time).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                    <span className="text-[15px] font-bold text-ink">
                      {fmtDuration(a.duration_s)}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 border-t border-hairline pt-3">
                    <Mini label={t("activities.distance")} value={`${fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)}`} />
                    <Mini label={t("activities.avg_hr")} value={fmtNum(a.avg_hr)} />
                    <Mini label={t("activities.avg_power")} value={fmtNum(a.avg_power)} />
                    <Mini label={t("activities.tss")} value={fmtNum(a.training_load, 0)} />
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow truncate">{label}</div>
      <div className="num mt-0.5 text-[13px] font-semibold text-ink">{value}</div>
    </div>
  );
}
