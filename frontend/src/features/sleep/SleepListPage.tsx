/**
 * Sleep list — recent nights with score ring, stage composition bar and
 * headline stats. Header carries the 7-day averages (mockup: "Week at a
 * glance" strip above the grid).
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api, type SleepList } from "../../app/api";
import {
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  StatPod,
  fmtHours,
  fmtNum,
} from "../../components/kit";

function stageColor(key: string): string {
  return {
    deep: "var(--c-stage-deep)",
    rem: "var(--c-stage-rem)",
    core: "var(--c-stage-core)",
    awake: "var(--c-stage-awake)",
  }[key] ?? "var(--c-hairline2)";
}

export default function SleepListPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sleep"],
    queryFn: () => api.get<SleepList>("/sleep?limit=42"),
  });

  if (isLoading) return <Loading />;
  if (isError) return <ErrorNote />;
  const nights = data?.items ?? [];

  const last7 = nights.slice(0, 7);
  const avg = (pick: (n: SleepList["items"][number]) => number | null) => {
    const vals = last7.map(pick).filter((v): v is number => v !== null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  const avgScore = avg((n) => n.sleep_score);
  const avgDur = avg((n) => n.total_sleep_s);
  const avgDeep = avg((n) => n.deep_s);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("sleep.title")} subtitle={t("sleep.subtitle")} />

      {nights.length === 0 ? (
        <Card>
          <Empty>
            {t("sleep.no_night")}
          </Empty>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatPod label={t("sleep.avg_score7")} value={fmtNum(avgScore, 0)} unit="/100" tone="primary" />
            <StatPod label={t("sleep.avg_duration7")} value={fmtHours(avgDur)} />
            <StatPod label={t("sleep.avg_deep7")} value={fmtHours(avgDeep)} sub={t("sleep.restorative")} />
            <StatPod label={t("sleep.nights_tracked")} value={String(nights.length)} sub={t("sleep.window42")} />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {nights.map((n) => {
              const total =
                (n.deep_s ?? 0) + (n.rem_s ?? 0) + (n.light_s ?? 0) + (n.awake_s ?? 0);
              const parts = [
                { key: "deep", v: n.deep_s ?? 0 },
                { key: "rem", v: n.rem_s ?? 0 },
                { key: "core", v: n.light_s ?? 0 },
                { key: "awake", v: n.awake_s ?? 0 },
              ];
              const date = new Date(n.local_date + "T00:00:00");
              const score = n.sleep_score === null ? null : Math.round(n.sleep_score);
              return (
                <Link key={n.local_date} to={`/app/sleep/${n.local_date}`}>
                  <Card className="group transition-colors hover:bg-surface2">
                    <div className="flex items-center justify-between">
                      <div className="eyebrow">
                        {date.toLocaleDateString(undefined, {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                        })}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`num text-[15px] font-bold ${
                            score !== null && score >= 75
                              ? "text-positiveText"
                              : score !== null && score < 50
                                ? "text-warningText"
                                : "text-ink"
                          }`}
                        >
                          {fmtNum(n.sleep_score, 0)}
                        </span>
                        <span className="text-[10px] font-medium text-muted">/100</span>
                      </div>
                    </div>
                    <div className="num mt-1 flex items-baseline gap-2">
                      <span className="text-[26px] font-bold leading-8 text-ink">
                        {fmtHours(n.total_sleep_s)}
                      </span>
                      <span className="text-[11px] text-faint">
                        {new Date(n.start_time).toLocaleTimeString(undefined, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        →{" "}
                        {new Date(n.end_time).toLocaleTimeString(undefined, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <div className="mt-3 flex h-2 w-full gap-0.5 overflow-hidden rounded-full">
                      {total > 0 &&
                        parts.map((p) => (
                          <div
                            key={p.key}
                            title={t(`stage.${p.key}`)}
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.max(1, (p.v / total) * 100)}%`,
                              background: stageColor(p.key),
                            }}
                          />
                        ))}
                    </div>
                    <div className="num mt-2 flex items-center justify-between text-[10px] text-muted">
                      <div className="flex gap-3">
                        {parts.slice(0, 3).map((p) => (
                          <span key={p.key} className="flex items-center gap-1">
                            <span
                              className="inline-block h-1.5 w-1.5 rounded-full"
                              style={{ background: stageColor(p.key) }}
                            />
                            {fmtHours(p.v)}
                          </span>
                        ))}
                      </div>
                      <ArrowRight
                        size={12}
                        className="text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-primaryText"
                      />
                    </div>
                  </Card>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
