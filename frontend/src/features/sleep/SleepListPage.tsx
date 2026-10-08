import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { api, type SleepList } from "../../app/api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  StatPod,
  ZoneBar,
  fmtHours,
  fmtNum,
} from "../../components/kit";
import { assess } from "../../components/data";
import { SleepTimingChart } from "./SleepTimingChart";
import { useUi } from "../../app/stores/ui";
export default function SleepListPage() {
  const { t } = useTranslation();
  const timezone = useUi((s) => s.me?.timezone);
  const query = useQuery({
    queryKey: ["sleep"],
    queryFn: () => api.get<SleepList>("/sleep?limit=42"),
  });
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorNote />;
  const nights = query.data?.items ?? [],
    last7 = nights.slice(0, 7);
  function avg(pick: (n: SleepList["items"][number]) => number | null) {
    const values = last7.map(pick).filter((v): v is number => v != null);
    return values.length
      ? values.reduce((a, b) => a + b, 0) / values.length
      : null;
  }
  const clock = (date: string) =>
    new Date(date).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: timezone,
    });
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("sleep.title")} subtitle={t("design.sleep_sub")} />
      {!nights.length ? (
        <Card>
          <Empty>{t("sleep.no_night")}</Empty>
        </Card>
      ) : (
        <>
          <div className="stat-row">
            <StatPod
              label={t("sleep.avg_score7")}
              value={fmtNum(avg((n) => n.sleep_score))}
              unit="/100"
            />
            <StatPod
              label={t("sleep.avg_duration7")}
              value={fmtHours(avg((n) => n.total_sleep_s))}
            />
            <StatPod
              label={t("sleep.avg_deep7")}
              value={fmtHours(avg((n) => n.deep_s))}
            />
            <StatPod
              label={t("sleep.nights_tracked")}
              value={String(nights.length)}
              sub={t("design.recorded_nights")}
            />
          </div>
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="section-label">
                {t("sleep.bed_window")}
              </h2>
            </div>
            <SleepTimingChart nights={nights} />
            <p className="mt-3 text-[12px] text-muted">{t("completion.sleep_timing_note")}</p>
          </Card>
          <Card className="!py-0">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("design.night")}</th>
                    <th>{t("sleep.time_asleep")}</th>
                    <th>{t("overview.sleep_score")}</th>
                    <th>{t("sleep.bed_window")}</th>
                    <th>{t("sleep.architecture")}</th>
                    <th className="numeric">{t("sleep.efficiency")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {nights.map((n) => {
                    const state = assess("sleep_score", n.sleep_score);
                    const inBed =
                      (new Date(n.end_time).getTime() -
                        new Date(n.start_time).getTime()) /
                      1000;
                    return (
                      <tr key={n.local_date}>
                        <td>
                          <Link
                            to={"/app/sleep/" + n.local_date}
                            className="font-medium"
                          >
                            {new Date(
                              n.local_date + "T12:00:00",
                            ).toLocaleDateString(undefined, {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                            })}
                          </Link>
                        </td>
                        <td className="font-medium">
                          {fmtHours(n.total_sleep_s)}
                        </td>
                        <td>
                          <div className="flex items-center gap-3">
                            <span className="num">{fmtNum(n.sleep_score)}</span>
                            <Badge tone={state.tone}>{t(state.key)}</Badge>
                          </div>
                        </td>
                        <td className="text-muted">
                          {clock(n.start_time)} – {clock(n.end_time)}
                        </td>
                        <td className="min-w-[160px]">
                          <ZoneBar
                            height={8}
                            parts={[
                              {
                                key: "deep",
                                value: n.deep_s ?? 0,
                                color: "var(--c-stage-deep)",
                              },
                              {
                                key: "rem",
                                value: n.rem_s ?? 0,
                                color: "var(--c-stage-rem)",
                              },
                              {
                                key: "core",
                                value: n.light_s ?? 0,
                                color: "var(--c-stage-core)",
                              },
                              {
                                key: "awake",
                                value: n.awake_s ?? 0,
                                color: "var(--c-stage-awake)",
                              },
                            ]}
                          />
                        </td>
                        <td className="numeric">
                          {fmtNum(
                            inBed > 0 && n.total_sleep_s != null
                              ? (n.total_sleep_s / inBed) * 100
                              : null,
                          )}{" "}
                          %
                        </td>
                        <td>
                          <Link
                            to={"/app/sleep/" + n.local_date}
                            aria-label={t("design.open_night", {
                              date: n.local_date,
                            })}
                          >
                            <ArrowUpRight size={17} />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="flex flex-wrap gap-6 text-[12px] text-muted">
            {["deep", "rem", "core", "awake"].map((stage) => (
              <span key={stage} className="flex items-center gap-2">
                <span
                  className="h-2 w-2"
                  style={{ background: "var(--c-stage-" + stage + ")" }}
                />
                {t("stage." + stage)}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
