/**
 * Sleep list — recent nights with score + stage composition sparkbars.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, type SleepList } from "../../app/api";
import {
  BigStat,
  Card,
  Empty,
  ErrorNote,
  Loading,
  fmtHours,
  fmtNum,
} from "../../components/kit";

export default function SleepListPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sleep"],
    queryFn: () => api.get<SleepList>("/sleep?limit=42"),
  });

  if (isLoading) return <Loading />;
  if (isError) return <ErrorNote />;
  const nights = data?.items ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="eyebrow">{t("app.name")} {t("app.suffix")}</div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          {t("sleep.title")}
        </h1>
      </div>

      {nights.length === 0 ? (
        <Empty>{t("sleep.no_night")}</Empty>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {nights.map((n) => {
            const total =
              (n.deep_s ?? 0) + (n.rem_s ?? 0) + (n.light_s ?? 0) + (n.awake_s ?? 0);
            const parts = [
              { key: "deep", v: n.deep_s ?? 0, color: "var(--c-stage-deep)" },
              { key: "rem", v: n.rem_s ?? 0, color: "var(--c-stage-rem)" },
              { key: "core", v: n.light_s ?? 0, color: "var(--c-stage-core)" },
              { key: "awake", v: n.awake_s ?? 0, color: "var(--c-stage-awake)" },
            ];
            const date = new Date(n.local_date + "T00:00:00");
            return (
              <Link key={n.local_date} to={`/app/sleep/${n.local_date}`}>
                <Card className="transition-colors hover:bg-surface2">
                  <div className="flex items-center justify-between">
                    <div className="eyebrow">
                      {date.toLocaleDateString(undefined, {
                        weekday: "short",
                        day: "numeric",
                        month: "short",
                      })}
                    </div>
                    <div className="num text-[13px] font-bold text-ink">
                      {fmtNum(n.sleep_score)}
                      <span className="ml-0.5 text-[10px] font-medium text-muted">/100</span>
                    </div>
                  </div>
                  <BigStat value={fmtHours(n.total_sleep_s)} size="md" className="mt-1.5" />
                  <div className="mt-3 flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full bg-hairline">
                    {total > 0 &&
                      parts.map((p) => (
                        <div
                          key={p.key}
                          className="h-full rounded-full"
                          style={{ width: `${(p.v / total) * 100}%`, background: p.color }}
                        />
                      ))}
                  </div>
                  <div className="num mt-1.5 flex gap-3 text-[10px] text-muted">
                    {parts.slice(0, 3).map((p) => (
                      <span key={p.key}>
                        <span
                          className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                          style={{ background: p.color }}
                        />
                        {t(`stage.${p.key}`)} {fmtHours(p.v)}
                      </span>
                    ))}
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
